import ccxt
import threading
import time
from datetime import datetime
import pandas as pd

# === SETTINGS ===
symbol = 'LUNA/USDT'
trade_usdt = 500
fee_pct = 0.001  # 0.1% on both exchanges
min_profit_usdt = 0.01
sleep_seconds = 5
csv_file = 'new_real_luna_tron_arbitrage.csv'
exchanges_to_check = [
    'binance', 'bybit', 'okx', 'bitget', 'mexc', 'gateio', 'kucoin',
    'crypto_com', 'bingx', 'kraken', 'huobi', 'bitmart', 'lbank',
    'xt', 'tokocrypto', 'biconomy', 'btcturk', 'deepcoin', 'hotcoin',
    'btse', 'digifinex', 'orangex', 'coinw', 'bitkan', 'phemex', 'tapbit',
    'bitvavo', 'kcex', 'pionex', 'whitebit', 'coindcx', 'bitrue', 'latoken',
    'osmosis', 'weex', 'onuspro', 'novadax', 'poloniex', 'bit', 'kujrafin',
    'bitexen', 'zke', 'uzxx', 'bitmarkets', 'hibt', 'bydfi', 'coincatch',
    'bibox', 'bigone', 'indodax', 'changenow', 'bitlo', 'ripio', 'bitcoiva'
]

# === INIT EXCHANGES ===
exchanges = {}
for ex_id in exchanges_to_check:
    try:
        ex = getattr(ccxt, ex_id)({'enableRateLimit': True})
        if symbol in ex.load_markets():
            exchanges[ex_id] = ex
    except Exception as e:
        print(f"❌ Failed to load {ex_id}: {e}")

# === MAIN LOOP ===
while True:
    prices = {}

    def fetch(ex_id, ex_obj):
        try:
            orderbook = ex_obj.fetch_order_book(symbol)
            bid, bid_qty = orderbook['bids'][0]
            ask, ask_qty = orderbook['asks'][0]
            prices[ex_id] = {
                'bid': bid,
                'bid_qty': bid_qty,
                'ask': ask,
                'ask_qty': ask_qty,
            }
        except Exception as e:
            print(f"⚠️ Error fetching {ex_id}: {e}")

    # Parallel fetch
    threads = []
    for ex_id, ex in exchanges.items():
        t = threading.Thread(target=fetch, args=(ex_id, ex))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # Arbitrage Detection
    results = []
    for buy_ex in prices:
        for sell_ex in prices:
            if buy_ex == sell_ex:
                continue

            buy_price = prices[buy_ex]['ask']
            sell_price = prices[sell_ex]['bid']
            buy_qty = prices[buy_ex]['ask_qty']
            sell_qty = prices[sell_ex]['bid_qty']

            qty = trade_usdt / buy_price

            if qty > buy_qty or qty > sell_qty:
                continue  # Not enough liquidity

            # With fees
            cost = trade_usdt * (1 + fee_pct)
            revenue = sell_price * qty * (1 - fee_pct)
            profit = revenue - cost

            if profit >= min_profit_usdt:
                data = {
                    'Time': datetime.utcnow().isoformat(),
                    'Buy From': buy_ex,
                    'Buy Price': round(buy_price, 6),
                    'Sell To': sell_ex,
                    'Sell Price': round(sell_price, 6),
                    'Qty (LUNA)': round(qty, 4),
                    'Profit (USDT)': round(profit, 4)
                }
                results.append(data)
                print(f"\n🚀 Arbitrage Opportunity:")
                print(f"Buy {qty:.2f} LUNA @ {buy_price} on {buy_ex}")
                print(f"Sell @ {sell_price} on {sell_ex}")
                print(f"📈 Net Profit: {profit:.4f} USDT")

    # Log results
    if results:
        df = pd.DataFrame(results)
        try:
            df.to_csv(csv_file, mode='a', index=False, header=not pd.io.common.file_exists(csv_file))
        except Exception as e:
            print(f"⚠️ Failed to write CSV: {e}")

    print(f"⏱ Waiting {sleep_seconds} sec...\n")
    time.sleep(sleep_seconds)

