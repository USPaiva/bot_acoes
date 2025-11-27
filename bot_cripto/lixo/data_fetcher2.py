import requests

def fetch_market_data():
    response = requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd")
    return response.json()

def fetch_btc_data():
    return {
        "price": 50000.00,  # Exemplo
        "dominance": 45.0   # Exemplo
    }