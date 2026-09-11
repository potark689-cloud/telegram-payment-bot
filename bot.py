import os
import asyncio
import threading
import requests

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("FAMPAY_API_KEY")
UPI_ID = os.getenv("UPI_ID")

QR_API = "https://fampay.anujbots.xyz/qr.php"
VERIFY_API = "https://fampay.anujbots.xyz/verify.php"

CHECK_INTERVAL = 5
QR_EXPIRE_SECONDS = 300

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram Payment Bot is running!"


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Payment करने के लिए:\n"
        "/pay 100\n\n"
        "Example: /pay 100"
    )


async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Amount बताइए।\n\nExample:\n/pay 100"
        )
        return

    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ सही amount डालें।")
        return

    try:
        response = requests.get(
            QR_API,
            params={
                "upi": UPI_ID,
                "amount": amount
            },
            timeout=20
        )

        data = response.json()

        if data.get("status") != "success":
            await update.message.reply_text(
                "❌ QR generate नहीं हो पाया।"
            )
            return

        order = data["data"]
        order_id = order["order_id"]
        qr_url = order["qr_url"]

        context.user_data["order_id"] = order_id
        context.user_data["amount"] = amount

        qr_image = requests.get(qr_url, timeout=20).content

        await update.message.reply_photo(
            photo=qr_image,
            caption=(
                f"💳 Payment करें\n\n"
                f"💰 Amount: ₹{amount:.2f}\n"
                f"🆔 Order ID: {order_id}\n\n"
                f"⏳ Payment के बाद verification automatically होगा।"
            )
        )

        asyncio.create_task(
            verify_payment(
                update,
                order_id,
                amount
            )
        )

    except Exception as e:
        print("PAY ERROR:", e)
        await update.message.reply_text(
            "❌ Payment QR बनाने में error आया।"
        )


async def verify_payment(update, order_id, expected_amount):
    elapsed = 0

    while elapsed < QR_EXPIRE_SECONDS:
        await asyncio.sleep(CHECK_INTERVAL)
        elapsed += CHECK_INTERVAL

        try:
            response = requests.get(
                VERIFY_API,
                params={
                    "order_id": order_id,
                    "api_key": API_KEY
                },
                timeout=20
            )

            result = response.json()

            if result.get("status") == "success":
                payment = result.get("data", result)

                paid_amount = float(
                    payment.get("amount", 0)
                )

                if abs(paid_amount - expected_amount) > 0.01:
                    await update.message.reply_text(
                        "⚠️ Payment मिला, लेकिन amount match नहीं करता।"
                    )
                    return

                transaction_id = payment.get(
                    "transaction_id",
                    "N/A"
                )

                utr = payment.get(
                    "utr",
                    "N/A"
                )

                sender = payment.get(
                    "sender_name",
                    "Unknown"
                )

                payment_time = payment.get(
                    "payment_time_ist",
                    "N/A"
                )

                await update.message.reply_text(
                    "✅ PAYMENT SUCCESSFUL!\n\n"
                    f"💰 Amount: ₹{paid_amount:.2f}\n"
                    f"👤 Sender: {sender}\n"
                    f"🔢 UTR: {utr}\n"
                    f"🆔 Transaction ID: {transaction_id}\n"
                    f"🕐 Time: {payment_time}"
                )

                return

        except Exception as e:
            print("VERIFY ERROR:", e)

    await update.message.reply_text(
        "⌛ Payment verification time खत्म हो गया।\n"
        "अगर आपने payment किया है तो support से संपर्क करें।"
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    if not API_KEY:
        raise RuntimeError("FAMPAY_API_KEY missing")

    if not UPI_ID:
        raise RuntimeError("UPI_ID missing")

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("pay", pay)
    )

    print("Bot starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
