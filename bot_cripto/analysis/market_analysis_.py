import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from utils.helpers import classify_altcoins, get_altcoin_index, diversification_strategy

load_dotenv()
CMC_API_KEY = os.getenv("COINMARKETCAP_API_KEY")

def fetch_market_data():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
    params = {"start": 1, "limit": 100, "convert": "USD"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()["data"]

def generate_report():
    data = fetch_market_data()
    btc = next((coin for coin in data if coin["symbol"] == "BTC"), None)

    altcoins = [c for c in data if c["symbol"] != "BTC"]
    blue, mid, low = classify_altcoins(altcoins)

    altcoin_index = get_altcoin_index()

    btc_price = btc["quote"]["USD"]["price"]
    btc_volume = btc["quote"]["USD"]["volume_24h"]
    btc_percent_change = btc["quote"]["USD"]["percent_change_24h"]

    btc_recommendation = "✅ BOM MOMENTO" if btc_percent_change > -1 and altcoin_index < 50 else "❌ EVITE"

    msg = f"📊 *Relatório Diário - {datetime.now().strftime('%d/%m/%Y')}*\n\n"
    msg += f"💰 *Bitcoin*\nPreço: ${btc_price:,.2f}\nVariação 24h: {btc_percent_change:.2f}%\nRecomendação: {btc_recommendation}\n\n"
    msg += f"📈 *Altcoin Index:* {altcoin_index}/100\n\n"

    def top_summary(title, coins):
        coins = sorted(coins, key=lambda x: x["market_cap"], reverse=True)[:5]
        return f"*{title}:*\n" + "\n".join([f"{c['symbol']} (${c['price']:.2f}) - MC: {c['market_cap']/1e9:.2f}B" for c in coins]) + "\n"

    msg += top_summary("🔵 Bluechips", blue)
    msg += top_summary("🟠 Médio porte", mid)
    msg += top_summary("🔴 Lowcaps", low)

    msg += "\n📦 *Diversificação sugerida:*\n"
    msg += diversification_strategy(len(blue), len(mid), len(low))

    return msg
