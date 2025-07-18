import os
import time
import json
import threading
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

# .env yükle
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL")
PORT = int(os.getenv("PORT", 10000))

# ================================
# KEEP-ALIVE
# ================================
def keep_alive():
    while True:
        try:
            if KEEP_ALIVE_URL:
                requests.get(KEEP_ALIVE_URL, timeout=10)
                print(f"[KEEP-ALIVE] Ping gönderildi → {KEEP_ALIVE_URL}")
        except Exception as e:
            print(f"[KEEP-ALIVE-ERROR] {e}")
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

# ================================
# START KOMUTU
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot çalışıyor!\n"
        "Komutlar:\n"
        "/ap → Altcoin Power raporu\n"
        "/io → IO (zaman dilimi bazlı değişim)\n"
        "/p <coin> → Tek coin fiyatı\n"
        "/help → Tüm komutlar"
    )

# ================================
# HELP KOMUTU
# ================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Komut Listesi:*\n"
        "/ap → Altcoin Power (AP) raporu\n"
        "/io → IO raporu (BTC, ETH, BNB, SOL)\n"
        "/p <coin> → Coin fiyatı ör: /p btc\n"
        "/start → Botu başlat\n"
        "/help → Bu mesaj",
        parse_mode="Markdown"
    )

# ================================
# P KOMUTU (TEK COIN)
# ================================
async def p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("Kullanım: /p btc")
            return

        coin = context.args[0].upper() + "USDT"
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={coin}", timeout=10)
        print(f"[DEBUG-P] {coin} → {r.status_code} → {r.text}")

        data = r.json()
        price = float(data.get("price", 0))
        await update.message.reply_text(f"{coin.replace('USDT','')}: {price:.2f}$")
    except Exception as e:
        await update.message.reply_text(f"❌ P Hatası: {e}")
        print(f"[DEBUG-P-ERROR] {e}")

# ================================
# AP KOMUTU (DEBUG EKLENDİ)
# ================================
async def ap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("⏳ AP verisi alınıyor...")
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        report_lines = []

        for symbol in symbols:
            r = requests.get(
                f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}",
                timeout=10,
            )
            print(f"[DEBUG-AP-RAW] {symbol} → {r.status_code} → {r.text}")

            data = r.json()
            last_price = float(data.get("lastPrice", 0))
            change_percent = float(data.get("priceChangePercent", 0))
            volume = float(data.get("quoteVolume", 0))

            report_lines.append(
                f"{symbol.replace('USDT','')}: {last_price:.2f}$ | {change_percent:+.2f}% | Hacim: {volume/1e6:.2f}M"
            )

        report = "📊 *AP Raporu*\n" + "\n".join(report_lines)
        await update.message.reply_text(report, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ AP Hatası: {e}")
        print(f"[DEBUG-AP-ERROR] {e}")

# ================================
# IO KOMUTU (DEBUG EKLENDİ)
# ================================
async def io_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("⏳ IO verisi alınıyor...")
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
        intervals = {"15m": "15dk", "1h": "1saat", "4h": "4saat", "1d": "24saat"}
        report_lines = []

        for symbol in symbols:
            changes = []
            for interval, label in intervals.items():
                r = requests.get(
                    f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=2",
                    timeout=10,
                )
                print(f"[DEBUG-IO-RAW] {symbol} [{interval}] → {r.status_code} → {r.text}")

                data = r.json()
                if len(data) >= 2:
                    close_prev = float(data[0][4])
                    close_now = float(data[1][4])
                    change = ((close_now - close_prev) / close_prev) * 100
                    changes.append(f"{label}: {change:+.2f}%")

            report_lines.append(f"{symbol.replace('USDT','')}: " + " | ".join(changes))

        report = "📊 *IO Raporu*\n" + "\n".join(report_lines)
        await update.message.reply_text(report, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ IO Hatası: {e}")
        print(f"[DEBUG-IO-ERROR] {e}")

# ================================
# ANA ÇALIŞTIRICI
# ================================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("p", p_command))
    app.add_handler(CommandHandler("ap", ap_command))
    app.add_handler(CommandHandler("io", io_command))

    print("✅ Bot Başlatıldı...")
    app.run_polling()

if __name__ == "__main__":
    main()
