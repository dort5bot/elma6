import os
import csv
import threading
import requests
import time as time_module
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
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
        return float(res.json().get("price", 0))
    except:
        return None

def format_price(price: float):
    if price is None or price == 0:
        return "❌"
    return f"{price:.8f}$" if price < 1 else f"{price:.2f}$"

def save_csv(filename, row, headers=None):
    file_exists = os.path.exists(filename)
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists and headers:
            writer.writerow(headers)
        writer.writerow(row)

# =============== AP FONKSİYONLARI ===============
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
    except:
        return 0, 0, 0

def get_previous_ap():
    if not os.path.exists(ap_csv):
        return None, None, None
    with open(ap_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
        if len(rows) < 2:
            return None, None, None
        last = rows[-1]
        return float(last[1]), float(last[2]), float(last[3])

# =============== IO FONKSİYONLARI ===============
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
    except:
        return 0

# =============== KOMUTLAR ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot Çalışıyor\n"
        "/ap - AP puanları\n"
        "/p COIN1 COIN2 - Fiyat\n"
        "/io [coin] - IO raporu\n"
        "/f1, /f2, /f3 - Hazır listeler\n"
        "/alarm <tarih-saat> <komut> - Alarm ekle\n"
        "/alarmlist - Alarm listesi\n"
        "/delalarm <id> - Alarm sil\n"
        "/cleancsv all|ap|p|alarms - CSV temizle",
        reply_markup=ReplyKeyboardMarkup([["AP", "IO"], ["P BTC"], ["F1", "F2", "F3"]], resize_keyboard=True)
    )

async def ap_command(update: Update, context: ContextTypes.DEFAULT_TYPE, auto=False):
    prev_btc, prev_usdt, prev_long = get_previous_ap()
    btc, usdt, long = get_ap_scores()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_csv(ap_csv, [timestamp, f"{btc:.2f}", f"{usdt:.2f}", f"{long:.2f}"],
             ["Timestamp", "BTC", "USDT", "LONG"])

    def change_text(current, previous):
        if previous is None:
            return ""
        diff = current - previous
        arrow = "🟢" if diff > 0 else "🔴"
        return f" {arrow} {diff:+.2f}"

    text = (
        f"📊 *AP Raporu*\n"
        f"- Alt/BTC: {btc:.1f}/100{change_text(btc, prev_btc)}\n"
        f"- Alt/USDT: {usdt:.1f}/100{change_text(usdt, prev_usdt)}\n"
        f"- Uzun Vade: {long:.1f}/100{change_text(long, prev_long)}"
    )
    if auto:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coins = [c.upper() for c in update.message.text.split()[1:]]
    if not coins:
        await update.message.reply_text("❌ Kullanım: /p BTC BNB ETH ...")
        return
    results = []
    for coin in coins:
        price = get_price(coin)
        results.append(f"{coin}: {format_price(price)}")
    await update.message.reply_text("\n".join(results))

async def f_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    list_name = update.message.text.strip().upper()
    if list_name not in f_lists:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    results = [f"💹 *{list_name} Fiyatları:*"]
    for coin in f_lists[list_name]:
        price = get_price(coin)
        results.append(f"- {coin}: {format_price(price)}")
        save_csv(p_csv, [timestamp, list_name, coin, f"{price if price else 0:.6f}"],
                 ["Timestamp", "List", "Coin", "Price"])
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
async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /alarm 2025-07-19_15:30 /ap")
        return
    date_str, command = context.args[0], " ".join(context.args[1:])
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d_%H:%M")
        save_csv(alarms_csv, [datetime.now().strftime("%Y-%m-%d %H:%M"), dt, command, "no"],
                 ["Timestamp", "Datetime", "Commands", "Repeat"])
        context.job_queue.run_once(run_alarm, dt, chat_id=update.effective_chat.id, name=str(dt),
                                   data={"command": command})
        await update.message.reply_text(f"✅ Alarm eklendi: {dt} → {command}")
    except:
        await update.message.reply_text("❌ Tarih formatı hatalı. Örn: 2025-07-19_15:30")

async def run_alarm(context: ContextTypes.DEFAULT_TYPE):
    cmd = context.job.data["command"]
    if "/ap" in cmd:
        await ap_command(None, context, auto=True)
    else:
        await context.bot.send_message(chat_id=CHAT_ID, text=f"🔔 Alarm: {cmd}")

async def alarmlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(alarms_csv):
        await update.message.reply_text("🔕 Alarm yok")
        return
    with open(alarms_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
        if len(rows) < 2:
            await update.message.reply_text("🔕 Alarm yok")
            return
        text = "⏰ *Alarm Listesi:*\n"
        for i, r in enumerate(rows[1:], start=1):
            text += f"{i}) {r[1]} → {r[2]}\n"
        await update.message.reply_text(text, parse_mode="Markdown")

async def delalarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Kullanım: /delalarm 1")
        return
    idx = int(context.args[0])
    if not os.path.exists(alarms_csv):
        await update.message.reply_text("🔕 Alarm yok")
        return
    with open(alarms_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if idx >= len(rows):
        await update.message.reply_text("❌ Alarm bulunamadı")
        return
    del rows[idx]
    with open(alarms_csv, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    await update.message.reply_text("✅ Alarm silindi")

async def cleancsv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Kullanım: /cleancsv all|ap|p|alarms")
        return
    t = context.args[0]
    files = {"ap": ap_csv, "p": p_csv, "alarms": alarms_csv}
    if t == "all":
        for f in files.values():
            if os.path.exists(f): os.remove(f)
        await update.message.reply_text("✅ Tüm CSV'ler temizlendi")
    elif t in files:
        if os.path.exists(files[t]): os.remove(files[t])
        await update.message.reply_text(f"✅ {t} CSV temizlendi")
    else:
        await update.message.reply_text("❌ Geçersiz seçenek")

# =============== KEEP-ALIVE ===============
def keep_alive():
    if not KEEP_ALIVE_URL:
        return
    while True:
        try:
            requests.get(KEEP_ALIVE_URL, timeout=5)
        except:
            pass
        time_module.sleep(300)

# =============== ANA FONKSİYON ===============
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ap", ap_command))
    app.add_handler(CommandHandler("p", price_command))
    app.add_handler(CommandHandler("io", io_command))
    app.add_handler(CommandHandler("f1", f_list))
    app.add_handler(CommandHandler("f2", f_list))
    app.add_handler(CommandHandler("f3", f_list))
    app.add_handler(CommandHandler("alarm", alarm_command))
    app.add_handler(CommandHandler("alarmlist", alarmlist))
    app.add_handler(CommandHandler("delalarm", delalarm))
    app.add_handler(CommandHandler("cleancsv", cleancsv))
    app.add_handler(MessageHandler(filters.Regex("^(AP|ap)$"), ap_command))
    app.add_handler(MessageHandler(filters.Regex("^(P|p)\\s+"), price_command))
    app.add_handler(MessageHandler(filters.Regex("^(IO|io)\\s*"), io_command))
    app.add_handler(MessageHandler(filters.Regex("^F[0-9]+$"), f_list))

    app.job_queue.run_daily(lambda ctx: ap_command(None, ctx, auto=True), time=time(hour=3, minute=0))
    threading.Thread(target=keep_alive, daemon=True).start()

    print("Birleşik Bot Çalışıyor...")
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path="", webhook_url=KEEP_ALIVE_URL)

if __name__ == "__main__":
    main()
