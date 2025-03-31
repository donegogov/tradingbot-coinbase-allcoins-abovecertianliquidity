
import ccxt
import pandas as pd
import time
import threading
from datetime import datetime
from pathlib import Path  # ✅ THIS LINE IS NEEDED

symbol = 'LUNA/USDT'
min_profit_threshold = 0.03  # USDT
trade_usdt = 100
csv_file = '100-no-trading-with-fees_luna_arbitrage_opportunities.csv'

exchange_ids = [
    'binance', 'bybit', 'okx', 'bitget', 'mexc', 'gateio', 'kucoin',
    'crypto_com', 'bingx', 'kraken', 'huobi', 'bitmart', 'lbank',
    'xt', 'tokocrypto', 'biconomy', 'btcturk', 'deepcoin', 'hotcoin',
    'btse', 'digifinex', 'orangex', 'coinw', 'bitkan', 'phemex', 'tapbit',
    'bitvavo', 'kcex', 'pionex', 'whitebit', 'coindcx', 'bitrue', 'latoken',
    'osmosis', 'weex', 'onuspro', 'novadax', 'poloniex', 'bit', 'kujrafin',
    'bitexen', 'zke', 'uzxx', 'bitmarkets', 'hibt', 'bydfi', 'coincatch',
    'bibox', 'bigone', 'indodax', 'changenow', 'bitlo', 'ripio', 'bitcoiva'
]

default_fee = 0.001  # 0.1%

known_fees = {
    'binance': 0.00075,
    'bybit': 0.001,
    'kucoin': 0.001,
    'latoken': 0.0049,
    'bitmart': 0.0025,
    'mexc': 0.001,
}

def fetch_ticker(ex_id, tickers):
    try:
        ex = getattr(ccxt, ex_id)({'enableRateLimit': True})
        markets = ex.load_markets()
        if symbol in markets:
            ticker = ex.fetch_ticker(symbol)
            tickers[ex_id] = {
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'fee': known_fees.get(ex_id, default_fee)
            }
    except Exception:
        pass

def run_check():
    while True:
        tickers = {}
        threads = []

        for ex_id in exchange_ids:
            t = threading.Thread(target=fetch_ticker, args=(ex_id, tickers))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        opportunities = []
        for buy_ex in tickers:
            for sell_ex in tickers:
                if buy_ex == sell_ex:
                    continue
                buy_price = tickers[buy_ex]['ask']
                sell_price = tickers[sell_ex]['bid']
                if not buy_price or not sell_price:
                    continue

                buy_fee = tickers[buy_ex]['fee']
                sell_fee = tickers[sell_ex]['fee']

                qty_luna = trade_usdt / buy_price
                #cost = trade_usdt * (1 + buy_fee)
                #revenue = qty_luna * sell_price * (1 - sell_fee)
                cost = trade_usdt
                revenue = qty_luna * sell_price 
                profit = revenue - cost

                if profit > min_profit_threshold:
                    print(f"[{datetime.utcnow().isoformat()}] 🚀 {buy_ex} → {sell_ex} | buy price {buy_price} - sell price {sell_price} | Profit: {profit:.4f} USDT")

                opportunities.append({
                    'timestamp': datetime.utcnow().isoformat(),
                    'buy_from': buy_ex,
                    'sell_to': sell_ex,
                    'buy_price': round(buy_price, 6),
                    'sell_price': round(sell_price, 6),
                    'buy_fee': buy_fee,
                    'sell_fee': sell_fee,
                    'qty_luna': round(qty_luna, 4),
                    'profit': round(profit, 4)
                })

        df = pd.DataFrame(opportunities)
        df.to_csv(csv_file, mode='a', index=False, header=not Path(csv_file).exists())
        print(f"✅ Check completed. Sleeping for 10 seconds...")

        time.sleep(10)

if __name__ == '__main__':
    run_check()
