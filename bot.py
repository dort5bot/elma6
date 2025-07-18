import os
import threading
import time as time_module
from datetime import datetime
import requests
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram import Update

# .env yükle
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", 10000))
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL")

# ================================
# 1) KEEP-ALIVE (Render uyku engelleme)
# ================================
def keep_alive():
    def run():
        while True:
            try:
                if KEEP_ALIVE_URL:
                    r = requests.get(KEEP_ALIVE_URL, timeout=10)
                    print(f"[KEEP-ALIVE] Ping → {KEEP_ALIVE_URL} [{r.status_code}]")
            except Exception as e:
                print(f"[KEEP-ALIVE ERROR] {e}")
            time_module.sleep(300)  # 5 dk'da bir ping
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()


# ================================
# 2) START & HELP KOMUTLARI
# ================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot Çalışıyor!\n\n"
        "Komutlar:\n"
        "/ap → Alt/BTC, Alt/USDT raporu\n"
        "/io → 15dk,1s,4s,24s değişim yüzdeleri\n"
        "/p <coin> → Tek coin fiyat bilgisi\n"
        "/help → Komut listesi"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


# ================================
# 3) AP KOMUTU (GÜNCELLENDİ)
# ================================
async def ap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("⏳ AP verisi alınıyor...")
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        report_lines = []

        for symbol in symbols:
            data = requests.get(
                f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}",
                timeout=10,
            ).json()

            last_price = float(data.get("lastPrice", 0))
            change_percent = float(data.get("priceChangePercent", 0))
            volume = float(data.get("quoteVolume", 0))

            report_lines.append(
                f"{symbol.replace('USDT','')}: {last_price:.2f}$ | {change_percent:+.2f}% | Hacim: {volume/1e6:.2f}M"
            )

            print(
                f"[DEBUG-AP] {symbol} -> Fiyat: {last_price}, Değişim: {change_percent}, Hacim: {volume}"
            )

        report = "📊 *AP Raporu*\n" + "\n".join(report_lines)
        await update.message.reply_text(report, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ AP Hatası: {e}")
        print(f"[DEBUG-AP-ERROR] {e}")


# ================================
# 4) IO KOMUTU (GÜNCELLENDİ)
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
                data = requests.get(
                    f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=2",
                    timeout=10,
                ).json()

                if len(data) >= 2:
                    close_prev = float(data[0][4])
                    close_now = float(data[1][4])
                    change = ((close_now - close_prev) / close_prev) * 100
                    changes.append(f"{label}: {change:+.2f}%")

                    print(
                        f"[DEBUG-IO] {symbol} [{interval}] -> Önceki: {close_prev}, Şimdi: {close_now}, Değişim: {change}%"
                    )

            report_lines.append(f"{symbol.replace('USDT','')}: " + " | ".join(changes))

        report = "📊 *IO Raporu*\n" + "\n".join(report_lines)
        await update.message.reply_text(report, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ IO Hatası: {e}")
        print(f"[DEBUG-IO-ERROR] {e}")


# ================================
# 5) P KOMUTU (Tek coin)
# ================================
async def p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Kullanım: /p <coin>\nÖr: /p btc")
            return

        coin = context.args[0].upper() + "USDT"
        data = requests.get(
            f"https://api.binance.com/api/v3/ticker/24hr?symbol={coin}",
            timeout=10,
        ).json()

        price = float(data.get("lastPrice", 0))
        change = float(data.get("priceChangePercent", 0))
        volume = float(data.get("quoteVolume", 0))

        msg = f"{coin.replace('USDT','')}: {price:.2f}$ | {change:+.2f}% | Hacim: {volume/1e6:.2f}M"
        await update.message.reply_text(msg)

        print(f"[DEBUG-P] {coin} -> {msg}")

    except Exception as e:
        await update.message.reply_text(f"❌ P Hatası: {e}")
        print(f"[DEBUG-P-ERROR] {e}")


# ================================
# 6) MAIN
# ================================
def main():
    keep_alive()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ap", ap_command))
    app.add_handler(CommandHandler("io", io_command))
    app.add_handler(CommandHandler("p", p_command))

    print("✅ Birleşik Bot Çalışıyor...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{KEEP_ALIVE_URL}/{TOKEN}",
    )


if __name__ == "__main__":
    main()
