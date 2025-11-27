import os
import requests
from dotenv import load_dotenv
from threading import Timer
from datetime import datetime, timedelta

load_dotenv()

def classify_altcoins(data):
    bluechips, midcaps, lowcaps = [], [], []
    for coin in data:
        mcap = coin["quote"]["USD"]["market_cap"]
        vol = coin["quote"]["USD"]["volume_24h"]
        info = {
            "name": coin["name"],
            "symbol": coin["symbol"],
            "price": coin["quote"]["USD"]["price"],
            "market_cap": mcap,
            "volume": vol
        }
        if mcap > 10e9:
            bluechips.append(info)
        elif 1e9 < mcap <= 10e9:
            midcaps.append(info)
        elif mcap < 1e9:
            lowcaps.append(info)
    return bluechips, midcaps, lowcaps

def get_altcoin_index():
    try:
        url = os.getenv("ALTCOIN_INDEX_API")
        response = requests.get(url)
        data = response.json()
        return int(data["data"][0]["value"])
    except Exception:
        return 50  # Valor neutro caso não carregue

def diversification_strategy(blue, mid, low):
    total = blue + mid + low
    if total == 0: return "Sem dados suficientes."

    return f"""
- 🔵 Bluechips: {int(blue/total*100)}%
- 🟠 Médio Porte: {int(mid/total*100)}%
- 🔴 Lowcaps: {int(low/total*100)}%
"""

def schedule_daily_task(callback, hour=9, minute=0):
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0)
    if now > target:
        target += timedelta(days=1)
    delay = (target - now).total_seconds()
    Timer(delay, run_daily, [callback]).start()

def run_daily(callback):
    callback()
    schedule_daily_task(callback)
