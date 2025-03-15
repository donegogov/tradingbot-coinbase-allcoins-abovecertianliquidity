from pybit.unified_trading import HTTP
from time import sleep
from decimal import Decimal, ROUND_DOWN
import requests
import socket
import os
import json
from dotenv import load_dotenv

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TESTNET = False  # True means your API keys were generated on testnet.bybit.com
START_PRICE_QTY = 130
SYMBOL = 'GRASSUSDT'
TOKEN_START_PRICE = 0.0
TOKEN_PROFIT_PRICE = 0.0
COIN = 'GRASS'
HELP_COIN = 'USDT'
CONNECTION_ERRORS = (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError,
                     requests.exceptions.Timeout, socket.timeout)
CONNECTION_ERRORS += (ConnectionResetError,)
# ✅ File to store held tokens
HELD_TOKENS_FILE = "held_tokens.json"
PRICE_HISTORY_FILE = "price_history.json"
TOKEN_PRICES_FILENAME = "token_prices.txt"


def make_order(symbol, side, qty):    
    print(session.place_order(
        category="spot",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=qty,
        orderFilter="Order",
    ))

def make_tp_order(symbol, side, qty):
    print(session.place_order(
        category="spot",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=qty,
        orderFilter="Order",
    ))

def get_token_price(symbol):
    response_price_dict = session.get_tickers(
        category="spot",
        symbol=symbol,
    )
    token_price = response_price_dict['result']['list'][0]['ask1Price']
    print('price')
    print(token_price)

    return token_price

def get_token_balance(coin):
    response_dict = session.get_coin_balance(
        accountType="UNIFIED",
        coin=coin,
        memberId="25506052"
    )
    token_wallet_balance = float(response_dict['result']['balance']['walletBalance'])

    return token_wallet_balance

# ✅ Save Held Tokens to File (every time we buy/sell)
def save_held_tokens():
    global held_tokens, held_token_prices
    
    data = {
        "held_tokens": list(held_tokens),
        "held_token_prices": held_token_prices
    }
    
    with open(HELD_TOKENS_FILE, "w") as file:
        json.dump(data, file, indent=4)


# ✅ Load Held Tokens from File (at startup)
def load_held_tokens():
    global held_tokens, held_token_prices

    if os.path.exists(HELD_TOKENS_FILE):
        with open(HELD_TOKENS_FILE, "r") as file:
            data = json.load(file)
            held_tokens = set(data.get("held_tokens", []))
            held_token_prices = data.get("held_token_prices", {})
        print(f"🔄 Loaded {len(held_tokens)} held tokens from file.")


def find_price_jump(token_price_history, min_x, percentage_threshold=0.03):
    prices = token_price_history[-min_x:]  # Get the last min_x prices
    min_price = float('inf')  # Start with a very high number
    last_price = None  # Store the last price when threshold is crossed
    price_change = 0.0

    for price in prices:
        if price < min_price:
            min_price = price  # Update min_price if a new lower value is found
        
    price_change_temp = (token_price_history[-1] - min_price) / min_price
    print(f"cenata se promenila od minimalista cena za {price_change_temp} procenti")
    if price_change_temp >= percentage_threshold:
        price_change = price_change_temp

    #ako e pod threshold promenata na cenata vrati 0
    if price_change == 0:
        return 0

    return price_change  # ako e nad threshold vrati ja promenata na cenata


# **Load price history from file**
def load_price_history():
    if os.path.exists(PRICE_HISTORY_FILE):
        with open(PRICE_HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}

# **Save price history to file**
def save_price_history(price_history):
    with open(PRICE_HISTORY_FILE, "w") as f:
        json.dump(price_history, f)

def save_prices(start_price, profit_price):
    with open(TOKEN_PRICES_FILENAME, "w") as file:
        file.write(f"{start_price},{profit_price}")


def load_prices():
    if os.path.exists(TOKEN_PRICES_FILENAME):
        with open(TOKEN_PRICES_FILENAME, "r") as file:
            data = file.read().strip()
            if data:
                start_price, profit_price = map(float, data.split(","))
                return start_price, profit_price
    return None, None  # Default values if file doesn't exist



import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

import random
import pandas as pd

def detect_spikes_dynamic(prices, min_spike=0.053, max_spike=0.50, recovery_threshold=0.053, max_time_range=20):
    """
    Detects significant price spikes by comparing each price with previous values across random time ranges.

    Parameters:
        prices (list): List of prices.
        min_spike (float): Minimum valid spike size in absolute price movement.
        max_spike (float): Maximum valid spike size.
        recovery_threshold (float): Minimum price increase after a down spike to count as recovery.
        max_time_range (int): Maximum lookback range (in number of data points). Time ranges will be randomly chosen up to this limit.

    Returns:
        list: List of tuples [(index, time_range, 'up'/'down'/'recovery', price change), ...]
    """
    df = pd.DataFrame({'price': prices})
    
    max_time_range = 2400  # Last 20 hours of stored prices
    # Generate random time ranges between 1 and max_time_range
    random_time_ranges = list(range(1, max_time_range + 1, 19))

    real_spikes = []
    last_down_index = {t: None for t in random_time_ranges}
    last_down_price = {t: None for t in random_time_ranges}

    for idx in range(max(random_time_ranges), len(df)):
        for time_range in random_time_ranges:
            past_price = df['price'].iloc[idx - time_range]
            current_price = df['price'].iloc[idx]
            change = round(float(current_price - past_price), 4)

            if min_spike <= abs(change) <= max_spike:
                direction = "up" if change > 0 else "down"
                real_spikes.append((idx, time_range, direction, round(change, 4)))

                if direction == "down":
                    last_down_index[time_range] = idx
                    last_down_price[time_range] = current_price

                if direction == "up" and last_down_index[time_range] is not None:
                    recovery = current_price - last_down_price[time_range]
                    if recovery >= recovery_threshold:
                        real_spikes.append((idx, time_range, "recovery", round(recovery, 4)))

    return real_spikes

def save_spike_results(results, filename="spike_results.txt"):
    with open(filename, "w") as f:
        for entry in results:
            f.write(f"{entry}\n")


import numpy as np
from collections import defaultdict

def format_spikes_last_only(spike_results):
    last_spikes = {}  # Dictionary to store the last spike per time range

    for idx, time_range, spike_type, change in spike_results:
        change = round(float(change), 4)  # Ensure it's a standard float
        last_spikes[time_range] = (idx, time_range, spike_type, change)  # Store only the last occurrence

    # Convert to a list of tuples
    formatted_spikes = list(last_spikes.values())

    return formatted_spikes




session = HTTP(
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
    testnet=TESTNET,
)

# ✅ Global variables
held_tokens = set()
held_token_prices = {}
load_held_tokens()
price_history = load_price_history()
X = 2400  # ✅ Check last 10 hours dynamically
min_X = 60  # ✅ Check last 5 minutes dynamically
smart_take_profit = False
can_buy = False

# Example Usage
TOKEN_START_PRICE, TOKEN_PROFIT_PRICE = load_prices()
if TOKEN_START_PRICE is None or TOKEN_PROFIT_PRICE is None:
    TOKEN_START_PRICE = 0.0  # Default values
    TOKEN_PROFIT_PRICE = 0.0
    save_prices(TOKEN_START_PRICE, TOKEN_PROFIT_PRICE)


token_history_price = float(get_token_price(SYMBOL))
sleep(30)

while True:
    try:
        token_price = float(get_token_price(SYMBOL))
        grass = get_token_balance(COIN)
        usdt = get_token_balance(HELP_COIN)
        print(grass)
        print(usdt)
        # **Price Change Calculation**
        historical_prices = price_history.get(COIN, {}).get("prices", [])
        
        # Append latest token price
        if token_price:
            historical_prices.append(token_price)

        # Keep only last X prices
        price_history[COIN] = {"prices": historical_prices[-X:]}
        save_price_history(price_history)

        # Ensure price change is calculated over 2.5 minutes to 4 hours
        if len(historical_prices) < min_X:
            continue
        
        # Extract price history
        token_price_history = [entry for entry in historical_prices]

        # Ensure we have enough history
        if len(token_price_history) < min_X:
            continue
        short_array = 3
        save_price_history(price_history)
        if can_buy == False:
            spike_fluct = 0.0
            # Run detection function
            spike_results = detect_spikes_dynamic(token_price_history)
            nested_spikes = format_spikes_last_only(spike_results)  # Format them properly
            # Save results to a text file
            save_spike_results(nested_spikes)

            print("Spikes saved to spike_results.txt")

            # Check if recovery exists
            if any(len(spike) == 2 and spike[2][3] == "recovery" for spike in spike_results):
                print("Recovery detected! You can buy.")
                for spike in spike_results:
                    if spike[1][3] == "down":
                        spike_fluct = abs(spike[1][4])
                        short_array = [1][1]
            else:
                print("No recovery detected yet.")
            #ako iame fluktacii od 6.5 do 16 centi
            if spike_fluct >= 0.053 and spike_fluct <= 0.16:
                threshold = 0.01
                TOKEN_PROFIT_PRICE = token_price * 1.02
                smart_take_profit_threshold = 0.01
                can_buy = True
            #ako iame fluktacii od 16.1 do 50 centi
            elif spike_fluct >= 0.161 and spike_fluct <= 0.5:
                threshold = 0.014
                TOKEN_PROFIT_PRICE = token_price * 1.03
                smart_take_profit_threshold = 0.026
                can_buy = True

        # Get price change over time
        #price_change = find_price_jump(token_price_history, len(token_price_history) - 1, threshold)
        #print(f"🔍 DEBUG: {SYMBOL} Price Change = {price_change:.20%}, Threshold = {threshold:.4%}")
        if TOKEN_START_PRICE == 0 and TOKEN_PROFIT_PRICE != 0 and can_buy == True:
            TOKEN_START_PRICE = token_price * (1 - 0.03)  # 3% lower
            #TOKEN_PROFIT_PRICE = token_price * 1.027
            save_prices(TOKEN_START_PRICE, TOKEN_PROFIT_PRICE)
            # Keep only last 3 prices
            short = len(token_price_history) - short_array
            price_history[COIN] = {"prices": historical_prices[-short:]}
            save_price_history(price_history)
        print('TOKEN_START_PRICE')
        print(TOKEN_START_PRICE)
        print('TOKEN_PROFIT_PRICE')
        print(TOKEN_PROFIT_PRICE)
        
        #ako momentalnata cena otisla od pomalce nad startna cena togas kupi GRASS
        if SYMBOL not in held_tokens:
            if token_price > TOKEN_START_PRICE and TOKEN_START_PRICE != 0 and TOKEN_PROFIT_PRICE != 0:
                print(f"DEBUG token_price > token start price and token_start_price > token history")
                token_wallet_balance_USDT = get_token_balance(HELP_COIN)
                token_wallet_balance_USDT = Decimal(token_wallet_balance_USDT)
                token_wallet_balance_USDT = token_wallet_balance_USDT.quantize(Decimal('0.1'), rounding=ROUND_DOWN)  # Keeps only 2 decimals
                side = 'Buy'
                print(token_wallet_balance_USDT)
                held_token_prices[SYMBOL] = {"buy_price": token_price, "highest_price": token_price}
                held_tokens.add(SYMBOL)
                save_held_tokens()  # ✅ Save after buying
                make_order(SYMBOL, side, token_wallet_balance_USDT)
            
        elif SYMBOL in held_tokens:
            #ako momentalnata cena otisla od poveke kon pomalce od startna cena togas prodaj GRASS
            if TOKEN_START_PRICE > token_price and TOKEN_START_PRICE != 0 and TOKEN_PROFIT_PRICE != 0:
                print(f"DEBUG token history > token start price and token_start > token_price")
                token_wallet_balance = get_token_balance(COIN)
                token_wallet_balance = Decimal(token_wallet_balance)          
                str_token_wallet_balance = token_wallet_balance.quantize(Decimal('0.1'), rounding=ROUND_DOWN)  # Keeps only 2 decimals
                side = 'Sell'
                # Remove token from held tokens after selling
                held_tokens.discard(SYMBOL)
                del held_token_prices[SYMBOL]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
                save_held_tokens()
                TOKEN_START_PRICE = 0.0
                TOKEN_PROFIT_PRICE = 0.0
                save_prices(TOKEN_START_PRICE, TOKEN_PROFIT_PRICE)
                can_buy = False
                make_order(SYMBOL, side, str_token_wallet_balance)
            
            elif (token_price > TOKEN_PROFIT_PRICE and TOKEN_START_PRICE != 0 and TOKEN_PROFIT_PRICE != 0) or smart_take_profit == True:
                print("TOKEN PROFIT PRICE IS HERE")
                smart_take_profit = True
                token_wallet_balance = get_token_balance(COIN)
                if token_wallet_balance > 1:
                    highest_price = held_token_prices[SYMBOL].get("highest_price", "buy_price")
                if token_price > highest_price:
                    print("updejt najgolema cent")
                    held_token_prices[SYMBOL]["highest_price"] = token_price
                if (held_token_prices[SYMBOL]["highest_price"] - token_price) / held_token_prices[SYMBOL]["highest_price"] >= smart_take_profit_threshold:
                    print('held_token_prices - token_price DELENOSO held_token_prices >= 0 koma 19 te 1,9 procenti te najvisokata suma padna za 1,9 posto pa prodavame')
                    token_wallet_balance = get_token_balance(COIN)
                    token_wallet_balance = Decimal(token_wallet_balance)          
                    str_token_wallet_balance = token_wallet_balance.quantize(Decimal('0.1'), rounding=ROUND_DOWN)  # Keeps only 2 decimals
                    side = 'Sell'
                    held_tokens.discard(SYMBOL)
                    del held_token_prices[SYMBOL]
                    save_held_tokens()
                    make_tp_order(SYMBOL, side, str_token_wallet_balance)
                    TOKEN_START_PRICE = 0.0
                    TOKEN_PROFIT_PRICE = 0.0
                    can_buy = False
                    smart_take_profit = False
                    save_prices(TOKEN_START_PRICE, TOKEN_PROFIT_PRICE)
                    #price_history[COIN] = {"prices": historical_prices[-3:]}
                    #save_price_history(price_history)

        token_history_price = token_price
        sleep(30)
    except CONNECTION_ERRORS as e:
        print(f'Éxception  {e}')
    except Exception as e:
        print(f'Éxception  {e}') 

#print(get_token_balance(COIN))
