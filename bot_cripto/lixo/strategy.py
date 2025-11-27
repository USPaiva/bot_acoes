from data_fetcher2 import fetch_market_data, fetch_btc_data
from classifier import classify_altcoins
from utils import save_to_csv

def generate_recommendations():
    market_data = fetch_market_data()
    btc_data = fetch_btc_data()
    btc_price = btc_data["price"]
    btc_dominance = btc_data["dominance"]

    blue, mid, low = classify_altcoins(market_data)
    save_to_csv(blue + mid + low)

    recommendations = []

    # BTC recomendação
    if btc_dominance < 50:
        recommendations.append("📉 *Bitcoin:* Dominância baixa, boa oportunidade para comprar Altcoins.")
    elif btc_dominance > 60:
        recommendations.append("📈 *Bitcoin:* Dominância alta, foco em BTC ou venda parcial de Altcoins.")

    # Lógica de venda (simplificada)
    for group, name in [(blue, "🔷 Bluechips"), (mid, "🔶 Midcaps"), (low, "🔴 Lowcaps")]:
        if group:
            recommendations.append(f"\n{name}:")
            for coin in group[:5]:  # Top 5
                price = coin["price"]
                market_cap = coin["market_cap"]
                volume = coin["volume"]
                signal = "✅ Comprar" if volume > 0.5 * market_cap else "⚠️ Observar"
                recommendations.append(f"- {coin['symbol']} (${price:.2f}) – {signal}")

    return "\n".join(recommendations)
