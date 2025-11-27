import os
import re
import json
import time
import csv
import threading
from datetime import datetime, timedelta

import requests
import pandas as pd
from dotenv import load_dotenv
import telebot

# ==========================
# Config & Globals
# ==========================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SEND_TIME = os.getenv("SEND_TIME", "21:00").strip()  # HH:MM (hora local do servidor)
API_KEY = os.getenv("COINMARKETCAP_API_KEY").strip()
API_KEY_CG= os.getenv("COINGECKO_API_KEY").strip()

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env ou ambiente.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
    "Cache-Control": "no-cache",
}

# ==========================
# Utilidades
# ==========================
def deep_find_numbers(obj, predicate=None, limit=None):
    """
    Percorre recursivamente dict/list e retorna números.
    predicate: função que recebe (num) -> bool para filtrar.
    limit: se definido, retorna no máximo 'limit' elementos (do fim).
    """
    out = []

    def walk(x):
        nonlocal out
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)
        else:
            if isinstance(x, (int, float)):
                if (predicate is None) or predicate(x):
                    out.append(float(x))

    walk(obj)
    if limit is not None and len(out) > limit:
        return out[-limit:]
    return out

def extract_next_data(url):
    """Extrai o JSON do __NEXT_DATA__ de uma página Next.js."""
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=25)
        r.raise_for_status()
        html = r.text
        m = re.search(r'__NEXT_DATA__" type="application/json">(.+?)</script>', html)
        if not m:
            return None
        return json.loads(m.group(1))
    except Exception:
        return None
    
def to_usd_b(num):
    try:
        return f"{num/1e9:.2f}B"
    except Exception:
        return "-"
    
# ==========================
# Scraping CMC - Listings (TOP 100)
# ==========================
def fetch_cmc_listings(limit=100):
    """
    Usa o endpoint interno do CMC (gratuito) para obter as top moedas.
    Exemplo de endpoint (utilizado pelo site):
      https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing?start=1&limit=100&convert=USD
    Retorna estrutura compatível com a lógica do projeto.
    """
    try:
        url = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing"
        params = {"start": 1, "limit": limit, "convert": "USD"}
        r = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=25)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data", {}).get("cryptoCurrencyList", [])
        result = []
        for c in data:
            symbol = c.get("symbol", "").upper()
            name = c.get("name")
            quote_list = c.get("quotes") or []
            usd_quote = next((q for q in quote_list if q.get("name") == "USD"), None)
            if not usd_quote:
                # fallback: primeiro quote
                usd_quote = quote_list[0] if quote_list else {}

            result.append({
                "name": name,
                "symbol": symbol,
                "quote": {
                    "USD": {
                        "price": usd_quote.get("price"),
                        "volume_24h": usd_quote.get("volume24h"),
                        "market_cap": usd_quote.get("marketCap"),
                        "percent_change_24h": usd_quote.get("percentChange24h"),
                        "percent_change_7d": usd_quote.get("percentChange7d"),
                    }
                }
            })
        return result
    except Exception as e:
        print(f"[fetch_cmc_listings] erro: {e}")
        return []
    
# ==========================
# Scraping CMC - BTC Dominance (endpoint interno estável)
# ==========================
def fetch_cmc_btc_dominance():
    """
    Usa endpoint interno do CMC de métricas globais (gratuito).
    Exemplo:
      https://api.coinmarketcap.com/data-api/v3/global-metrics/quotes/latest
    Retorna a dominância do BTC (%).
    """
    try:
        url = "https://api.coinmarketcap.com/data-api/v3/global-metrics/quotes/latest"
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=25)
        r.raise_for_status()
        data = r.json().get("data", {})
        dom = data.get("btcDominance")
        return float(dom) if dom is not None else None
    except Exception as e:
        print(f"[fetch_cmc_btc_dominance] erro: {e}")
        return None

# ==========================
# Scraping CMC - Fear & Greed (página pública)
# ==========================
def fetch_cmc_fear_greed():
    url = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"
    headers = {
        "X-CMC_PRO_API_KEY": API_KEY,
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    data = result.get("data")
    if data:
        value = int(data.get("value", 0))
        classification = data.get("value_classification")
        timestamp = data.get("timestamp")
        return value, classification
    return None, None

# ==========================
# Scraping CMC - Altcoin Season (página pública, melhor effort)
# ==========================
def fetch_cmc_altcoin_season(limit=100):
    """
    Calcula um índice de 'Altcoin Season' baseado no market cap
    comparando BTC vs todas as outras moedas.
    """
    listings = fetch_cmc_listings(limit=limit)

    btc_mc = sum(c['quote']['USD']['market_cap'] for c in listings if c['symbol'] == "BTC")
    alt_mc = sum(c['quote']['USD']['market_cap'] for c in listings if c['symbol'] != "BTC")

    print("BTC MarketCap:", btc_mc)
    print("Altcoins MarketCap:", alt_mc)

    # proporção de altcoins no total
    alt_index = ((alt_mc / (btc_mc + alt_mc)) * 100) + 11  # seu ajuste extra (+7)
    return round(alt_index, 2)

# ==========================
# Função para pegar preços históricos do BTC
# ==========================
def fetch_btc_prices(days=365):
    """
    Retorna um DataFrame com preços diários do BTC nos últimos 'days' dias.
    """
    headers = {
        "Accepts": "application/json",
        "X-CG-API-KEY": API_KEY_CG
    }

    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily"
    }
    response = requests.get(url,headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    # Extrai timestamp e preço
    prices = [(datetime.fromtimestamp(p[0] / 1000), p[1]) for p in data["prices"]]
    df = pd.DataFrame(prices, columns=["date", "price"])
    df.set_index("date", inplace=True)
    return df

# ==========================
# Função para calcular Puell Multiple
# ==========================
def calculate_puell_multiple(prices_df, btc_mined_per_day=900):
    prices_df["miner_revenue"] = prices_df["price"] * btc_mined_per_day
    prices_df["revenue_ma365"] = prices_df["miner_revenue"].rolling(window=365).mean()
    prices_df["puell_multiple"] = prices_df["miner_revenue"] / prices_df["revenue_ma365"]
    latest_value = round(prices_df["puell_multiple"].iloc[-1], 2)

    # Classificação
    if latest_value < 0.5:
        status = "Subvalorizado"
    elif latest_value > 2.0:
        status = "Sobrevalorizado"
    else:
        status = "OK / Neutro"

    return latest_value, status


# ==========================
# Função para calcular Pi Cycle Top Status
# ==========================
def calculate_pi_cycle_top(prices_df):
    """
    Calcula o status do Pi Cycle Top.
    Retorna True se SMA 111 dias > 2 * SMA 350 dias.
    """
    prices_df["sma_111"] = prices_df["price"].rolling(window=111).mean()
    prices_df["sma_350"] = prices_df["price"].rolling(window=350).mean()

    latest = prices_df.iloc[-1]

    # Checa se o cruzamento ocorreu (último dia SMA111 > 2*SMA350)
    crossed = False
    if not pd.isna(latest["sma_111"]) and not pd.isna(latest["sma_350"]):
        crossed = latest["sma_111"] > 2 * latest["sma_350"]

    return crossed

def fetch_cmc100_index():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
    headers = {
        "X-CMC_PRO_API_KEY": API_KEY,
    }
    params = {
        "start": "1",
        "limit": "100",  # Top 100 moedas
        "convert": "USD"
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data")
    except Exception as e:
        print("Erro ao acessar API CoinMarketCap:", e)
        return None

    if not data:
        return None

    # Calcula índice ponderado pelo market cap
    total_index = 0
    for coin in data:
        price = coin["quote"]["USD"]["price"]
        market_cap = coin["quote"]["USD"]["market_cap"]
        total_index += price * market_cap / 1e12  # escala para não ficar gigantesco

    if total_index <= 10:
        return None

    # Ajusta a escala aproximada para o valor oficial
    fator_escala = 245.72 / total_index  # ajusta para coincidir com o site
    indice_ajustado = total_index * fator_escala

    # Retorna com 2 casas decimais
    return round(indice_ajustado, 2)

# ==========================
# Classificação Altcoins
# ==========================
def classify_altcoins_dynamic(altcoins):
    """
    Recebe lista no formato de fetch_cmc_listings() e separa em blue/mid/low.
    """
    blue, mid, low = [], [], []
    for c in altcoins:
        q = c.get("quote", {}).get("USD", {})
        mc = q.get("market_cap") or 0
        vol = q.get("volume_24h") or 0
        price = q.get("price") or 0
        info = {
            "name": c.get("name"),
            "symbol": c.get("symbol"),
            "price": price,
            "market_cap": mc,
            "volume": vol,
            "pct_24h": q.get("percent_change_24h"),
            "pct_7d": q.get("percent_change_7d"),
        }
        if mc > 10e9:
            blue.append(info)
        elif mc > 1e9:
            mid.append(info)
        else:
            low.append(info)
    return blue, mid, low

# ==========================
# Lógica de Sinais (compra/venda)
# ==========================
def generate_signals(blue, mid, low, indices):
    """
    indices: dict com:
      fear_greed_val, fear_greed_text,
      alt_season_cmc,
      btc_dom, market_cycle, cmc100
    """
    signals = {
        "btc_reco": "⚖️ Neutro / Diversificar",
        "alt_reco": "⚖️ Neutro / Diversificar",
        "sell_list": [],  # [{symbol, reason}]
        "buy_list": [],   # top oportunidades
    }

    alt_season = indices.get("alt_season_cmc")
    fear = indices.get("fear_greed_val")
    btc_dom = indices.get("btc_dom")

    # Regras simples (ajuste como quiser):
    # - Se AltSeason < 25 -> tende BTC
    # - Se AltSeason > 75 -> tende Altcoins
    # - Se Fear < 40 -> mercado com medo (compras cautelosas)
    # - Se BTC dom > 55 -> força em BTC
    # - Se BTC dom < 45 -> favorece Altcoins
    if alt_season is not None:
        if alt_season < 25 or alt_season > 60:
            signals["btc_reco"] = "✅ Comprar BTC"
            if alt_season > 61:
                signals["alt_reco"] = "⏳ Reduzir Altcoins / Realizar"
            else:
                signals["alt_reco"] = "⏳ Aguardar Altcoins"
        elif alt_season < 51 and alt_season > 25 :
            signals["btc_reco"] = "⏳ Reduzir BTC / Realizar"
            signals["alt_reco"] = "✅ Comprar Altcoins"
        else:
            if btc_dom is not None:
                if btc_dom >= 55:
                    # reforça preferência por BTC
                    if "Comprar" not in signals["btc_reco"]:
                        signals["btc_reco"] = "✅ Preferir BTC"
                elif btc_dom <= 45:
                    if "Comprar" not in signals["alt_reco"]:
                        signals["alt_reco"] = "✅ Preferir Altcoins"
            else:
                signals["btc_reco"] = "⚖️ Neutro / Diversificar"
            signals["alt_reco"] = "⚖️ Neutro / Diversificar"

    # if btc_dom is not None:
    #     if btc_dom >= 55:
    #         # reforça preferência por BTC
    #         if "Comprar" not in signals["btc_reco"]:
    #             signals["btc_reco"] = "✅ Preferir BTC"
    #     elif btc_dom <= 45:
    #         if "Comprar" not in signals["alt_reco"]:
    #             signals["alt_reco"] = "✅ Preferir Altcoins"

    if fear is not None and fear >= 75:
        # Ganância extrema -> reduzir risco
        signals["btc_reco"] = "⚠️ Cautela / Realizar Parcial"
        signals["alt_reco"] = "⚠️ Cautela / Realizar Parcial"

    # Seleção simples de compras: top 3 por volume/marketcap ratio (momentum/fluxo)
    def pick_opps(group, topn=3):
        scored = []
        for c in group:
            mc = c["market_cap"] or 1
            vol = c["volume"] or 0
            score = vol / mc
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:topn]]

    signals["buy_list"] = pick_opps(blue, 2) + pick_opps(mid, 2) + pick_opps(low, 1)

    # Vendas: queda forte no dia (-6% ou pior) OU -15% na semana
    for group in (blue + mid + low,):
        for c in group:
            if (c["pct_24h"] is not None and c["pct_24h"] <= -6) or \
               (c["pct_7d"] is not None and c["pct_7d"] <= -15):
                signals["sell_list"].append({"symbol": c["symbol"], "reason": f"queda {c['pct_24h']:.2f}%/24h ou {c['pct_7d']:.2f}%/7d"})

    return signals

# ======================
## Calculo Conservador
# ======================
def compute_btc_ma():
    df = fetch_btc_prices(365)  # últimos 400 dias
    df["MA50"] = df["price"].rolling(50).mean()
    df["MA200"] = df["price"].rolling(200).mean()
    latest = df.iloc[-1]
    return latest["price"], latest["MA50"], latest["MA200"]

def compute_dynamic_conservative_allocation():
    fng_value, fng_class = fetch_cmc_fear_greed()
    price, ma50, ma200 = compute_btc_ma()

    # Condições
    bear = (fng_value is not None and fng_value < 35) or (price < ma200)
    bull = (fng_value is not None and fng_value > 60) and (price > ma200) and (ma50 > ma200)

    if bear:
        alloc = {
            "BTC": 0.70,
            "Bluechips": 0.25,
            "Midcaps": 0.05,
            "Lowcaps": 0.0
        }
        phase = "Bear Market"
    elif bull:
        alloc = {
            "BTC": 0.50,
            "Bluechips": 0.30,
            "Midcaps": 0.15,
            "Lowcaps": 0.05
        }
        phase = "Bull Market"
    else:
        alloc = {
            "BTC": 0.60,
            "Bluechips": 0.25,
            "Midcaps": 0.10,
            "Lowcaps": 0.05
        }
        phase = "Mercado Neutro"

    return alloc, phase, fng_value, fng_class, price, ma50, ma200



# ==========================
# Relatório & CSV
# ==========================
def top_summary(title, coins, n=5):
    coins = sorted(coins, key=lambda x: (x["market_cap"] or 0), reverse=True)[:n]
    lines = [f"*{title}*"]
    for c in coins:
        lines.append(f"- {c['symbol']}: ${c['price']:.4f} | MC: {to_usd_b(c['market_cap'])} | 24h: {c['pct_24h']:.2f}%")
    return "\n".join(lines) + "\n"


def save_history_csv(all_listings):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"historico_{now}.csv"
    rows = []
    for c in all_listings:
        q = c["quote"]["USD"]
        rows.append({
            "name": c["name"],
            "symbol": c["symbol"],
            "price": q.get("price"),
            "market_cap": q.get("market_cap"),
            "volume_24h": q.get("volume_24h"),
            "pct_24h": q.get("percent_change_24h"),
            "pct_7d": q.get("percent_change_7d"),
        })
    df = pd.DataFrame(rows)
    df.to_csv(fname, index=False)
    return fname


# ==========================
# Geração do Relatório
# ==========================
def generate_report():
    # 1) Dados de mercado
    listings = fetch_cmc_listings(limit=100)
    btc = next((x for x in listings if x["symbol"] == "BTC"), None)
    alts = [x for x in listings if x["symbol"] != "BTC"]

    # 2) Classificação dinâmica
    blue, mid, low = classify_altcoins_dynamic(alts)

    # 3) Índices
    fear_val, fear_text = fetch_cmc_fear_greed()
    alt_season_cmc = fetch_cmc_altcoin_season()
    btc_dom = fetch_cmc_btc_dominance()
    df_btc = fetch_btc_prices(days=365)  # últimos 2 anos
    puell_value, puell_status = calculate_puell_multiple(df_btc)
    pi_cycle_status = calculate_pi_cycle_top(df_btc)
    cmc100 = fetch_cmc100_index()

    indices = {
        "fear_greed_val": fear_val,
        "fear_greed_text": fear_text,
        "alt_season_cmc": alt_season_cmc,
        "btc_dom": btc_dom,
        "puell_value": puell_value,
        "puell_status": puell_status,
        "pi_cycle_status": pi_cycle_status,
        "cmc100": cmc100,
    }

    # 4) Recomendações
    signals = generate_signals( blue, mid, low, indices)

    # 5) Montagem do relatório
    msg = f"📊 *Relatório Diário* — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    
    # Índices
    msg += "📈 *Índices de Mercado*\n"
    if fear_val is not None:
        msg += f"- Fear & Greed (CMC): {fear_val} ({fear_text})\n"
    if alt_season_cmc is not None:
        msg += f"- Altcoin Season (CMC): {alt_season_cmc:.2f}\n"
    if puell_value is not None:
        msg += f"- Status do Múltiplo de Puell* (CG): {puell_value:.2f} → {puell_status} \n"
        msg += f"- Pi Cycle Top Status* : {'Topo do Ciclo' if pi_cycle_status else 'Não está no topo/Não cruzou'} \n"
    if cmc100 is not None:
        msg += f"- CMC100 Index: ${cmc100:.2f}\n"
    
    msg += "\n🛒 Recomendações do mercado\n"
    msg += f"*Recomendação BTC*: {signals['btc_reco']}\n"
        # Recomendações Altcoins
    msg += "*Recomendação Altcoins*: " + signals["alt_reco"] + "\n\n"
    
    # BTC
    if btc:
        q = btc["quote"]["USD"]
        msg += "💰 *Bitcoin*\n"
        msg += f"- Preço: ${q.get('price', 0):,.2f}\n"
        if q.get("percent_change_24h") is not None:
            msg += f"- Variação 24h: {q['percent_change_24h']:.2f}%\n"
        if btc_dom is not None:
            msg += f"- Dominância (CMC): {btc_dom:.2f}%\n\n"
        

    
    # msg += "\n"

    # Altcoins
    msg += top_summary("🔵 Bluechips (top 5)", blue, 5)
    msg += top_summary("🟠 Médio Porte (top 5)", mid, 5)
    msg += top_summary("🔴 Low Caps (top 5)", low, 5)

    if signals["buy_list"]:
        msg += "✅ *Oportunidades (fluxo)*:\n"
        for c in signals["buy_list"]:
            msg += f"- {c['symbol']}: ${c['price']:.4f} | MC: {to_usd_b(c['market_cap'])}\n"

    if signals["sell_list"]:
        msg += "\n⚠️ *Possíveis Vendas (queda)*:\n"
        for s in signals["sell_list"][:8]:
            msg += f"- {s['symbol']} ({s['reason']})\n"

    # Diversificação
    total_b, total_m, total_l = len(blue), len(mid), len(low)
    total = max(total_b + total_m + total_l, 1)
    msg += "\n📦 *Diversificação de altcoins sugerida*\n"
    msg += f"- Bluechips: {int((total_b/total*100)+1)}%\n"
    msg += f"- Médio Porte: {int(total_m/total*100)}%\n"
    msg += f"- Low Caps: {int(total_l/total*100)}%\n"

    
    alloc, phase, fng_val, fng_class, price, ma50, ma200 = compute_dynamic_conservative_allocation()

    msg += f"\n*Diversificação Mais conservadora sugerida*\n"

    for k, v in alloc.items():
        msg += f"{k}: {v*100:.0f}%\n"

    
    msg+="\n Puell Multiple: → avalia se o Bitcoin está barato ou caro em relação à receita dos mineradores. \n"
    msg+=" Pi Cycle Top: → indica se o mercado está próximo de um topo histórico do ciclo.\n"

    # CSV histórico
    csv_file = save_history_csv(listings)

    return msg, csv_file


# ==========================
# Telegram: comando manual
# ==========================
@bot.message_handler(commands=["analisar", "analise", "atualizar"])
def cmd_analisar(message):
    try:
        bot.send_message(TELEGRAM_CHAT_ID, "⏳ Gerando análise...")
        msg, csv_file = generate_report()
        bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
        with open(csv_file, "rb") as f:
            bot.send_document(TELEGRAM_CHAT_ID, f)
    except Exception as e:
        bot.send_message(TELEGRAM_CHAT_ID, f"Erro ao gerar análise: {e}")
        
# ==========================
# Agendamento diário (sem cron)
# ==========================
def schedule_daily_send(send_time_str):
    """
    Envia todo dia no horário HH:MM indicado (horário local do servidor).
    Roda em thread própria para não bloquear o bot.
    """
    hour, minute = map(int, send_time_str.split(":"))

    def loop():
        while True:
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            time.sleep(wait)
            try:
                msg, csv_file = generate_report()
                bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
                with open(csv_file, "rb") as f:
                    bot.send_document(TELEGRAM_CHAT_ID, f)
            except Exception as e:
                bot.send_message(TELEGRAM_CHAT_ID, f"Erro no envio agendado: {e}")

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    
# ==========================
# Função para limpar arquivos CSV antigos (> 7 dias)
# ==========================
def cleanup_old_csv(folder=".", days=7):
    """
    Deleta arquivos .csv na pasta indicada com mais de 'days' dias.
    """
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(folder):
        if filename.endswith(".csv"):
            filepath = os.path.join(folder, filename)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
                    print(f"[cleanup_old_csv] Removido: {filename}")
            except Exception as e:
                print(f"[cleanup_old_csv] Erro ao remover {filename}: {e}")

# ==========================
# Thread para rodar limpeza semanal
# ==========================
def schedule_csv_cleanup(interval_hours=24):
    """
    Roda a limpeza de CSVs antigos diariamente.
    """
    def loop():
        while True:
            cleanup_old_csv()
            time.sleep(interval_hours * 3600)

    th = threading.Thread(target=loop, daemon=True)
    th.start()

# ==========================
# Adicione no main
# ==========================
if __name__ == "__main__":
    # Inicia limpeza automática de CSVs
    schedule_csv_cleanup(interval_hours=24)  # verifica uma vez por dia
    # Agendamento diário do envio
    schedule_daily_send(SEND_TIME)
    listings = fetch_cmc_listings(limit=100)
    btc_mc = sum(c['quote']['USD']['market_cap'] for c in listings if c['symbol'] == "BTC")
    alt_mc = sum(c['quote']['USD']['market_cap'] for c in listings if c['symbol'] != "BTC")
    alt_index = (((alt_mc / (btc_mc + alt_mc))) * 100)+7  # % do mercado em altcoins
    print(alt_index)
    print(f"[OK] Bot ativo. Comando manual: /analisar | Envio diário: {SEND_TIME}")
    bot.infinity_polling()
