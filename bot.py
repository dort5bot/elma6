import os
import csv
import threading
import requests
import time as time_module
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

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
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        return float(data.get("price", 0))
    except Exception as e:
        print(f"[get_price] HATA {symbol}: {e}")
        return None

def format_price(price: float):
    if price is None or price == 0:
        return "❌"
    return f"{price:.8f}$" if price < 1 else f"{price:.2f}$"

def get_ap_scores():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        data = requests.get(url, timeout=10).json()
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
    except Exception as e:
        print(f"[AP] HATA: {e}")
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
    keys = [["AP", "IO"], ["P BTC BNB"], ["F1", "F2", "F3"]]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

# =============== IO (PUBLIC API) ===============
def get_io(symbol, interval="15m", limit=50):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        b, s = 0, 0
        for k in data:
            o, c, v = float(k[1]), float(k[4]), float(k[5])
            if c > o:
                b += v
            else:
                s += v
        return round((b / (b + s) * 100), 2) if b + s > 0 else 0
    except Exception as e:
        print(f"[get_io] HATA {symbol}: {e}")
        return 0

# =============== KOMUTLAR ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot çalışıyor.\n"
        "Komutlar:\n"
        "/ap - Alt/BTC, Kısa Vade ve Uzun Vade puanları\n"
        "/p COIN1 COIN2 ... - Fiyat sorgusu\n"
        "/f1, /f2, /f3 - Hazır coin listeleri\n"
        "/io [coin] - IO raporu (15m,1h,4h,1d)\n"
        "/alarm - Alarm kur\n"
        "/alarmlist, /delalarm <id>\n"
        "/cleancsv all|ap|p|alarms - CSV temizle",
        reply_markup=get_keyboard()
    )

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

    text = f"""
📊 *AP Raporu*
- Altların BTC'ye karşı: {btc:.1f}/100{change_text(btc, prev_btc)}
- Alt Kısa Vade: {usdt:.1f}/100{change_text(usdt, prev_usdt)}
- Coinlerin Uzun Vade: {long:.1f}/100{change_text(long, prev_long)}
"""
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

async def f_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if text not in f_lists:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    results = [f"💹 *{text} Fiyatları:*"]
    for coin in f_lists[text]:
        price = get_price(coin)
        results.append(f"- {coin}: {format_price(price)}")
        save_csv(p_csv, [timestamp, text, coin, f"{price if price else 0:.6f}"])
    await update.message.reply_text("\n".join(results), parse_mode="Markdown")

async def io_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    coins = args[1:] if len(args) > 1 else ["BTC", "ETH", "BNB", "SOL"]
    tfs = ["15m", "1h", "4h", "1d"]
    text = "📊 *IO Raporu:*\n"
    for coin in coins:
        vals = [f"{get_io(f'{coin}USDT', tf):.1f}%" for tf in tfs]
        text += f"- {coin}: {' | '.join(vals)}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# =============== ALARM & TEMİZLİK ===============
# ... (BURAYA senin alarm ve cleanup kodların tam hali aynı şekilde kalacak)
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
# =============== KEEP-ALIVE ===============
def keep_alive():
    if not KEEP_ALIVE_URL:
        print("KEEP_ALIVE_URL ayarlanmamış.")
        return
    while True:
        try:
            requests.get(KEEP_ALIVE_URL, timeout=5)
            print(f"[KEEP-ALIVE] Ping gönderildi → {KEEP_ALIVE_URL}")
        except:
            pass
        time_module.sleep(60 * 5)

# =============== ANA FONKSİYON ===============
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ap", ap_command))
    app.add_handler(CommandHandler("p", price_command))
    app.add_handler(CommandHandler("io", io_command))
    app.add_handler(CommandHandler("alarm", alarm_command))
    app.add_handler(CommandHandler("alarmlist", alarmlist))
    app.add_handler(CommandHandler("delalarm", delalarm))
    app.add_handler(CommandHandler("cleancsv", cleancsv))
    app.add_handler(MessageHandler(filters.Regex("^(AP|ap)$"), ap_command))
    app.add_handler(MessageHandler(filters.Regex("^(P|p)\\s+"), price_command))
    app.add_handler(MessageHandler(filters.Regex("^(IO|io)\\s*"), io_command))
    app.add_handler(MessageHandler(filters.Regex("^F[0-9]+$"), f_list))

    app.job_queue.run_daily(auto_cleanup, time=time(hour=3, minute=0))

    threading.Thread(target=keep_alive, daemon=True).start()
    print("Bot Webhook ile çalışıyor...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="",
        webhook_url=KEEP_ALIVE_URL
    )

if __name__ == "__main__":
    main()
