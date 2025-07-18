import os
import csv
import threading
import asyncio
import requests
import time as time_module
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# == elma5_io_bot.py
# =============== ORTAM YÜKLEME ===============
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", 10000))
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL")

# =============== CSV DOSYALARI ===============
ap_csv = "ap_history.csv"
p_csv = "p_history.csv"
alarms_csv = "alarms.csv"

f_lists = {
    "F1": ["BTC", "ETH", "BNB", "SOL"],
    "F2": ["PEPE", "BOME", "DOGE"],
    "F3": ["S", "CAKE", "ZRO"]
}

# =============== GENEL FONKSİYONLAR ===============
def get_price(symbol: str):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT"
    try:
        data = requests.get(url, timeout=5).json()
        return float(data["price"])
    except:
        return None

def format_price(price: float):
    if price is None:
        return "❌"
    return f"{price:.8f}$" if price < 1 else f"{price:.2f}$"

def get_ap_scores():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        data = requests.get(url, timeout=5).json()
        alt_btc_strength, alt_usdt_strength, long_term_strength = [], [], []
        for c in data:
            symbol = c["symbol"]
            price_change = float(c["priceChangePercent"])
            volume = float(c["quoteVolume"])
            if symbol.endswith("BTC") and volume > 10:
                alt_btc_strength.append(price_change)
            if symbol.endswith("USDT") and volume > 1_000_000:
                alt_usdt_strength.append(price_change)
            if volume > 5_000_000:
                long_term_strength.append(price_change)

        def normalize(values):
            if not values:
                return 0
            avg = sum(values) / len(values)
            return max(0, min(100, (avg + 10) * 5))

        return normalize(alt_btc_strength), normalize(alt_usdt_strength), normalize(long_term_strength)
    except:
        return 0, 0, 0

def save_csv(filename, row):
    file_exists = os.path.exists(filename)
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            if "ap" in filename:
                writer.writerow(["Timestamp", "BTC", "USDT", "LONG"])
            elif "alarm" in filename:
                writer.writerow(["Timestamp", "Datetime", "Commands", "Repeat"])
            else:
                writer.writerow(["Timestamp", "List", "Coin", "Price"])
        writer.writerow(row)

def get_previous_ap():
    if not os.path.exists(ap_csv):
        return None, None, None
    with open(ap_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
        if len(rows) < 2:
            return None, None, None
        last = rows[-1]
        return float(last[1]), float(last[2]), float(last[3])

def get_keyboard():
    keys = [
        ["AP", "IO", "NPR"],
        ["P BTC BNB ETH", "F1", "F2", "F3"],
        ["/alarmlist", "/help"]
    ]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

# =============== IO FONKSİYONLARI (PUBLIC API) ===============
def get_io(symbol, interval="15m", limit=50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        klines = requests.get(url, timeout=5).json()
        b, s = 0, 0
        for k in klines:
            o, c, v = float(k[1]), float(k[4]), float(k[5])
            if c > o:
                b += v
            else:
                s += v
        return (b / (b + s) * 100) if b + s > 0 else 0
    except:
        return 0

def calc_mts(sym):
    s = get_io(sym, "15m")
    l = get_io(sym, "4h")
    return round((s + 1) / (l + 1), 1)

def market_inout(symbols, interval):
    tw = tv = 0
    for s in symbols:
        try:
            r = get_io(s, interval)
            v = float(requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={s}").json()['quoteVolume'])
            tw += r * v
            tv += v
        except:
            continue
    return tw / tv if tv else 0

def npr_calc(symbols):
    i15 = market_inout(symbols, "15m")
    i1 = market_inout(symbols, "1h")
    i4 = market_inout(symbols, "4h")
    return i15, i1, i4

# =============== KOMUTLAR ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✅ Birleşik Bot Çalışıyor.\n\n"
        "🔹 /ap - Alt Güç Raporu\n"
        "🔹 /io BTCUSDT - IO Hesabı (Örnek: /io BTCUSDT)\n"
        "🔹 /npr - Piyasa Nakit Raporu\n"
        "🔹 /p BTC BNB ETH - Coin fiyatları\n"
        "🔹 /f1, /f2, /f3 - Ön tanımlı coin listeleri fiyatları\n"
        "🔹 /alarm HH:MM komutlar - Günlük alarm kur\n"
        "🔹 /alarm YYYY-MM-DD HH:MM komutlar - Tek seferlik alarm\n"
        "🔹 /alarmlist - Kurulu alarmları listele\n"
        "🔹 /delalarm <id> - Alarm sil\n"
        "🔹 /cleancsv all|ap|p|alarms - CSV dosyalarını temizle\n"
        "🔹 /help - Komut listesi\n"
    )
    await update.message.reply_text(text, reply_markup=get_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def ap_command(update: Update, context: ContextTypes.DEFAULT_TYPE, auto=False):
    prev_btc, prev_usdt, prev_long = get_previous_ap()
    btc, usdt, long = get_ap_scores()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_csv(ap_csv, [timestamp, f"{btc:.2f}", f"{usdt:.2f}", f"{long:.2f}"])

    def change_text(current, previous):
        if previous is None:
            return ""
        diff = current - previous
        arrow = "🟢" if diff > 0 else "🔴"
        return f" {arrow} {diff:+.2f}"

    text = (
        f"📊 *AP Raporu*\n"
        f"- Altların BTC'ye karşı: {btc:.1f}/100{change_text(btc, prev_btc)}\n"
        f"- Alt Kısa Vade: {usdt:.1f}/100{change_text(usdt, prev_usdt)}\n"
        f"- Coinlerin Uzun Vade: {long:.1f}/100{change_text(long, prev_long)}"
    )
    if auto:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    coins = [c.upper() for c in text.split()[1:]]
    if not coins:
        await update.message.reply_text("❌ Kullanım: /p BTC BNB ETH ...")
        return

    results = []
    for coin in coins:
        price = get_price(coin)
        results.append(f"{coin}: {format_price(price)}")
    await update.message.reply_text("\n".join(results))

async def f_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip().upper()
    if cmd not in f_lists:
        await update.message.reply_text("❌ Geçersiz liste komutu. F1, F2 veya F3 kullanın.")
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    results = [f"💹 *{cmd} Fiyatları:*"]
    for coin in f_lists[cmd]:
        price = get_price(coin)
        results.append(f"- {coin}: {format_price(price)}")
        save_csv(p_csv, [timestamp, cmd, coin, f"{price if price else 0:.6f}"])
    await update.message.reply_text("\n".join(results), parse_mode="Markdown")

async def io_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("❌ Kullanım: /io BTCUSDT")
        return
    sym = args[1].upper()
    res = {tf: get_io(sym, tf) for tf in ["15m", "1h", "4h", "1d"]}
    mts = calc_mts(sym)
    trend = "".join("🔼" if res[tf] > res["1h"] else "🔻" for tf in res)
    text = f"📈 *IO Raporu*: {sym}\n"
    text += "\n".join([f"- {tf}: %{res[tf]:.1f}" for tf in res])
    text += f"\nMTS: {mts} {trend}"
    await update.message.reply_text(text, parse_mode="Markdown")

async def npr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"]
    i15, i1, i4 = npr_calc(symbols)
    msg = f"✅ *NPR*: 15m %{i15:.1f} | 1h %{i1:.1f} | 4h %{i4:.1f}"
    await update.message.reply_text(msg, parse_mode="Markdown")

# =============== ALARM İŞLEMLERİ ===============
async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = update.message.text.split()
        if len(args) < 3:
            await update.message.reply_text("❌ Kullanım: /alarm [YYYY-MM-DD] HH:MM komutlar\n veya /alarm HH:MM komutlar (günlük)")
            return

        # Günlük alarm (sadece saat:dakika)
        if len(args[1]) == 5 and ":" in args[1]:
            alarm_time = datetime.strptime(args[1], "%H:%M").time()
            commands = args[2:]
            context.job_queue.run_daily(trigger_alarm, time=alarm_time, data={"commands": commands, "repeat": True})
            save_csv(alarms_csv, [datetime.now().strftime("%Y-%m-%d %H:%M"), f"Her Gün {args[1]}", " ".join(commands), "YES"])
            await update.message.reply_text(f"✅ Her gün {args[1]} → {' '.join(commands)}")
            return

        # Tek seferlik alarm
        dt_str = f"{args[1]} {args[2]}"
        alarm_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        commands = args[3:]
        if alarm_time < datetime.now():
            await update.message.reply_text("❌ Geçmiş zaman için alarm kurulamaz.")
            return
        context.job_queue.run_once(trigger_alarm, when=alarm_time, data={"commands": commands, "repeat": False})
        save_csv(alarms_csv, [datetime.now().strftime("%Y-%m-%d %H:%M"), alarm_time.strftime("%Y-%m-%d %H:%M"), " ".join(commands), "NO"])
        await update.message.reply_text(f"✅ Alarm kuruldu: {alarm_time} → {' '.join(commands)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Alarm kurulamadı: {e}")

async def trigger_alarm(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    commands = job_data.get("commands", [])
    msg = f"⏰ *Alarm*: {' '.join(commands)}"
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

    # Taklit güncelleme objesi oluşturuyoruz, command fonksiyonlarını çağırırken
    class FakeMessage:
        def __init__(self):
            self.text = ""
        async def reply_text(self, text, **kwargs):
            await context.bot.send_message(chat_id=CHAT_ID, text=text, **kwargs)

    class FakeUpdate:
        def __init__(self):
            self.message = FakeMessage()

    fake_update = FakeUpdate()
    for cmd in commands:
        cmd_lower = cmd.lower()
        if cmd_lower == "ap":
            await ap_command(fake_update, context, auto=True)
        elif cmd_upper := cmd.upper():
            if cmd_upper in f_lists:
                fake_update.message.text = cmd_upper
                await f_list_command(fake_update, context)
            elif cmd_upper.startswith("P"):
                # Fiyat sorgusu: P BTC BNB
                fake_update.message.text = cmd
                await price_command(fake_update, context)
            elif cmd_lower == "io":
                fake_update.message.text = "/io BTCUSDT"  # örnek default
                await io_command(fake_update, context)
            elif cmd_lower == "npr":
                await npr_command(fake_update, context)

async def alarmlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(alarms_csv):
        await update.message.reply_text("❌ Kayıtlı alarm yok.")
        return
    with open(alarms_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    if not rows:
        await update.message.reply_text("❌ Kayıtlı alarm yok.")
        return
    text = "⏰ *Kurulu Alarmlar:*\n"
    for i, r in enumerate(rows, start=1):
        text += f"{i}. {r[1]} → {r[2]} ({'Tek Sefer' if r[3]=='NO' else 'Her Gün'})\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def delalarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("❌ Kullanım: /delalarm <id>")
        return
    alarm_id = int(args[1])
    if not os.path.exists(alarms_csv):
        await update.message.reply_text("❌ Alarm bulunamadı.")
        return
    with open(alarms_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if alarm_id < 1 or alarm_id >= len(rows):
        await update.message.reply_text("❌ Geçersiz ID.")
        return
    del rows[alarm_id]
    with open(alarms_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    await update.message.reply_text("✅ Alarm silindi.")

# =============== TEMİZLİK İŞLEMLERİ ===============
def cleanup_csv_file(filename, days=30, max_lines=10000):
    if not os.path.exists(filename):
        return
    with open(filename, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) <= 1:
        return
    header, data = rows[0], rows[1:]
    filtered = []
    now = datetime.now()
    for row in data:
        try:
            row_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if now - row_time <= timedelta(days=days):
                filtered.append(row)
        except:
            filtered.append(row)
    if len(filtered) > max_lines:
        filtered = filtered[-max_lines:]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(filtered)

async def auto_cleanup(context: ContextTypes.DEFAULT_TYPE):
    for file in [ap_csv, p_csv, alarms_csv]:
        cleanup_csv_file(file)
    await context.bot.send_message(chat_id=CHAT_ID, text="✅ Otomatik temizlik tamamlandı.")

async def cleancsv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    target = args[1].lower() if len(args) > 1 else "all"
    files = {
        "ap": ap_csv,
        "p": p_csv,
        "alarms": alarms_csv
    }
    if target == "all":
        for f in files.values():
            cleanup_csv_file(f, days=0, max_lines=0)
        await update.message.reply_text("✅ Tüm CSV dosyaları temizlendi.")
    elif target in files:
        cleanup_csv_file(files[target], days=0, max_lines=0)
        await update.message.reply_text(f"✅ {target} CSV dosyası temizlendi.")
    else:
        await update.message.reply_text("❌ Geçersiz parametre. Kullanım: /cleancsv all|ap|p|alarms")

# =============== KEEP-ALIVE ===============
def keep_alive():
    if not KEEP_ALIVE_URL:
        print("KEEP_ALIVE_URL ayarlanmamış.")
        return
    while True:
        try:
            requests.get(KEEP_ALIVE_URL, timeout=5)
            print(f"[KEEP-ALIVE] Ping gönderildi → {KEEP_ALIVE_URL}")
        except Exception as e:
            print(f"[KEEP-ALIVE] Hata: {e}")
        time_module.sleep(60 * 5)

# =============== ANA FONKSİYON ===============
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Komutlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ap", ap_command))
    app.add_handler(CommandHandler("p", price_command))
    app.add_handler(CommandHandler("f1", f_list_command))
    app.add_handler(CommandHandler("f2", f_list_command))
    app.add_handler(CommandHandler("f3", f_list_command))
    app.add_handler(CommandHandler("io", io_command))
    app.add_handler(CommandHandler("npr", npr_command))

    app.add_handler(CommandHandler("alarm", alarm_command))
    app.add_handler(CommandHandler("alarmlist", alarmlist))
    app.add_handler(CommandHandler("delalarm", delalarm))
    app.add_handler(CommandHandler("cleancsv", cleancsv))

    # Otomatik Temizlik Her Gün Saat 04:00
    app.job_queue.run_daily(auto_cleanup, time=time(hour=4, minute=0))

    # Keep-Alive Thread
    threading.Thread(target=keep_alive, daemon=True).start()

    print("Birleşik Bot Çalışıyor...")
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path="", webhook_url=KEEP_ALIVE_URL)

if __name__ == "__main__":
    main()
