import os
import requests
import telegram
import pandas as pd
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis do .env
load_dotenv()

# Configuração compatível com várias versões
try:
    # Para versões mais recentes (v20+)
    from telegram import Bot
    from telegram.ext import Application, CommandHandler
    from telegram.constants import ParseMode
    NEW_VERSION = True
except ImportError:
    # Fallback para versões mais antigas (v13.x)
    from telegram import Bot, ParseMode
    from telegram.ext import Updater, CommandHandler
    NEW_VERSION = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ALTCOINS = os.getenv("ALTCOINS").split(',')

bot = Bot(token=TELEGRAM_TOKEN)
HISTORICO = []

# Categorias de altcoins (exemplo base, ideal manter atualizado)
CATEGORIAS = {
    'bluechip': ['ETH', 'BNB', 'ADA'],
    'medio_porte': ['MATIC', 'LINK', 'ATOM'],
    'emergente': ['INJ', 'RNDR', 'PYTH']
}

def obter_dados_mercado():
    dados = []
    for moeda in ALTCOINS:
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{moeda.lower()}"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()  # Verifica erros HTTP
            info = r.json()
            
            # Verifica se a resposta contém os dados esperados
            if 'market_data' not in info:
                print(f"Dados incompletos para {moeda}")
                continue
                
            preco = info['market_data']['current_price']['usd']
            volume = info['market_data']['total_volume']['usd']
            dominancia = info.get('market_cap_rank', 999)
            variacao_24h = info['market_data']['price_change_percentage_24h']
            
            dados.append({
                'moeda': moeda.upper(),
                'preco': preco,
                'volume': volume,
                'dominancia_rank': dominancia,
                'variacao_24h': variacao_24h
            })
        except Exception as e:
            print(f"Erro ao obter dados para {moeda}: {str(e)}")
            continue
    return dados

def analisar_momento_compra(dados):
    try:
        # Obter preço do Bitcoin primeiro
        btc_response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
            timeout=5
        )
        btc_response.raise_for_status()
        preco_btc = btc_response.json()['bitcoin']['usd']
        
        compra_btc = preco_btc < 45000  # Exemplo de oportunidade
        compra_alt = []
        venda_alt = []

        for d in dados:
            if not isinstance(d, dict):
                continue
                
            try:
                # Compra: bom volume e variação positiva
                if d.get('variacao_24h', 0) > 1 and d.get('volume', 0) > 10_000_000:
                    compra_alt.append(d)
                # Venda: baixa variação ou volume
                if d.get('variacao_24h', 0) < -2 or d.get('volume', 0) < 3_000_000 or d.get('dominancia_rank', 999) > 100:
                    venda_alt.append(d)
            except Exception as e:
                print(f"Erro ao analisar {d.get('moeda', 'unknown')}: {e}")

        return compra_btc, compra_alt, venda_alt, preco_btc
        
    except Exception as e:
        print(f"Erro na análise de momento de compra: {e}")
        return False, [], [], 0  # Retorna valores padrão em caso de erro

def classificar_altcoins(lista):
    classificadas = { 'bluechip': [], 'medio_porte': [], 'emergente': [] }
    for alt in lista:
        for cat, nomes in CATEGORIAS.items():
            if alt['moeda'] in nomes:
                classificadas[cat].append(alt)
    return classificadas

def estrategia_diversificacao():
    return {
        'bitcoin': '50%',
        'altcoins_bluechip': '25%',
        'altcoins_medio_porte': '15%',
        'altcoins_emergentes': '10%'
    }

def gerar_relatorio():
    try:
        dados = obter_dados_mercado()
        compra_btc, compra_alt, venda_alt, preco_btc = analisar_momento_compra(dados)
        alt_class = classificar_altcoins(compra_alt)
        diversificacao = estrategia_diversificacao()

        msg = f"\U0001F4B0 *Alerta Cripto Diário* ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n"
        msg += f"*Bitcoin:* ${preco_btc:.2f}\n"
        msg += "\n*Recomendação:* " + ("Comprar" if compra_btc else "Aguardar") + "\n"

        msg += "\n*Altcoins recomendadas para compra:*\n"
        for cat, alts in alt_class.items():
            if alts:
                msg += f"\n_{cat.title().replace('_', ' ')}:_\n"
                for alt in alts:
                    msg += f"- {alt['moeda']}: ${alt['preco']:.2f}, +{alt['variacao_24h']:.2f}%\n"

        if venda_alt:
            msg += "\n*Altcoins sugeridas para venda:*\n"
            for alt in venda_alt:
                msg += f"- {alt['moeda']}: {alt['variacao_24h']:.2f}%  | Volume: ${alt['volume']:.2f}\n"

        msg += "\n*Estratégia Sugerida:*\n"
        for k, v in diversificacao.items():
            msg += f"- {k.replace('_', ' ').title()}: {v}\n"

        df = pd.DataFrame(dados)
        nome_arquivo = f"historico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(nome_arquivo, index=False)

        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
        with open(nome_arquivo, 'rb') as f:
            bot.send_document(chat_id=TELEGRAM_CHAT_ID, document=f)
    except Exception as e:
        print(f"Erro ao gerar relatório: {e}")
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="❌ Ocorreu um erro ao gerar o relatório.")

def comando_analise(update, context):
    gerar_relatorio()
    update.message.reply_text("Análise enviada com sucesso!")

def main():
    try:
        if NEW_VERSION:
            # Configuração para v20+
            application = Application.builder().token(TELEGRAM_TOKEN).build()
            application.add_handler(CommandHandler("analisar", comando_analise))
            
            print("Bot iniciado (v20+)...")
            application.run_polling()
        else:
            # Configuração para v13.x
            updater = Updater(TELEGRAM_TOKEN)
            dp = updater.dispatcher
            dp.add_handler(CommandHandler("analisar", comando_analise))
            
            print("Bot iniciado (v13.x)...")
            updater.start_polling()
        
        # Loop para o agendador
        while True:
            schedule.run_pending()
            time.sleep(10)
            
    except Exception as e:
        print(f"Erro ao iniciar o bot: {e}")

if __name__ == "__main__":
    main()