
import ccxt
import pandas as pd
import time
import threading
from datetime import datetime
from pathlib import Path  # ✅ THIS LINE IS NEEDED

symbol = 'LUNA/USDT'
min_profit_threshold = 0.01  # USDT
trade_usdt = 1000
csv_file = '1000_orderbook_trading_withdraw_luna_arbitrage_opportunities.csv'

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

def get_withdrawal_fees(exchange, coin):
    try:
        currencies = exchange.fetch_currencies()
        if coin in currencies:
            return float(currencies[coin].get("fee", 0))
    except:
        return 0
    return 0


def get_avg_price(orderbook_side, target_amount_usd, side='buy'):
    total_cost = 0
    total_qty = 0
    #print(side)
    for level in orderbook_side:
        if len(level) != 2:
            continue  # skip invalid entries
        price, qty = level
        #print(level)
        fill_value = price * qty
        if side == 'buy':
            if total_cost + fill_value >= target_amount_usd:
                needed_qty = (target_amount_usd - total_cost) / price
                total_qty += needed_qty
                total_cost += needed_qty * price
                break
            else:
                total_qty += qty
                total_cost += fill_value
        elif side == 'sell':
            if total_qty + qty >= target_amount_usd / price:
                needed_qty = (target_amount_usd / price) - total_qty
                total_cost += needed_qty * price
                total_qty += needed_qty
                break
            else:
                total_qty += qty
                total_cost += fill_value

    if total_qty == 0:
        return None
    return total_cost / total_qty


def fetch_ticker(ex_id, tickers):
    try:
        ex = getattr(ccxt, ex_id)({'enableRateLimit': True})
        markets = ex.load_markets()
        if symbol in markets:
            orderbook = ex.fetch_order_book(symbol)
            ask_price = get_avg_price(orderbook['asks'], trade_usdt, side='buy')
            bid_price = get_avg_price(orderbook['bids'], trade_usdt, side='sell')

            if ask_price and bid_price:
                luna_fee = get_withdrawal_fees(ex, 'LUNA')
                usdt_fee = get_withdrawal_fees(ex, 'USDT')
                tickers[ex_id] = {
                    'ask': ask_price,
                    'bid': bid_price,
                    'fee': known_fees.get(ex_id, default_fee),
                    'luna_withdraw': luna_fee,
                    'usdt_withdraw': usdt_fee
                }
    except Exception as e:
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
                luna_withdraw = tickers[buy_ex]['luna_withdraw']
                usdt_withdraw = tickers[sell_ex]['usdt_withdraw']

                luna_withdraw_in_usdt = luna_withdraw * sell_price  # receive side price
                cost = trade_usdt * (1 + buy_fee) + luna_withdraw_in_usdt
                revenue = qty_luna * sell_price * (1 - sell_fee) - usdt_withdraw
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
                    'luna_withdraw': luna_withdraw,
                    'usdt_withdraw': usdt_withdraw,
                    'profit': round(profit, 4)
                })

        df = pd.DataFrame(opportunities)
        df.to_csv(csv_file, mode='a', index=False, header=not Path(csv_file).exists())
        print(f"✅ Check completed. Sleeping for 3 seconds...")

        time.sleep(3)

if __name__ == '__main__':
    run_check()
