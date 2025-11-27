import schedule
import time
from bot import analyze_and_notify
import os
from dotenv import load_dotenv

load_dotenv()

UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 3600))  # padrão: 1h

def start_scheduler():
    schedule.every(UPDATE_INTERVAL).seconds.do(analyze_and_notify)

    print(f"[Scheduler] Rodando a cada {UPDATE_INTERVAL} segundos...")

    while True:
        schedule.run_pending()
        time.sleep(1)
