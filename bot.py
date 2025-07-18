import os
import asyncio
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ------------------- IO VERİ FONKSİYONU -------------------
def get_io_data(symbols=["BTC", "ETH", "BNB", "SOL"]):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for sym in symbols:
            pair = sym + "USDT"
            item = next((x for x in data if x["symbol"] == pair), None)
            if item:
                price_change_percent = float(item["priceChangePercent"])
                high_price = float(item["highPrice"])
                low_price = float(item["lowPrice"])
                volume = float(item["quoteVolume"]) / 1_000_000  # Milyon USDT
                results.append(
                    f"{sym}: {price_change_percent:.2f}% | H:{high_price:.2f} | L:{low_price:.2f} | V:{volume:.2f}M"
                )
            else:
                results.append(f"{sym}: ❌ Veri yok")
        return "\n".join(results)
    except Exception as e:
        return f"❌ IO Hatası: {e}"

# ------------------- AP VERİ FONKSİYONU -------------------
def get_ap_data(symbols=["BTC", "ETH", "BNB"]):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for sym in symbols:
            pair = sym + "USDT"
            item = next((x for x in data if x["symbol"] == pair), None)
            if item:
                last_price = float(item["lastPrice"])
                price_change_percent = float(item["priceChangePercent"])
                volume = float(item["quoteVolume"]) / 1_000_000
                results.append(
                    f"{sym}: {last_price:.2f}$ | {price_change_percent:+.2f}% | Hacim:{volume:.2f}M"
                )
            else:
                results.append(f"{sym}: ❌ Veri yok")
        return "\n".join(results)
    except Exception as e:
        return f"❌ AP Hatası: {e}"

# ------------------- TELEGRAM KOMUTLARI -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot çalışıyor! Komutlar: /ap , /io , /p btc")

async def ap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ AP verisi alınıyor...")
    result = get_ap_data()
    await update.message.reply_text(f"📊 AP Raporu\n{result}")

async def io_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ IO verisi alınıyor...")
    result = get_io_data()
    await update.message.reply_text(f"📊 IO Raporu\n{result}")

async def p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("⚠️ Kullanım: /p BTC")
        return

    symbol = context.args[0].upper()
    result = get_ap_data([symbol])
    await update.message.reply_text(result)

# ------------------- MAIN -------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ap", ap_command))
    app.add_handler(CommandHandler("io", io_command))
    app.add_handler(CommandHandler("p", p_command))

    print("✅ Bot Çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
