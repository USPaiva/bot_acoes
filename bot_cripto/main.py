from bot.telegram_bot import TelegramBot
from analysis.market_analysis import generate_report
from utils.helpers import schedule_daily_task

if __name__ == "__main__":
    bot = TelegramBot()
    schedule_daily_task(lambda: bot.send_message(generate_report()))
    bot.run()  # Mantém o bot escutando comandos
