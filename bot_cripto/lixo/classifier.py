def classify_altcoins(data):
    bluechips, midcaps, lowcaps = [], [], []

    for coin in data:
        try:
            quote = coin["quote"]["USD"]
            market_cap = quote["market_cap"]
            volume = quote["volume_24h"]
            price = quote["price"]
            name = coin["name"]
            symbol = coin["symbol"]

            info = {
                "name": name,
                "symbol": symbol,
                "price": price,
                "market_cap": market_cap,
                "volume": volume
            }

            if market_cap > 10e9:
                bluechips.append(info)
            elif 1e9 < market_cap <= 10e9:
                midcaps.append(info)
            else:
                lowcaps.append(info)
        except Exception as e:
            print(f"Erro ao classificar {coin.get('name')}: {e}")

    return bluechips, midcaps, lowcaps
