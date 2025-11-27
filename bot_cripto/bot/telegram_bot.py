import os
import telebot
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = telebot.TeleBot(TOKEN)


class TelegramBot:
    def send_message(self, message):
        bot.send_message(CHAT_ID, message)

    def run(self):
        @bot.message_handler(commands=["analise", "atualizar"])
        def send_report(msg):
            from analysis.market_analysis_ import generate_report
            bot.send_message(CHAT_ID, generate_report())

        bot.infinity_polling()
