import telegram
from telegram.ext import Updater, CommandHandler
from strategy import generate_recommendations
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telegram.Bot(token=TOKEN)

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Bot ativo. Use /analisar para executar a análise.")

def analisar(update, context):
    message = generate_recommendations()
    context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode="Markdown")

def analyze_and_notify():
    message = generate_recommendations()
    bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

def run_telegram_bot():
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("analisar", analisar))

    updater.start_polling()
    updater.idle()
