import os
import re
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Mantém seus helpers existentes
from utils.helpers import classify_altcoins, diversification_strategy

load_dotenv()

# Opcional (apenas se você tiver; não é obrigatório no modo gratuito)
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY")

# Headers para scraping leve
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

# ---------- FONTES GRATUITAS / FALLBACKS ----------

def fetch_market_data():
    """
    GRATUITO: CoinGecko /coins/markets
    Retorna em formato compatível com sua lógica (simulando estrutura CMC 'quote'->'USD')
    """
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    mapped = []
    for c in data:
        mapped.append({
            "name": c.get("name"),
            "symbol": c.get("symbol", "").upper(),
            "quote": {
                "USD": {
                    "price": c.get("current_price"),
                    "volume_24h": c.get("total_volume"),
                    "market_cap": c.get("market_cap"),
                    "percent_change_24h": c.get("price_change_percentage_24h_in_currency"),
                    "percent_change_7d": c.get("price_change_percentage_7d_in_currency"),
                }
            }
        })
    return mapped


def get_btc_dominance():
    """
    GRATUITO: CoinGecko /global -> calcula dominância BTC (%)
    """
    try:
        url = "https://api.coingecko.com/api/v3/global"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        # CoinGecko retorna percentuais por moeda em data.market_cap_percentage
        btc_dom = data["data"]["market_cap_percentage"].get("btc")
        return float(btc_dom) if btc_dom is not None else None
    except Exception:
        return None


def get_fear_greed_index():
    """
    GRATUITO: Alternative.me Fear & Greed Index (proxy gratuito do índice de 'ganância')
    """
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=15)
        r.raise_for_status()
        d = r.json()
        v = int(d["data"][0]["value"])
        cls = d["data"][0]["value_classification"]
        return v, cls
    except Exception:
        return None, None


def get_coinglass_altcoin_season_index():
    """
    Preferencial (mais confiável) – CoinGlass Altcoin Season Index.
    - Se COINGLASS_API_KEY existir: usa endpoint oficial gratuito.
    - Caso contrário: tenta fallback por scraping do HTML (best effort).
    """
    # 1) Tenta API oficial (requer key gratuita)
    if COINGLASS_API_KEY:
        try:
            url = "https://open-api-v4.coinglass.com/api/index/altcoin-season"
            headers = {
                "Authorization": f"Bearer {COINGLASS_API_KEY}",
                "accept": "application/json",
            }
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            payload = r.json()
            data = payload.get("data") or []
            if data:
                # Em geral o último é o mais recente
                return float(data[-1].get("altcoin_index", 0))
        except Exception:
            pass

    # 2) Fallback: tentar extrair do HTML público (pode falhar conforme mudanças do site)
    try:
        url = "https://www.coinglass.com/pt/pro/i/alt-coin-season"
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text

        # Alguns sites SPA embutem JSON em <script> tipo __NEXT_DATA__ / window.__INITIAL_STATE__
        # Tentativa genérica:
        m = re.search(r'__NEXT_DATA__" type="application/json">(.+?)</script>', html)
        if m:
            app_json = json.loads(m.group(1))
            # A estrutura pode mudar. Tente localizar 'altcoin' em qualquer parte
            # Procura recursiva simples:
            def deep_find(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if "altcoin" in k.lower() and isinstance(v, (list, dict)):
                            return v
                        found = deep_find(v)
                        if found is not None:
                            return found
                elif isinstance(obj, list):
                    for it in obj:
                        found = deep_find(it)
                        if found is not None:
                            return found
                return None

            maybe = deep_find(app_json)
            # Se for lista de pontos, pega último valor numérico
            if isinstance(maybe, list) and maybe:
                last = maybe[-1]
                # Tenta extrair valor se for dict/tuple
                if isinstance(last, dict):
                    for val in last.values():
                        if isinstance(val, (int, float)):
                            return float(val)
                elif isinstance(last, (list, tuple)):
                    for val in last[::-1]:
                        if isinstance(val, (int, float)):
                            return float(val)
            # Como fallback, procura qualquer número percentual próximo ao termo "Altcoin"
            nums = re.findall(r'(\d{1,3}(?:\.\d+)?)\s*%?', html)
            if nums:
                # isso é bem heurístico; retorna o maior em 0..100
                candidates = [float(x) for x in nums if 0 <= float(x) <= 100]
                if candidates:
                    return max(candidates)
    except Exception:
        pass

    return None


# ---------- ITENS "CMC CHARTS" (GRATUITOS, BEST EFFORT) ----------

def _extract_next_data(url):
    """Tenta extrair JSON __NEXT_DATA__ das páginas públicas do CMC (gratuito)."""
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
        m = re.search(r'__NEXT_DATA__" type="application/json">(.+?)</script>', html)
        if not m:
            return None
        return json.loads(m.group(1))
    except Exception:
        return None


def get_cmc_altcoin_season_index():
    """Altcoin Season Index via página pública do CMC (best effort)."""
    data = _extract_next_data("https://coinmarketcap.com/pt-br/charts/altcoin-season-index/")
    if not data:
        return None
    # Estruturas do CMC mudam; tentamos localizar qualquer série relevante
    def deep_numbers(obj):
        out = []
        if isinstance(obj, dict):
            for v in obj.values():
                out.extend(deep_numbers(v))
        elif isinstance(obj, list):
            for it in obj:
                out.extend(deep_numbers(it))
        else:
            if isinstance(obj, (int, float)):
                out.append(float(obj))
        return out

    nums = deep_numbers(data)
    # Se houver muitos números, um heurístico: usar últimos valores em faixa 0..100
    vals = [x for x in nums if 0 <= x <= 100]
    if vals:
        return vals[-1]
    return None


def get_cmc_market_cycle_marker():
    """Market Cycle Indicators via página pública do CMC (best effort)."""
    data = _extract_next_data("https://coinmarketcap.com/pt-br/charts/crypto-market-cycle-indicators/")
    if not data:
        return None
    # Heurística semelhante
    def deep_pairs(obj):
        # retorna lista de números 'marcadores' 0..100
        out = []
        if isinstance(obj, dict):
            for v in obj.values():
                out.extend(deep_pairs(v))
        elif isinstance(obj, list):
            for it in obj:
                out.extend(deep_pairs(it))
        else:
            if isinstance(obj, (int, float)) and 0 <= obj <= 100:
                out.append(float(obj))
        return out

    vals = deep_pairs(data)
    return vals[-1] if vals else None


def get_cmc100_index_level():
    """CMC100 Index via página pública do CMC (best effort). Retorna o último valor numérico encontrado."""
    data = _extract_next_data("https://coinmarketcap.com/pt-br/charts/cmc100/")
    if not data:
        return None
    # Busca heurística por valores grandes (índice costuma ser > 100)
    def deep_big_numbers(obj):
        out = []
        if isinstance(obj, dict):
            for v in obj.values():
                out.extend(deep_big_numbers(v))
        elif isinstance(obj, list):
            for it in obj:
                out.extend(deep_big_numbers(it))
        else:
            if isinstance(obj, (int, float)) and obj > 10:  # filtro mínimo
                out.append(float(obj))
        return out

    vals = deep_big_numbers(data)
    return vals[-1] if vals else None


# ---------- GERAÇÃO DO RELATÓRIO ----------

def generate_report():
    # 1) Dados de mercado (gratuito / estável)
    data = fetch_market_data()
    btc = next((coin for coin in data if coin["symbol"] == "BTC"), None)

    # 2) Classificação dinâmica por market cap (usa seus helpers)
    altcoins = [c for c in data if c["symbol"] != "BTC"]
    blue, mid, low = classify_altcoins(altcoins)

    # 3) Indicadores (gratuitos + best effort)
    fear_greed_val, fear_greed_text = get_fear_greed_index()             # Alternative.me
    alt_season_cmc = get_cmc_altcoin_season_index()                      # CMC (scrape best effort)
    alt_season_coinglass = get_coinglass_altcoin_season_index()          # CoinGlass (API grátis se key)
    market_cycle = get_cmc_market_cycle_marker()                          # CMC (scrape best effort)
    btc_dom = get_btc_dominance()                                        # CoinGecko /global
    cmc100_level = get_cmc100_index_level()                               # CMC (scrape best effort)

    # 4) Métricas BTC
    if btc:
        btc_price = btc["quote"]["USD"]["price"]
        btc_percent_change = btc["quote"]["USD"]["percent_change_24h"]
    else:
        btc_price = None
        btc_percent_change = None

    # 5) Regras simples de recomendação
    #    - Se Altcoin Season (CoinGlass) > 75 → foco em altcoins; se < 25 → foco em BTC
    #    - Se Fear&Greed >= 75 (ganância extrema) → cautela
    btc_recommendation = "Aguardar"
    if alt_season_coinglass is not None:
        if alt_season_coinglass < 25:
            btc_recommendation = "✅ Comprar BTC"
        elif alt_season_coinglass > 75:
            btc_recommendation = "⚠️ Preferir Altcoins / Reduzir BTC"
        else:
            btc_recommendation = "⚖️ Neutro / Diversificar"
    else:
        # Fallback se não houver índice da CoinGlass
        if btc_percent_change is not None and btc_percent_change > -1:
            btc_recommendation = "✅ Comprar BTC"
        else:
            btc_recommendation = "⚖️ Neutro / Diversificar"

    # 6) Montagem do relatório
    msg = f"📊 *Relatório Diário - {datetime.now().strftime('%d/%m/%Y')}*\n\n"

    # BTC
    msg += "💰 *Bitcoin*\n"
    if btc_price is not None:
        msg += f"Preço: ${btc_price:,.2f}\n"
    if btc_percent_change is not None:
        msg += f"Variação 24h: {btc_percent_change:.2f}%\n"
    msg += f"Dominância BTC (CG): {btc_dom:.2f}%\n" if btc_dom is not None else ""
    msg += f"Recomendação: {btc_recommendation}\n\n"

    # Índices
    msg += "📈 *Índices de Mercado*\n"
    if fear_greed_val is not None:
        msg += f"- Fear & Greed (Alt.me): {fear_greed_val} ({fear_greed_text})\n"
    if alt_season_cmc is not None:
        msg += f"- Altcoin Season (CMC): {alt_season_cmc:.2f}\n"
    if alt_season_coinglass is not None:
        msg += f"- Altcoin Season (CoinGlass): {alt_season_coinglass:.2f}\n"
    if market_cycle is not None:
        msg += f"- Market Cycle (CMC): {market_cycle:.2f}\n"
    if cmc100_level is not None:
        msg += f"- CMC100 Index (CMC): {cmc100_level:.2f}\n"
    msg += "\n"

    # Top lists
    def top_summary(title, coins):
        coins = sorted(coins, key=lambda x: x["market_cap"], reverse=True)[:5]
        return f"*{title}:*\n" + "\n".join(
            [f"{c['symbol']} (${c['price']:.2f}) - MC: {c['market_cap']/1e9:.2f}B" for c in coins]
        ) + "\n"

    msg += top_summary("🔵 Bluechips", blue)
    msg += top_summary("🟠 Médio porte", mid)
    msg += top_summary("🔴 Lowcaps", low)

    # Diversificação
    msg += "\n📦 *Diversificação sugerida:*\n"
    msg += diversification_strategy(len(blue), len(mid), len(low))

    return msg
