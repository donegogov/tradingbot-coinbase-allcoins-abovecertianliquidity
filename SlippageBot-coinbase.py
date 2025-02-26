import json
import time
import requests
from web3 import Web3
import os
import logging
from dotenv import load_dotenv
from web3.middleware import ExtraDataToPOAMiddleware
from eth_utils import event_abi_to_log_topic
import random
from eth_account import Account
from datetime import datetime
import csv
# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Load environment variables from .env file
load_dotenv()


# Connect to the blockchain
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
AERODROME_SUBGRAPH_URL = "https://gateway.thegraph.com/api/547adc7c0f0541cf9e78feaffbc5cce5/subgraphs/id/GENunSHWLBXm59mBSgPzQ8metBEp9YDfdqwFr91Av1UM"
# TheGraph API (ONLY FOR POOLS & PRICES)
#THEGRAPH_UNISWAP_URL = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
THEGRAPH_COINBASE_URL = AERODROME_SUBGRAPH_URL

# **CACHE SETTINGS**
TOKEN_PAIRS_CACHE_FILE = "token_pairs_cache.json"
LAST_PAIR_FETCH_TIME = 0  # Last time pairs were fetched (UNIX timestamp)

# **CACHE POOLS** (Fetch every 1 hour)
POOLS_CACHE_FILE = "pools_cache.json"
LAST_POOL_FETCH_TIME = 0  # Store last fetch time

if not RPC_URL or not PRIVATE_KEY:
    raise ValueError("Missing required environment variables. Check your .env file.")

print(f"RPC_URL: {RPC_URL}")
print(f"PRIVATE_KEY: {PRIVATE_KEY[:5]}...")  # Print first 5 characters for verification

w3 = Web3(Web3.HTTPProvider(RPC_URL))
# Add middleware for Proof-of-Authority chains (e.g., Polygon, BSC)                
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
if w3.is_connected():
    print("Connected to the network")
else:
    print("Failed to connect to the network")
AERODROME_ROUTER = w3.to_checksum_address("0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43")  # Confirm actual address

owner_address = w3.eth.account.from_key(PRIVATE_KEY).address
WALLET_ADDRESS = owner_address
print(owner_address)
# Load the contract ABI
with open("contract_abi.json") as f:
    contract_abi = json.load(f)


STOP_LOSS_PERCENT = -0.03  # 5% drop
TAKE_PROFIT_PERCENT = 0.09  # 10% increase
TAKE_PROFIT_STOP_LOSS_PERCENT = -0.015

TRADE_LOG_FILE = "trade_history.csv"

# **Uniswap V3 Pool ABI (Minimal Required Functions & Events)**
UNISWAP_V3_POOL_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "recipient", "type": "address"},
            {"indexed": False, "internalType": "int256", "name": "amount0", "type": "int256"},
            {"indexed": False, "internalType": "int256", "name": "amount1", "type": "int256"},
            {"indexed": False, "internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"indexed": False, "internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"indexed": False, "internalType": "int24", "name": "tick", "type": "int24"}
        ],
        "name": "Swap",
        "type": "event"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "fee",
        "outputs": [{"name": "", "type": "uint24"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"name": "", "type": "uint128"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"}
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]


# Load ERC-20 ABI (Minimal)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_from", "type": "address"},
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Approval",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]


# Uniswap V2 Router ABI (Minimal)
UNISWAP_V2_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}]')

AERODROME_ROUTER_ABI = json.loads('[{"inputs": [{ "internalType": "uint256", "name": "amountIn", "type": "uint256" },{ "internalType": "uint256", "name": "amountOutMin", "type": "uint256" },{ "internalType": "tuple[]","name": "routes","type": "tuple[]","components": [{ "internalType": "address", "name": "from", "type": "address" },{ "internalType": "address", "name": "to", "type": "address" },{ "internalType": "bool", "name": "stable", "type": "bool" },{ "internalType": "address", "name": "factory", "type": "address" }]},{ "internalType": "address", "name": "to", "type": "address" },{ "internalType": "uint256", "name": "deadline", "type": "uint256" }],"name": "swapExactTokensForTokens","outputs": [],"stateMutability": "nonpayable","type": "function"},{"inputs": [{ "internalType": "uint256", "name": "amountIn", "type": "uint256" },{ "internalType": "tuple[]","name": "routes","type": "tuple[]","components": [{ "internalType": "address", "name": "from", "type": "address" },{ "internalType": "address", "name": "to", "type": "address" },{ "internalType": "bool", "name": "stable", "type": "bool" },{ "internalType": "address", "name": "factory", "type": "address" }]}],"name": "getAmountsOut","outputs": [{"internalType": "uint256[]","name": "amounts","type": "uint256[]"}],"stateMutability": "view","type": "function"}]')

# Uniswap V2 Router Address (Polygon)
UNISWAP_V2_ROUTER = w3.to_checksum_address("0xedf6066a2b290C185783862C7F4776A2C8077AD1")

# Uniswap Pool Fee Tier (500 = 0.05%, 3000 = 0.3%, 10000 = 1%)
POOL_FEE = 3000

# Token Addresses (Example: WMATIC -> USDC)
USDC_ADDRESS = w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")  # usdc
WETH_ADDRESS = w3.to_checksum_address("0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619")  # with

LAST_PAIR_FETCH_TIME = 0

# Load mock data from files
#with open("mock_token_pairs.json", "r") as f:
#    token_pairs = json.load(f)

#with open("mock_price_history.json", "r") as f:
#    price_history = json.load(f)

#with open("mock_pools.json", "r") as f:
#    pools = json.load(f)

#with open("mock_swaps.json", "r") as f:
#    monitor_swaps_data = json.load(f)

# Print to verify loading
#print("✅ Mock data loaded successfully")
#print(f"Loaded {len(token_pairs)} token pairs")
#print(f"Loaded {len(pools)} pools")
#print(f"Loaded {len(monitor_swaps_data)} swaps")


PRICE_HISTORY_FILE = "price_history.json"

FETCH_SWAPS_FROM_LATEST_XBLOCKS = 500
IF_FETCH_SWAPS_FROM_LATEST_XBLOCKS = False

SWAP_EVENT_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "sender", "type": "address"},
        {"indexed": False, "name": "amount0In", "type": "uint256"},
        {"indexed": False, "name": "amount1In", "type": "uint256"},
        {"indexed": False, "name": "amount0Out", "type": "uint256"},
        {"indexed": False, "name": "amount1Out", "type": "uint256"},
        {"indexed": True, "name": "to", "type": "address"},
    ],
    "name": "Swap",
    "type": "event"
}

# Global trade log
trade_log = []

# ✅ File to store held tokens
HELD_TOKENS_FILE = "held_tokens.json"

# ✅ Global variables
held_tokens = set()
held_token_prices = {}

# Define base tokens (USDC, WETH, WMATIC) and decimals
BASE_TOKENS = {
    "USDC": {"id": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6, "token_price": 1.0},
    "WETH": {"id": "0x4200000000000000000000000000000000000006", "decimals": 18, "token_price": 3000.00},
    "USDT": {"id": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", "decimals": 6, "token_price": 1.0},
    "WBTC": {"id": "0x0555E30da8f98308EdB960aa94C0Db47230d2B9c", "decimals": 8, "token_price": 100000.00}
}

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


def to_checksum(address):
    """Converts an Ethereum address to a checksum address."""
    try:
        return w3.to_checksum_address(address)
    except Exception:
        logging.error(f"⚠️ Invalid address: {address}")
        return address  # Return original if conversion fails

def get_wallet_token_balance(token_id):
    # Standard ERC-20 balanceOf function ABI
    balance_of_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
    
    # Create contract instance
    token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_id), abi=balance_of_abi)
    
    # Get token balance
    balance = token_contract.functions.balanceOf(WALLET_ADDRESS).call()
    
    return balance  # Returns balance in token's smallest unit (e.g., Wei)


# Function to get ERC-20 balance
def get_token_balance(token_address, owner):
    token_contract = w3.eth.contract(address=to_checksum(token_address), abi=ERC20_ABI)
    balance = token_contract.functions.balanceOf(to_checksum(owner)).call()
    return balance

# Function to approve Uniswap V2 Router to spend tokens
def approve_token(token_address, spender, amount):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    
    tx = token_contract.functions.approve(spender, amount).build_transaction({
        "from": WALLET_ADDRESS,
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(WALLET_ADDRESS),
    })
    try:
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"✅ Approve Transaction Sent: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        return tx_hash
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    return 


def aerodrome_swap(token_in, token_out, amount_in, amount_out_min, smart_take_profit=False):
    router_contract = w3.eth.contract(address=AERODROME_ROUTER, abi=AERODROME_ROUTER_ABI)
    print('aerodrome_swap')
    print(token_in)
    print(token_out)
    # Build Swap Transaction
    AERODROME_FACTORY_ADDRESS = w3.to_checksum_address('0x420DD381b31aEf6683db6B902084cB0FFECe40Da')
    deadline = w3.eth.get_block("latest")["timestamp"] + 300  # 5-minute deadline
    stable = False
    routes = [{
        "from": w3.to_checksum_address(token_in),
        "to": w3.to_checksum_address(token_out),
        "stable": False,  # If the pool is stable, set this to True
        "factory": AERODROME_FACTORY_ADDRESS
    }]
    amountOut = router_contract.functions.getAmountsOut(amount_in, routes).call()
    amountOutMin = amountOut[1] / (10**get_token_decimals(token_out))
    amountOutMin = amountOutMin * 0.99
    amountOutMin = amountOutMin * (10**get_token_decimals(token_out))
    amountOutMin = int(amountOutMin)
    swap_tx = router_contract.functions.swapExactTokensForTokens(
        amount_in,
        amountOutMin,
        routes,  
        w3.to_checksum_address(WALLET_ADDRESS),
        deadline
    ).build_transaction({
        "from": w3.to_checksum_address(WALLET_ADDRESS),
        "gas": 300000,
        "gasPrice": int(w3.eth.gas_price * 1.5),
        "nonce": w3.eth.get_transaction_count(WALLET_ADDRESS),
    })

    # Sign and Send Transaction
    signed_swap_tx = w3.eth.account.sign_transaction(swap_tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_swap_tx.raw_transaction)
    print(f"✅ Swap Transaction Sent: {tx_hash.hex()}")
    try:
    # Wait for Confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"✅ Swap Successful! Tx Hash: {tx_hash.hex()}")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    time.sleep(1)
    
    #####sell with to usdc
    if token_out == w3.to_checksum_address("0x4200000000000000000000000000000000000006") and smart_take_profit == True:
        approve_token(token_out, AERODROME_ROUTER, amountOutMin)  # Approve 10

        
        deadline = w3.eth.get_block("latest")["timestamp"] + 300  # 5-minute deadline
        stable = False
        routes = [{
            "from": w3.to_checksum_address(token_out), #WETH
            "to": w3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"), #USDC
            "stable": False,  # If the pool is stable, set this to True
            "factory": AERODROME_FACTORY_ADDRESS
        }]
        amountOut = router_contract.functions.getAmountsOut(amountOutMin, routes).call()
        amountOutUSDC = amountOut[1] / (10**6)
        amountOutUSDC = amountOutUSDC * 0.99
        amountOutUSDC = amountOutUSDC * (10**6)
        amountOutUSDC = int(amountOutUSDC)    
        swap_tx = router_contract.functions.swapExactTokensForTokens(
            amountOutMin,
            amountOutUSDC,
            routes,  
            w3.to_checksum_address(WALLET_ADDRESS),
            deadline
        ).build_transaction({
            "from": w3.to_checksum_address(WALLET_ADDRESS),
            "gas": 300000,
            "gasPrice": int(w3.eth.gas_price * 1.5),
            "nonce": w3.eth.get_transaction_count(WALLET_ADDRESS),
        })

        # Sign and Send Transaction
        signed_swap_tx = w3.eth.account.sign_transaction(swap_tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_swap_tx.raw_transaction)
        print(f"✅ Swap Transaction Sent: {tx_hash.hex()}")
        try:
        # Wait for Confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            print(f"✅ Swap Successful! Tx Hash: {tx_hash.hex()}")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
    #####
    return tx_hash




def uniswap_v2_swap(token_in, token_out, amount_in, amount_out_min):
    router_contract = w3.eth.contract(address=UNISWAP_V2_ROUTER, abi=UNISWAP_V2_ABI)

    # Build Swap Transaction
    deadline = w3.eth.get_block("latest")["timestamp"] + 300  # 5-minute deadline
    swap_tx = router_contract.functions.swapExactTokensForTokens(
        amount_in,
        amount_out_min,
        [token_in, token_out],  # Token path
        WALLET_ADDRESS,
        deadline
    ).build_transaction({
        "from": WALLET_ADDRESS,
        "gas": 300000,
        "gasPrice": int(w3.eth.gas_price * 1.5),
        "nonce": w3.eth.get_transaction_count(WALLET_ADDRESS),
    })
    try:
        # Sign and Send Transaction
        signed_swap_tx = w3.eth.account.sign_transaction(swap_tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_swap_tx.raw_transaction)
        print(f"✅ Swap Transaction Sent: {tx_hash.hex()}")
    
        # Wait for Confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"✅ Swap Successful! Tx Hash: {tx_hash.hex()}")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    return 

from web3 import Web3
from eth_account import Account

def execute_batch_trades(trades):
    """Executes multiple trades in a single transaction."""
    if not trades:
        print("✅ No trades to execute.")
        return
    
    router = w3.eth.contract(address=UNISWAP_V2_ROUTER, abi=UNISWAP_V2_ABI)

    txs = []

    try:
        #First approve all tokens
        for trade in trades:
            approve_token(to_checksum(trade["tokenIn"]), UNISWAP_V2_ROUTER, trade["amountIn"])  # Approve 10

        nonce = w3.eth.get_transaction_count(WALLET_ADDRESS)
        for trade in trades:
            path = [trade["tokenIn"], trade["tokenOut"]]
            amount_in = trade["amountIn"]
            amount_out_min = trade["amountOutMin"]

            tx = router.functions.swapExactTokensForTokens(
                amount_in, 0, path, WALLET_ADDRESS, int(time.time()) + 600
            ).build_transaction({
                "from": WALLET_ADDRESS,
                "gas": 250000,
                "gasPrice": w3.to_wei('5', 'gwei'),
                "nonce": nonce
            })

        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        txs.append(signed_tx.raw_transaction)
        nonce += 1

        # **Send all transactions together**
        tx_hashes = [w3.eth.send_raw_transaction(tx) for tx in txs]
    
        print(f"✅ Sent {len(trades)} trades in batch!")
        # **🔄 Wait for all transactions to be confirmed**
        receipts = []
        for tx_hash in tx_hashes:
            print(f"⏳ Waiting for transaction {tx_hash.hex()} to be confirmed...")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)  # ⏳ Wait max 120 sec
            receipts.append(receipt)
            print(f"✅ Transaction {tx_hash.hex()} confirmed in block {receipt.blockNumber}")

        print(f"✅ All {len(trades)} trades confirmed! 🎉")
        return receipts
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    return 

def autoTrade(token_in, token_out, amount_in, amount_out_min, pool_fee, smart_take_profit = False):
    try:
        token_in = w3.to_checksum_address(token_in)
        token_out = w3.to_checksum_address(token_out)
        # Step 1: Approve Uniswap V3 Router to Spend Tokens
        #for trade in trades
        approve_token(token_in, AERODROME_ROUTER, amount_in)  # Approve 10

        aerodrome_swap(token_in, token_out, amount_in, amount_out_min, smart_take_profit)
        #execute_batch_trades(trades)
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    return 


def log_trade(trade_type, token, price, profit_loss=0, reason=""):
    global trade_log
    
    trade_data = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_type": trade_type,  # Buy or Sell
        "token": token,
        "price": price,
        "profit_loss": profit_loss,  # 0 for buy, actual P&L for sells
        "reason": reason  # Take Profit or Stop Loss
    }
    
    trade_log.append(trade_data)

    # ✅ Save to CSV
    file_exists = os.path.exists(TRADE_LOG_FILE)
    with open(TRADE_LOG_FILE, mode="a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=trade_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade_data)


def discover_token_pairs(force_refresh=False):
    """Fetch Uniswap v3 token pairs (caches results for 1 hour)."""
    global LAST_PAIR_FETCH_TIME
    now = time.time()

    # **Check if last fetch was within 1 hour**
    if not force_refresh and now - LAST_PAIR_FETCH_TIME < 3600:
        try:
            with open(TOKEN_PAIRS_CACHE_FILE, "r") as f:
                return json.load(f)  # Load from cache
        except FileNotFoundError:
            pass  # If cache not found, fetch fresh data

    # **Fetch data from TheGraph**
    try:
        query = """
        {
            pairs(first: 1000, where: { reserveUSD_gt: 999 }) {
                token0 { id symbol }
                token1 { id symbol }
                id
                reserveUSD
                token0Price
                token1Price
            }
        }
        """
        response = requests.post(THEGRAPH_UNISWAP_URL, json={"query": query})
        response.raise_for_status()
        data = response.json()

        pools = data["data"]["pairs"]
        token_pairs = []

        for pool in pools:
            #print(pool)
            #print('POOLPOOL')
            token0_price = float(pool.get("token0Price", "0"))  # Ensure float
            token1_price = float(pool.get("token1Price", "0"))  # Ensure float

            token_pairs.append({
                "token0": {
                    "id": to_checksum(pool["token0"]["id"]),
                    "symbol": pool["token0"]["symbol"]
                },
                "token1": {
                    "id": to_checksum(pool["token1"]["id"]),
                    "symbol": pool["token1"]["symbol"]
                },
                "pairId": pool["id"],
                "liquidity": int(float(pool["reserveUSD"])),
                "token0Price": token0_price,
                "token1Price": token1_price
            })

        # **Update Cache**
        LAST_PAIR_FETCH_TIME = now
        with open(TOKEN_PAIRS_CACHE_FILE, "w") as f:
            json.dump(token_pairs, f)

        return token_pairs

    except Exception as e:
        logging.error(f"❌ Error discovering token pairs: {e}")
        return []

def check_and_approve_allowance(token_address, spender_address, required_amount):
    """Check token allowance and approve if necessary."""
    try:
        token_contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_ABI)

        # Check allowance
        allowance = token_contract.functions.allowance(owner_address, spender_address).call()
        logger.info(f"Current allowance for {token_address}: {allowance}")

        if allowance < required_amount:
            logger.info(f"Insufficient allowance. Approving {required_amount} for {spender_address}...")
            approve_tx = token_contract.functions.approve(spender_address, required_amount).build_transaction({
                'from': owner_address,
                'gas': 100000,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(owner_address)
            })

            signed_approve_tx = w3.eth.account.sign_transaction(approve_tx, private_key=PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_approve_tx.raw_transaction)
            logger.info(f"Approval transaction sent. Tx hash: {tx_hash.hex()}")

        else:
            logger.info(f"Sufficient allowance already exists for {spender_address}.")

    except Exception as e:
        logger.error(f"Error checking or approving allowance for {token_address}: {e}")


def get_pool_address(pool_id):
    """Fetch Uniswap V3 pool address using pool ID from Polygon RPC (No Graph API)"""
    try:
        # **Convert pool ID to checksum address**
        # **Ensure Pool ID is in Proper Hex Format**
        if not pool_id.startswith("0x"):
            pool_id = "0x" + pool_id  # ✅ Add '0x' prefix if missing
        pool_address = w3.to_checksum_address(pool_id)
        return pool_address  # ✅ Return directly for monitor_swaps()

    except Exception as e:
        logging.error(f"❌ Error converting pool ID to address: {e}")
        return None

def decode_swap_log(log):
    """ Decodes a Uniswap V2 Swap event log and formats it into swap_data """
    
    try:
        # Ensure log is for Swap event
        swap_event_topic = event_abi_to_log_topic(SWAP_EVENT_ABI)
        if log["topics"][0].hex() != swap_event_topic:
            return None  # Skip invalid logs

        # Decode the log
        decoded_event = w3.codec.decode_log(SWAP_EVENT_ABI, log["data"], log["topics"])
        
        # Structure swap data
        swap_data = {
            "transactionHash": log["transactionHash"].hex(),
            "blockNumber": log["blockNumber"],
            "amount0": int(decoded_event["amount0In"]) - int(decoded_event["amount0Out"]),  # Net token0
            "amount1": int(decoded_event["amount1In"]) - int(decoded_event["amount1Out"]),  # Net token1
            "amountUSD": abs(float(decoded_event["amount0In"])) + abs(float(decoded_event["amount1In"]))  # USD value
        }

        return swap_data

    except Exception as e:
        logging.error(f"⚠️ Error decoding swap log: {e}")
        return None

# Define Uniswap V2 Swap Event ABI (Simplified)
UNISWAP_V2_PAIR_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "sender", "type": "address"},
            {"indexed": False, "name": "amount0In", "type": "uint256"},
            {"indexed": False, "name": "amount1In", "type": "uint256"},
            {"indexed": False, "name": "amount0Out", "type": "uint256"},
            {"indexed": False, "name": "amount1Out", "type": "uint256"},
            {"indexed": True, "name": "to", "type": "address"},
        ],
        "name": "Swap",
        "type": "event",
    }
]



def monitor_swaps_mock(pool_id):
    """Mock swap data to simulate real swaps happening in pools."""
    return [{
        "amountUSD": round(random.uniform(900, 1100), 2)  # Simulating swap amounts close to 1000 USD
    }]



def monitor_swaps(pool_id):
    """Fetch recent swaps from Polygon RPC using Uniswap V3 pool ID"""
    """Mock monitor_swaps function using preloaded mock data"""
    #global monitor_swaps_data
    #return monitor_swaps_data.get(pool_id, [])  # Return mock swap data
    global FETCH_SWAPS_FROM_LATEST_XBLOCKS
    try:
        # **Fetch Pool Address from Pool ID**
        pool_address = get_pool_address(pool_id)

        if not pool_address:
            logging.error(f"❌ Pool address not found for pool ID: {pool_id}")
            return []

        # **Swap Event Signature (Uniswap V3)**
        #swap_event_signature = w3.solidity_keccak(['string'],['Swap(address,address,int256,int256,uint160,uint128,int24)']).hex()
        #print(f"🔍 Debug: Swap Event Signature -> {swap_event_signature}")
        swap_event_signature = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
        #print(f"🔍 Debug: Swap Event Signature -> {swap_event_signature}")

        # **Fetch Swap Logs from Polygon RPC**
        logs = w3.eth.get_logs({
            "fromBlock": w3.eth.block_number - FETCH_SWAPS_FROM_LATEST_XBLOCKS,  # Last 500 blocks (~10 minutes)
            "toBlock": "latest",
            "pair_address": pool_address,  # ✅ Now using pool address
            "topics": [swap_event_signature]  # Filter only Swap events
        })
        #print(logs)
        if FETCH_SWAPS_FROM_LATEST_XBLOCKS == 500000 and IF_FETCH_SWAPS_FROM_LATEST_XBLOCKS:
            FETCH_SWAPS_FROM_LATEST_XBLOCKS = 500

        print(f"✅ Found {len(logs)} logs (After Filtering)")
        decoded_swaps = []
        for log in logs:
            try:
                # Instantiate the contract
                pair_contract = w3.eth.contract(address= pool_address, abi=UNISWAP_V2_PAIR_ABI)

                # Process the log using Uniswap V2 Swap event
                decoded_event = pair_contract.events.Swap().process_log(log)
                
                amount0_in = float(decoded_event["args"]["amount0In"])
                amount1_in = float(decoded_event["args"]["amount1In"])
                amount0_out = float(decoded_event["args"]["amount0Out"])
                amount1_out = float(decoded_event["args"]["amount1Out"])

                # ✅ Price Calculation
                if amount0_in > 0 and amount1_out > 0:
                    price_token0 = abs(amount1_out / amount0_in)  # ✅ Token0 price in Token1
                    price_token1 = abs(amount0_in / amount1_out)  # ✅ Token1 price in Token0
                elif amount1_in > 0 and amount0_out > 0:
                    price_token0 = abs(amount1_in / amount0_out)  # ✅ Token0 price in Token1
                    price_token1 = abs(amount0_out / amount1_in)  # ✅ Token1 price in Token0
                else:
                    price_token0 = None
                    price_token1 = None

                # ✅ Store Swap Data
                swap_data = {
                    "transactionHash": log.transactionHash.hex(),
                    "blockNumber": log.blockNumber,
                    "amount0In": amount0_in,
                    "amount1In": amount1_in,
                    "amount0Out": amount0_out,
                    "amount1Out": amount1_out,
                    "amountUSD": abs(amount0_in) + abs(amount1_in),  # ✅ USD value traded
                    "price_token0": price_token0,  # ✅ Correct price for token0
                    "price_token1": price_token1   # ✅ Correct price for token1
                }
                decoded_swaps.append(swap_data)

            except Exception as decode_error:
                logging.error(f"⚠️ Error decoding swap log: {decode_error}")
                continue

        return decoded_swaps[-15:]  # ✅ Returns **decoded** swaps with `amountUSD`

    except Exception as e:
        logging.error(f"❌ Error fetching swaps from RPC: {e}")
        return []


# **DETERMINE TOKEN PRICES (CACHE)**
TOKEN_PRICE_CACHE = {}

def calculate_moving_average(data, period):
    """Calculate the moving average over a specific period."""
    if len(data) < period:
        return None
    return sum(data[-period:]) / period

def analyze_volume(swaps):
    """Analyze trade volume in recent swaps."""
    return sum(float(swap["amountUSD"]) for swap in swaps)


def decide_trades_old(token_pairs, price_history, base_tokens, token_prices, pools, 
                  threshold=0.05, slippage_tolerance=0.01, min_liquidity=5_000):
    """Scans ALL Uniswap v3 pools and finds the best tokens to trade dynamically."""
    global IF_FETCH_SWAPS_FROM_LATEST_XBLOCKS
    global held_tokens, held_token_prices
    trades = []
    
    X = 600  # ✅ Check last 10 hours dynamically
    min_X = 5  # ✅ Check last 5 minutes dynamically

    for pair in token_pairs:
        token0 = pair["token0"]
        token1 = pair["token1"]
        pool_id = pair["pairId"]
        liquidity = pair.get("liquidity", min_liquidity + 1)  # Ensure liquidity is always present

        # **Ensure valid Ethereum address**
        if len(token0["id"]) != 42 or not token0["id"].startswith("0x"):
            continue
        if len(token1["id"]) != 42 or not token1["id"].startswith("0x"):
            continue

        # Ensure sufficient liquidity
        if liquidity < min_liquidity:
            continue

        # **Fetch latest swaps**
        swaps = monitor_swaps(pool_id)
        amount_usd = swaps[-1]["amountUSD"] if swaps else 1000.0  # Use fallback if no swaps exist

        # **Price Change Calculation**
        historical_prices = price_history.get(pool_id, {}).get("prices", [])
        historical_prices.append(amount_usd)
        price_history[pool_id] = {"amountUSD": amount_usd, "prices": historical_prices[-X:]}

        price_change_values = [
            (amount_usd - historical_prices[-i]) / historical_prices[-i]
            for i in range(min_X, min(X, len(historical_prices))) if len(historical_prices) > i
        ]
        price_change = max(price_change_values) if price_change_values else 0.0

        # **Trade decision based on price movements**
        token0_price = determine_token_price(token0["id"], pools) or token_prices.get(token0["id"], 1.0)
        token1_price = determine_token_price(token1["id"], pools) or token_prices.get(token1["id"], 1.0)

        if token0_price is None or token1_price is None:
            continue

        # **Find the best base token and pool order**
        best_base_token = None
        best_base_token_price = None
        best_base_token_decimals = None

        for pool in pools:
            pool_token0 = pool.get("token0", {}).get("id")
            pool_token1 = pool.get("token1", {}).get("id")

            for base_token in base_tokens.values():
                base_token_id = base_token["id"]
                base_token_decimals = base_token["decimals"]

                if pool_token0 == base_token_id and pool_token1 in [token0["id"], token1["id"]]:
                    best_base_token = base_token_id
                    best_base_token_price = token_prices.get(base_token_id, 1.0)
                    best_base_token_decimals = base_token_decimals
                    break  
                elif pool_token1 == base_token_id and pool_token0 in [token0["id"], token1["id"]]:
                    best_base_token = base_token_id
                    best_base_token_price = token_prices.get(base_token_id, 1.0)
                    best_base_token_decimals = base_token_decimals
                    break  
            if best_base_token:
                break  

        trade_direction = None
        token_to_buy = token0["id"] if token0_price > token1_price else token1["id"]
        token_to_sell = token1["id"] if token0_price > token1_price else token0["id"]

        # **Buy Logic (Force Execution)**
        if price_change > threshold and token_to_buy not in held_tokens:
            held_token_prices[token_to_buy] = token0_price if token0["id"] == token_to_buy else token1_price
            trade_direction = "buy"
            held_tokens.add(token_to_buy)
            
            # ✅ Force trade execution
            amount_in = int((1 / best_base_token_price) * (10 ** best_base_token_decimals))
            trade = {
                "tokenIn": best_base_token,
                "tokenOut": token_to_buy,
                "amountIn": amount_in,
                "amountOutMin": int(amount_in * (1 - slippage_tolerance)),
                "poolFee": 3000
            }
            trades.append(trade)
        
        # **Take Profit / Stop Loss Logic**
        elif token_to_sell in held_tokens:
            buy_price = held_token_prices[token_to_sell]
            adjusted_price_change = (token_prices[token_to_sell] - buy_price) / buy_price

            if adjusted_price_change >= TAKE_PROFIT_PERCENT or adjusted_price_change <= STOP_LOSS_PERCENT:
                trade_direction = "sell"
                held_tokens.discard(token_to_sell)
                del held_token_prices[token_to_sell]
                
                # ✅ Force trade execution
                amount_in = int((1 / best_base_token_price) * (10 ** best_base_token_decimals))
                trade = {
                    "tokenIn": token_to_sell,
                    "tokenOut": best_base_token,
                    "amountIn": amount_in,
                    "amountOutMin": int(amount_in * (1 - slippage_tolerance)),
                    "poolFee": 3000
                }
                trades.append(trade)
    
    return trades

def extract_swap_price(log, pool_address):
    """Extracts price from Uniswap V2 Swap event log using process_log()."""
    try:
        # Instantiate the Uniswap V2 Pair contract
        pair_contract = w3.eth.contract(address=to_checksum(pool_address), abi=UNISWAP_V2_PAIR_ABI)

        # Decode the event using process_log()
        decoded_event = pair_contract.events.Swap().process_log(log)

        # Extract amounts
        amount0_in = float(decoded_event["args"]["amount0In"])
        amount1_in = float(decoded_event["args"]["amount1In"])
        amount0_out = float(decoded_event["args"]["amount0Out"])
        amount1_out = float(decoded_event["args"]["amount1Out"])

        # Determine price (Avoid division by zero)
        if amount0_in > 0:
            price = amount0_out / amount0_in
        elif amount1_in > 0:
            price = amount1_out / amount1_in
        else:
            return None  # No valid swap data

        return price

    except Exception as e:
        print(f"❌ ERROR: Failed to decode swap log - {e}")
        return None



def fetch_recent_swaps(pair_id, from_block, to_block):
    """
    Fetch the latest swap event price for a given token within Uniswap V2 pools.
    """
    print(f"🔍 Fetching recent swaps for token: {pair_id}...")

    swap_event_signature = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

    try:
        # **Fetch Pool Address from Pool ID**
        pool_address = get_pool_address(pair_id)

        if not pool_address:
            logging.error(f"❌ Pool address not found for pool ID: {pool_id}")
            return []

        swap_event_signature = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

        # **Fetch Swap Logs from Polygon RPC**
        logs = w3.eth.get_logs({
            "fromBlock": w3.eth.block_number - FETCH_SWAPS_FROM_LATEST_XBLOCKS,  # Last 500 blocks (~10 minutes)
            "toBlock": "latest",
            "pair_address": pool_address,  # ✅ Now using pool address
            "topics": [swap_event_signature]  # Filter only Swap events
        })
        
        print(f"✅ Found fetch_recent_swaps {len(logs)} logs (After Filtering)")   

        decoded_swaps = []
        for log in logs:
            try:
                # Instantiate the contract
                pair_contract = w3.eth.contract(address= pool_address, abi=UNISWAP_V2_PAIR_ABI)

                # Process the log using Uniswap V2 Swap event
                decoded_event = pair_contract.events.Swap().process_log(log)
                # **Extract relevant data**
                # **Extract Swap Data (Fix for V2)**
                swap_data = {
                    "transactionHash": log.transactionHash.hex(),
                    "blockNumber": log.blockNumber,
                    "amount0In": float(decoded_event["args"]["amount0In"]),  # ✅ Corrected field name
                    "amount1In": float(decoded_event["args"]["amount1In"]),
                    "amount0Out": float(decoded_event["args"]["amount0Out"]),
                    "amount1Out": float(decoded_event["args"]["amount1Out"]),
                    "amountUSD": abs(float(decoded_event["args"]["amount0In"])) + abs(float(decoded_event["args"]["amount1In"]))  # ✅ Calculate USD value based on inputs
                }
                token_price = swap_data['amount0In'] / swap_data['amount1In'] if swap_data['amount1In'] > 0 else swap_data['amount0Out'] / swap_data['amount1Out']
                decoded_swaps.append(swap_data)
                return token_price

            except Exception as e:
                print(f"❌ ERROR: Failed to decode swap log for {pair_id} - {e}")
                continue

    except Exception as e:
        print(f"❌ ERROR: Failed to fetch logs for {pair_id} - {e}")

    print(f"❌ ERROR: No swap price found for token {pair_id}")
    return None  # ✅ Return None if no valid price found


def decide_trades(token_pairs, price_history, token_prices_in_usd, base_tokens, pools, base_token_prices,
                  threshold=0.02, slippage_tolerance=0.005, min_liquidity=10_000):
    """Scans ALL Uniswap v2 pools and finds the best tokens to trade dynamically."""
    global IF_FETCH_SWAPS_FROM_LATEST_XBLOCKS
    global held_tokens, held_token_prices
    trades = []

    X = 600  # ✅ Check last 10 hours dynamically
    min_X = 5  # ✅ Check last 5 minutes dynamically

    # ✅ Collect all unique tokens
    unique_tokens = set()
    for pair in token_pairs:
        unique_tokens.add(pair["token0"]["id"].lower())
        unique_tokens.add(pair["token1"]["id"].lower())
    
    for token_id in unique_tokens:
        if token_id in base_tokens.values():
            continue  # Skip base tokens
        
        token_price = token_prices_in_usd.get(token_id, 0)
        print(f"🔍 DEBUG: token_id = {token_id}, price = {token_price}")
        
        if token_price == 0:
            print(f"⚠️ WARNING: Missing price for {token_id}, skipping.")
            continue  # Skip if price is missing

        # **Price Change Calculation**
        historical_prices = price_history.get(token_id, {}).get("prices", [])
        
        # Append latest token price
        if token_price:
            historical_prices.append(token_price)

        # Keep only last X prices
        price_history[token_id] = {"prices": historical_prices[-X:]}
        
        # Ensure price change is calculated over 5 minutes to 10 hours
        if len(historical_prices) < min_X:
            continue
        
        # Extract price history
        token_price_history = [entry for entry in historical_prices]

        # Ensure we have enough history
        if len(token_price_history) < min_X:
            continue

        # Get price change over time
        price_change = (token_price - token_price_history[-min_X]) / token_price_history[-min_X]

        print(f"🔍 DEBUG: {token_id} Price Change = {price_change:.4%}, Threshold = {threshold:.4%}")
        
        # **Trade decision based on price movements**
        trade_direction = None
        temp_token_id = token_id
        temp_buy_price = 0
        temp_current_price = token_price
        temp_stop_loss_take_profit_buy_signal = ''
        smart_take_profit = False
        if price_change > threshold and token_id not in held_tokens:
            trade_direction = "buy"
            held_token_prices[token_id] = {"buy_price": token_price, "highest_price": token_price}
            held_tokens.add(token_id)
            save_held_tokens()  # ✅ Save after buying
            print(f"✅ BUY: {token_id} at {token_price:.2f}")
            temp_buy_price = token_price
            temp_stop_loss_take_profit_buy_signal = "Buy Signal"
            #log_trade("buy", token_id, token_price, 0, "Buy Signal")

        elif token_id in held_tokens:
            buy_price = held_token_prices[token_id]["buy_price"]
            current_price = token_price
            highest_price = held_token_prices[token_id].get("highest_price", buy_price)
            temp_buy_price = buy_price
            # Stop-loss: Sell if price drops 3% from buy price
            if (current_price - buy_price) / buy_price <= -0.03:
                trade_direction = "sell"
                print(f"🚨 STOP LOSS: Selling {token_id}")
                temp_stop_loss_take_profit_buy_signal = "Stop Loss"
                #profit_loss = (current_price - buy_price) / buy_price * 100
                #log_trade("sell", token_id, float(current_price), float(profit_loss), "Stop Loss")
           
            # Take profit: Sell if price increases by 7% from buy price]
            elif (current_price - buy_price) / buy_price >= 0.07:
                # Update highest price if the price continues to increase
                if current_price > highest_price:
                    held_token_prices[token_id]["highest_price"] = current_price
                # If price drops by 2% from the peak, sell
                if (held_token_prices[token_id]["highest_price"] - current_price) / held_token_prices[token_id]["highest_price"] >= 0.02:
                    trade_direction = "sell"
                    smart_take_profit = True
                    profit_percentage = ((current_price - buy_price) / buy_price) * 100
                    print(f"💰 SMART TAKE PROFIT: Selling {token_id} at {current_price:.2f} ({profit_percentage:.2f}% profit)")
                    temp_stop_loss_take_profit_buy_signal = "SMART TAKE PROFIT"
                    # Remove token from held tokens after selling
                    held_tokens.discard(token_id)
                    del held_token_prices[token_id]
                    save_held_tokens()

            
        if trade_direction:
            valid_pool_found = False
            preferred_base = None
            best_pool = None

            print(f"🔍 DEBUG: Looking for a valid pool for {token_id}, Trade Direction: {trade_direction}")
            token_name = "WETH"
            for base in ["WETH"]:
                base_token_id = base_tokens[base]["id"].lower()  # Convert to lowercase

                for pool in pools:
                    pool_token0 = pool["token0"]["id"].lower()
                    pool_token1 = pool["token1"]["id"].lower()

                    # Debugging: Show pool details
                    print(f"🧐 Checking Pool: {pool_token0} <-> {pool_token1} | Base: {base} ({base_token_id})")

                    # Buying case: Base token must be the input
                    if trade_direction == "buy":
                        if (pool_token0 == base_token_id and pool_token1 == token_id) or (pool_token1 == base_token_id and pool_token0 == token_id):
                            print(f"✅ Found Valid BUY Pool: {base_token_id} -> {token_id}")
                            preferred_base = base_token_id
                            best_pool = pool
                            valid_pool_found = True

                    # Selling case: Target token must be the input
                    elif trade_direction == "sell":
                        if (pool_token0 == token_id and pool_token1 == base_token_id) or (pool_token1 == token_id and pool_token0 == base_token_id):
                            print(f"✅ Found Valid SELL Pool: {token_id} -> {base_token_id}")
                            preferred_base = base_token_id
                            best_pool = pool
                            valid_pool_found = True

                if valid_pool_found:
                    token_name = base
                    break  # Stop once we find a valid pool

            if not valid_pool_found:
                if trade_direction == "buy":
                    held_tokens.discard(token_id)
                    held_token_prices.pop(token_id, None)
                    save_held_tokens()  # ✅ Save after selling
                print(f"❌ No valid base token found for {token_id}, skipping.")
                continue

            if valid_pool_found:
                amount_out_min = 0
                if trade_direction == "sell":
                    held_tokens.discard(token_id)
                    held_token_prices.pop(token_id, None)
                    save_held_tokens()  # ✅ Save after selling
                    # Keep only the last 3 prices to prevent old data affecting new buy signals
                    if token_id in price_history:
                        price_history[token_id]["prices"] = price_history[token_id]["prices"][-3:]  
                        save_price_history(price_history)  # ✅ Save updated price history
                        print(f"🔄 RESET PRICE HISTORY for {token_id}, keeping last 3 prices.")
                #amount_in = int((5 / base_tokens[base]["token_price"]) * (10 ** base_tokens[base]["decimals"]))  # 5 USD worth of base token
                if trade_direction == "buy":
                    # Keep original logic for buying: convert USD value into base token amount
                    amount_in = 2 / base_tokens[token_name]["token_price"] * (10 ** base_tokens[token_name]["decimals"])
                    #amount_in = 0.001 * (10 ** base_tokens[token_name]["decimals"])
                    amount_out_min = (3/token_price)*(1 - slippage_tolerance)
                    amount_out_min = amount_out_min*(10**get_token_decimals(token_id))
                    amount_out_min = int(amount_out_min)
                    log_trade("buy", token_id, token_price, 0, temp_stop_loss_take_profit_buy_signal)
                elif trade_direction == "sell":
                    amount_in = get_wallet_token_balance(token_id)
                    #amount_out_min = ((2/get_weth_price())/token_price)*(10**get_token_decimals(token_id))
                    amount_out_min = (((amount_in / (10**get_token_decimals(token_id))) * token_price)/BASE_TOKENS[token_name]["token_price"])*(1 - slippage_tolerance)
                    amount_out_min = amount_out_min*(10**base_tokens[token_name]["decimals"])
                    amount_out_min = int(amount_out_min)
                    profit_loss = (temp_current_price - temp_buy_price) / temp_buy_price * 100
                    log_trade("sell", temp_token_id, float(temp_current_price), float(profit_loss), temp_stop_loss_take_profit_buy_signal)
                trade = {
                    "tokenIn": token_id if trade_direction == "sell" else preferred_base,
                    "tokenOut": preferred_base if trade_direction == "sell" else token_id,
                    "amountIn": amount_in,
                    "amountOutMin": amount_out_min,
                    "poolFee": 3000,
                    "smart_take_profit": smart_take_profit
                }
                trades.append(trade)
            
    return trades


def fetch_all_token_prices():
    """Fetch all token prices in USD from The Graph API dynamically"""
    query = """
    {
      pairs(first: 1000) {
        token0 {
          id
          symbol
          derivedETH
        }
        token1 {
          id
          symbol
          derivedETH
        }
      }
      bundle(id: "1") {
        ethPrice
      }
    }
    """

    response = requests.post(UNISWAP_SUBGRAPH_URL, json={"query": query})
    data = response.json()

    if "data" not in data:
        raise ValueError("❌ ERROR: Invalid response from The Graph API")

    eth_price = float(data["data"]["bundle"]["ethPrice"])  # ETH/USD Price
    token_prices = {}

    # Extract token prices from pairs
    for pair in data["data"]["pairs"]:
        token0 = pair["token0"]
        token1 = pair["token1"]

        token0_id = token0["id"]
        token1_id = token1["id"]

        # Convert derived ETH prices to USD
        if token0["derivedETH"] is not None:
            token_prices[token0_id] = float(token0["derivedETH"]) * eth_price
        if token1["derivedETH"] is not None:
            token_prices[token1_id] = float(token1["derivedETH"]) * eth_price

    return token_prices




def determine_token_price(token_id, pools):
    """Determines the latest token price from Uniswap V2 swaps."""
    from_block = w3.eth.block_number - 500  # ✅ Last 500 blocks
    to_block = w3.eth.block_number  # ✅ Current block

    # Get price from latest swaps
    price = fetch_recent_swaps(token_id, from_block, to_block)

    if price:
        return price
    else:
        print(f"❌ ERROR: No swap price found for token {token_id}")
        return None


def determine_token_price_mock(token_id, pools):
    """Mock function to determine token price from liquidity pools."""
    try:
        for pool in pools:
            # ✅ Ensure `pool` is a dictionary
            if not isinstance(pool, dict):
                logging.warning(f"⚠️ Invalid pool format: {pool}")
                continue  # Skip invalid pools
            
            # ✅ Extract token addresses safely
            pool_token0 = pool.get("token0", {}).get("id")
            pool_token1 = pool.get("token1", {}).get("id")

            if not pool_token0 or not pool_token1:
                logging.warning(f"⚠️ Missing token0 or token1 in pool: {pool}")
                continue

            # ✅ Check if this pool contains the requested token
            if token_id == pool_token0 or token_id == pool_token1:
                reserve0 = float(pool.get("reserve0", 1.0))  # Use default value if missing
                reserve1 = float(pool.get("reserve1", 1.0))  # Use default value if missing
                
                if reserve0 > 0 and reserve1 > 0:
                    return reserve1 / reserve0  # ✅ Calculate token price (basic AMM pricing formula)

        return None  # ✅ Return None if no matching pool found

    except Exception as e:
        logging.warning(f"⚠️ Error in determining price for {token_id}: {str(e)}")
        return None



def execute_trades(trades):
    """Execute the trades by interacting with the smart contract."""
    if not trades:
        logger.info("No trades to execute.")
        return

    tokens_in = [trade["tokenIn"] for trade in trades]
    tokens_out = [trade["tokenOut"] for trade in trades]
    amounts_in = [int(trade["amountIn"]) for trade in trades]
    amounts_out_min = [int(trade["amountOutMin"]) for trade in trades]
    pool_fees = [trade["poolFee"] for trade in trades]
    tokens_in = [w3.to_checksum_address(token) for token in tokens_in]
    tokens_out = [w3.to_checksum_address(token) for token in tokens_out]
    smart_take_profits = [trade["smart_take_profit"] for trade in trades]

    logger.info(f"Tokens In: {tokens_in}")
    logger.info(f"Tokens Out: {tokens_out}")
    logger.info(f"Amounts In: {amounts_in}")
    logger.info(f"Amounts Out Min: {amounts_out_min}")
    logger.info(f"Pool Fees: {pool_fees}")
    

    
    for i in range(len(trades)):
        # Execute autoTrade
        autoTrade(w3.to_checksum_address(tokens_in[i]), w3.to_checksum_address(tokens_out[i]), amounts_in[i], amounts_out_min[i], pool_fees[i], smart_take_profits[i])
        print(i)
        print(tokens_in[i])
        print(tokens_out[i])
        trade_log = {
            #"transactionHash": tx_hash.hex(),
            "tokenIn": tokens_in[i],
            "tokenOut": tokens_out[i],
            "amountIn": amounts_in[i],
            "amountOutMin": amounts_out_min[i],
            "poolFee": pool_fees[i]
        }
        #log_trade(trade_log)



# **CACHE POOLS (Fetch Only Every 1 Hour)**
def fetch_all_pools(force_refresh=False):
    global LAST_POOL_FETCH_TIME
    now = time.time()

    # **Check if last fetch was within 1 hour**
    if not force_refresh and now - LAST_POOL_FETCH_TIME < 3600:
        try:
            with open(POOLS_CACHE_FILE, "r") as f:
                return json.load(f)  # Load from cache
        except FileNotFoundError:
            pass  # If cache not found, fetch fresh data

    # Fetch fresh pools
    query = """
   
  { 
  pairs(first: 1000, where: { 
    reserveUSD_gte: 999, 
    token0_: { symbol_in: ["POL", "USDC", "USDT", "WMATIC", "WETH", "WBTC"] }
  }) { 
    id 
    token0 { id symbol } 
    token1 { id symbol } 
    reserveUSD 
    reserve0   # ✅ Add reserve0
    reserve1   # ✅ Add reserve1
  } 
} 
    """
    try:
        response = requests.post(THEGRAPH_UNISWAP_URL, json={'query': query})
        response.raise_for_status()  # Raise error for bad response
        json_response = response.json()
        #print("🔍 Debug: Full API Response:", json_response)


        # **Check if response contains expected data**
        if "data" not in json_response or "pairs" not in json_response["data"]:
            raise ValueError(f"Unexpected response format: {json_response}")

        pools1 = json_response["data"]["pairs"]

        # Fetch fresh pools
        query = """
    { 
  pairs(first: 1000, where: { 
    reserveUSD_gte: 999, 
    token1_: { symbol_in: ["POL", "USDC", "USDT", "WMATIC", "WETH", "WBTC"] }
  }) { 
    id 
    token0 { id symbol } 
    token1 { id symbol } 
    reserveUSD 
    reserve0   # ✅ Add reserve0
    reserve1   # ✅ Add reserve1
  } 
} 
        """                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            
        response = requests.post(THEGRAPH_UNISWAP_URL, json={'query': query})
        response.raise_for_status()  # Raise error for bad response
        json_response = response.json()
        #print("🔍 Debug: Full API Response:", json_response)


        # **Check if response contains expected data**
        if "data" not in json_response or "pairs" not in json_response["data"]:
            raise ValueError(f"Unexpected response format: {json_response}")

        pools2 = json_response["data"]["pairs"]
   
        pools1.extend(pools2)
        pools = pools1

        LAST_POOL_FETCH_TIME = now

        # **Cache the response**
        with open(POOLS_CACHE_FILE, "w") as f:
            json.dump(pools, f)

        return pools

    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Network error fetching Uniswap pools: {e}")
    except ValueError as e:
        logging.error(f"⚠️ TheGraph response error: {e}")
    except Exception as e:
        logging.error(f"❌ Unexpected error fetching Uniswap pools: {e}")

    return []

import requests

def fetch_token_prices_from_graph():
    query = """
    {
      pairs(first: 1000, orderBy: reserveUSD, orderDirection: desc) {
        id
        token0 {
          id
          symbol
        }
        token1 {
          id
          symbol
        }
        reserveUSD
        token0Price
        token1Price
      }
    }
    """

    url = UNISWAP_SUBGRAPH_URL
    response = requests.post(url, json={"query": query})
    data = response.json()

    if "data" not in data or "pairs" not in data["data"]:
        print("❌ ERROR: No pairs data returned from The Graph API!")
        return {}

    token_prices = {}

    # ✅ Define Base Tokens (Important!)
    BASE_TOKENS = {
        "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359".lower(),
        "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F".lower(),
        "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270".lower(),
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619".lower(),
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6".lower()
    }

    # ✅ Iterate Over Pairs
    for pair in data["data"]["pairs"]:
        token0_id = pair["token0"]["id"].lower()  # Convert to lowercase for consistency
        token1_id = pair["token1"]["id"].lower()
        token0_price = float(pair["token0Price"])
        token1_price = float(pair["token1Price"])

        # ✅ Ensure token prices are not zero before storing them
        if token0_price == 0 or token1_price == 0:
            continue

        # ✅ If token0 is a base token, store token1's price
        if token0_id in BASE_TOKENS.values():
            token_prices[token1_id] = {
                "price_in_base": token1_price,
                "base_token": token0_id
            }

        # ✅ If token1 is a base token, store token0's price
        elif token1_id in BASE_TOKENS.values():
            token_prices[token0_id] = {
                "price_in_base": token0_price,
                "base_token": token1_id
            }

    #print("✅ ✅ ✅ Final Token Prices:", token_prices)
    return token_prices


def convert_to_usd(token_prices_in_base):
    """Convert token prices from base tokens to USD"""
    
    # ✅ Define base token prices in USD (adjust these values dynamically)
    base_token_prices = {
        "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359".lower(): 1.00,  # USDC
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F".lower(): 1.00,  # USDT
        "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270".lower(): 0.34,  # WMATIC
        "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619".lower(): 2700.00,  # WETH
        "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6".lower(): 98000.00  # WBTC
    }
    
    token_prices_in_usd = {}

    for token_id, data in token_prices_in_base.items():
        base_token = data["base_token"]
        price_in_base = data["price_in_base"]

        if base_token in base_token_prices:
            # ✅ Convert price to USD
            price_in_usd = price_in_base * base_token_prices[base_token]
            token_prices_in_usd[token_id.lower()] = price_in_usd
        else:
            print(f"❌ ERROR: No USD price available for base token {base_token}")

    #print("✅ ✅ ✅ Final Token Prices in USD:", token_prices_in_usd)
    return token_prices_in_usd



def calculate_all_token_prices(pairs, base_tokens, base_token_prices):
    """
    Compute the price of all tokens in USD, even if they are not paired with base tokens.
    """
    token_prices_in_usd = {}

    # Step 1: Initialize base tokens with known USD prices
    for base_token, base_info in base_tokens.items():
        token_prices_in_usd[base_info["id"].lower()] = base_info["token_price"]

    # Step 2: First pass - Direct price assignments from base tokens
    for pair in pairs:
        token0_id = pair["token0"]["id"].lower()
        token1_id = pair["token1"]["id"].lower()
        token0_price = float(pair["token0Price"])
        token1_price = float(pair["token1Price"])

        if token0_id in token_prices_in_usd:
            token_prices_in_usd[token1_id] = token_prices_in_usd[token0_id] * token0_price
        elif token1_id in token_prices_in_usd:
            token_prices_in_usd[token0_id] = token_prices_in_usd[token1_id] * token1_price

    # Step 3: Second pass - Fill missing values indirectly
    for _ in range(3):  # Repeat up to 3 times to fill missing prices via connected pairs
        for pair in pairs:
            token0_id = pair["token0"]["id"].lower()
            token1_id = pair["token1"]["id"].lower()
            token0_price = float(pair["token0Price"])
            token1_price = float(pair["token1Price"])

            if token0_id in token_prices_in_usd and token1_id not in token_prices_in_usd:
                token_prices_in_usd[token1_id] = token_prices_in_usd[token0_id] * token0_price
            elif token1_id in token_prices_in_usd and token0_id not in token_prices_in_usd:
                token_prices_in_usd[token0_id] = token_prices_in_usd[token1_id] * token1_price

    return token_prices_in_usd

def fetch_pairs():
# **Fetch data from TheGraph**
    try:
        query = """
        {
            pairs(first: 1000, where: { reserveUSD_gt: 999 }) {
                token0 { id symbol }
                token1 { id symbol }
                token0Price
                token1Price
            }
        }
        """
        response = requests.post(THEGRAPH_UNISWAP_URL, json={"query": query})
        response.raise_for_status()
        data = response.json()

        pools = data["data"]["pairs"]
        token_pairs = []

        for pool in pools:
            #print(pool)
            #print('POOLPOOL')
            token0_price = float(pool.get("token0Price", "0"))  # Ensure float
            token1_price = float(pool.get("token1Price", "0"))  # Ensure float

            token_pairs.append({
                "token0": {
                    "id": to_checksum(pool["token0"]["id"]),
                    "symbol": pool["token0"]["symbol"]
                },
                "token1": {
                    "id": to_checksum(pool["token1"]["id"]),
                    "symbol": pool["token1"]["symbol"]
                },
                "token0Price": token0_price,
                "token1Price": token1_price
            })
        return token_pairs
    except Exception as e:
        logging.error(f"❌ Unexpected error fetching Uniswap PAIR PRICES: {e}")
        


# ✅ Load Held Tokens from File (at startup)
def load_held_tokens():
    global held_tokens, held_token_prices

    if os.path.exists(HELD_TOKENS_FILE):
        with open(HELD_TOKENS_FILE, "r") as file:
            data = json.load(file)
            held_tokens = set(data.get("held_tokens", []))
            held_token_prices = data.get("held_token_prices", {})
        print(f"🔄 Loaded {len(held_tokens)} held tokens from file.")

# ✅ Save Held Tokens to File (every time we buy/sell)
def save_held_tokens():
    global held_tokens, held_token_prices
    
    data = {
        "held_tokens": list(held_tokens),
        "held_token_prices": held_token_prices
    }
    
    with open(HELD_TOKENS_FILE, "w") as file:
        json.dump(data, file, indent=4)

import time
import json
import requests
import logging

# Constants
BITQUERY_API_KEY = "YOUR_BITQUERY_API_KEY"
BITQUERY_URL = "https://graphql.bitquery.io/"
POOLS_CACHE_FILE = "pools_cache.json"
LAST_POOL_FETCH_TIME = 0

# **CACHE POOLS (Fetch Only Every 1 Hour)**
def fetch_all_pools_aerodrome(force_refresh=False):
    global LAST_POOL_FETCH_TIME
    now = time.time()

    # **Check if last fetch was within 1 hour**
    if not force_refresh and now - LAST_POOL_FETCH_TIME < 3600:
        try:
            with open(POOLS_CACHE_FILE, "r") as f:
                return json.load(f)  # Load from cache
        except FileNotFoundError:
            pass  # If cache not found, fetch fresh data

    # **Query 1: token0 must be a base token**
    query1 = """
    {
        EVM(network: base) {
            DEXTrades(
                where: {
                    Trade: { Dex: { ProtocolName: { is: "Aerodrome" } } },
                    Buy: { Currency: { Symbol: { in: ["USDC", "USDT", "WMATIC", "WETH", "WBTC"] } } }
                }
            ) {
                Trade {
                    Dex { SmartContract }
                    Buy { Currency { SmartContract Symbol } }
                    Sell { Currency { SmartContract Symbol } }
                    Liquidity
                }
            }
        }
    }
    """

    # **Query 2: token1 must be a base token**
    query2 = """
    {
        EVM(network: base) {
            DEXTrades(
                where: {
                    Trade: { Dex: { ProtocolName: { is: "Aerodrome" } } },
                    Sell: { Currency: { Symbol: { in: ["USDC", "USDT", "WMATIC", "WETH", "WBTC"] } } }
                }
            ) {
                Trade {
                    Dex { SmartContract }
                    Buy { Currency { SmartContract Symbol } }
                    Sell { Currency { SmartContract Symbol } }
                    Liquidity
                }
            }
        }
    }
    """

    try:
        # **Fetch Data for Query 1**
        response1 = requests.post(
            BITQUERY_URL,
            json={"query": query1},
            headers={"X-API-KEY": BITQUERY_API_KEY}
        )
        response1.raise_for_status()
        data1 = response1.json()

        # **Fetch Data for Query 2**
        response2 = requests.post(
            BITQUERY_URL,
            json={"query": query2},
            headers={"X-API-KEY": BITQUERY_API_KEY}
        )
        response2.raise_for_status()
        data2 = response2.json()

        # **Process Data**
        pools1 = parse_pools(data1)
        pools2 = parse_pools(data2)

        # **Combine Pools**
        pools1.extend(pools2)
        pools = pools1

        LAST_POOL_FETCH_TIME = now

        # **Cache the response**
        with open(POOLS_CACHE_FILE, "w") as f:
            json.dump(pools, f)

        return pools

    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Network error fetching Aerodrome pools: {e}")
    except ValueError as e:
        logging.error(f"⚠️ Bitquery response error: {e}")
    except Exception as e:
        logging.error(f"❌ Unexpected error fetching Aerodrome pools: {e}")

    return []

# **Helper function to parse response and match existing format**
def parse_pools(response_data):
    pools = []
    if "data" in response_data and "EVM" in response_data["data"]:
        for trade in response_data["data"]["EVM"]["DEXTrades"]:
            pool = {
                "id": trade["Trade"]["Dex"]["SmartContract"],  # DEX contract as ID
                "token0": {
                    "id": trade["Trade"]["Buy"]["Currency"]["SmartContract"],
                    "symbol": trade["Trade"]["Buy"]["Currency"]["Symbol"]
                },
                "token1": {
                    "id": trade["Trade"]["Sell"]["Currency"]["SmartContract"],
                    "symbol": trade["Trade"]["Sell"]["Currency"]["Symbol"]
                },
                "reserveUSD": trade["Trade"]["Liquidity"],  # Approximated Liquidity
            }
            pools.append(pool)
    return pools

def get_expected_output(token_in, token_out, amount_in, pools):
    """
    Estimate expected amount out from Uniswap V2 pools.
    """
    for pool in pools:
        pool_token0 = pool["token0"]["id"].lower()
        pool_token1 = pool["token1"]["id"].lower()

        if (token_in == pool_token0 and token_out == pool_token1) or (token_in == pool_token1 and token_out == pool_token0):
            # Get reserves
            reserve_in = float(pool["reserve0"]) if token_in == pool_token0 else float(pool["reserve1"])
            reserve_out = float(pool["reserve1"]) if token_in == pool_token0 else float(pool["reserve0"])

            # Apply Uniswap V2 formula
            expected_out = (amount_in * reserve_out) / (reserve_in + amount_in)
            return expected_out
    
    return 0  # No valid pool found


def get_token_decimals(token_address):
    """Fetches the number of decimals for an ERC-20 token."""

    ERC20_ABI_DECIMALS = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    }
]

    token_contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_ABI_DECIMALS)
    return token_contract.functions.decimals().call()


# ✅ Chainlink Price Feed Contract Addresses (Polygon)
PRICE_FEEDS = {
    "MATIC": "0x12129aAC52D6B0f0125677D4E1435633E61fD25f",
    "ETH": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
    "BTC": "0x64c911996D3c6aC71f9b455B1E8E7266BcbD848F",
}

# ✅ ABI for Chainlink Price Feed
CHAINLINK_AGGREGATOR_ABI = '[{"inputs":[],"name":"latestRoundData","outputs":[{"internalType":"uint80","name":"roundId","type":"uint80"},{"internalType":"int256","name":"answer","type":"int256"},{"internalType":"uint256","name":"startedAt","type":"uint256"},{"internalType":"uint80","name":"updatedAt","type":"uint80"},{"internalType":"uint80","name":"answeredInRound","type":"uint80"}],"stateMutability":"view","type":"function"}]'


def get_price(asset):
    """Fetch the latest price of an asset from Chainlink."""
    contract = w3.eth.contract(address=w3.to_checksum_address(PRICE_FEEDS[asset]), abi=CHAINLINK_AGGREGATOR_ABI)
    latest_data = contract.functions.latestRoundData().call()
    price = latest_data[1] / 1e8  # Chainlink prices have 8 decimal places
    return price

def update_base_tokens():
    """Update the token_price field in BASE_TOKENS using Chainlink."""
    global BASE_TOKENS
    for asset in ["WETH", "WBTC"]:
        try:
            price = get_price(asset.replace("W", ""))  # Remove 'W' to match Chainlink keys (MATIC, ETH, BTC)
            BASE_TOKENS[asset]["token_price"] = price
            print(f"✅ Updated {asset}: ${price:.2f}")
        except Exception as e:
            print(f"⚠️ Error fetching price for {asset}: {e}")


# Function to get WETH price from Chainlink (this must be implemented)
def get_weth_price():
    return BASE_TOKENS["WETH"]["token_price"]

def fetch_all_pools_coinbase_subgraph(force_refresh=False):
    global LAST_POOL_FETCH_TIME
    now = time.time()

    # **Check if last fetch was within 1 hour**
    if not force_refresh and now - LAST_POOL_FETCH_TIME < 3600:
        try:
            with open(POOLS_CACHE_FILE, "r") as f:
                return json.load(f)  # Load from cache
        except FileNotFoundError:
            pass  # If cache not found, fetch fresh data

    # ✅ **GraphQL Query for Coinbase Pools**
    query = """
    {
      pools(first: 1000, where: { liquidity_gte: "1000000",
          token0_: { symbol_in: ["WETH"] }
 }) {
        id
        token0 {
          id
          symbol
          decimals
          derivedETH
          volumeUSD
        }
        token1 {
          id
          symbol
          decimals
          derivedETH
          volumeUSD
        }
        liquidity
      }
    }
    """
    pairs = []
    try:
        response = requests.post(THEGRAPH_COINBASE_URL, json={'query': query})
        response.raise_for_status()  # Raise error for bad response
        json_response = response.json()
        #print("🔍 Debug: Full API Response:", json_response)

        # **Check if response contains expected data**
        if "data" not in json_response or "pools" not in json_response["data"]:
            raise ValueError(f"Unexpected response format: {json_response}")

        pools = json_response["data"]["pools"]
        LAST_POOL_FETCH_TIME = now

        # ✅ **Fetch WETH price from Chainlink**
        weth_price = get_weth_price()

        # ✅ **Convert Coinbase Pools to Uniswap V2 `pairs` Format**
        
        for pool in pools:
            token0 = pool["token0"]
            token1 = pool["token1"]

            # Get token decimals
            token0_decimals = int(token0["decimals"])
            token1_decimals = int(token1["decimals"])

            # Convert derivedETH to USD price
            token0_price = float(token0["derivedETH"]) * weth_price if float(token0["derivedETH"]) > 0 else 0
            token1_price = float(token1["derivedETH"]) * weth_price if float(token1["derivedETH"]) > 0 else 0

            # Construct Uniswap V2-like pair structure
            pair = {
                "id": pool["id"],
                "token0": {
                    "id": token0["id"],
                    "symbol": token0["symbol"],
                    "decimals": token0_decimals
                },
                "token1": {
                    "id": token1["id"],
                    "symbol": token1["symbol"],
                    "decimals": token1_decimals
                },
                "reserveUSD": float(pool["liquidity"]),
                "token0Price": token0_price,
                "token1Price": token1_price
            }
            pairs.append(pair)
    except Exception as e:
        print(f"⚠️ Error fetching POOLS: {e}")
        return []

###############PAIR2
# ✅ **GraphQL Query for Coinbase Pools**
    query = """
    {
      pools(first: 1000, where: { liquidity_gte: "1000000",
          token1_: { symbol_in: ["WETH"] }
 }) {
        id
        token0 {
          id
          symbol
          decimals
          derivedETH
          volumeUSD
        }
        token1 {
          id
          symbol
          decimals
          derivedETH
          volumeUSD
        }
        liquidity
      }
    }
    """

    try:
        response = requests.post(THEGRAPH_COINBASE_URL, json={'query': query})
        response.raise_for_status()  # Raise error for bad response
        json_response = response.json()
        #print("🔍 Debug: Full API Response:", json_response)

        # **Check if response contains expected data**
        if "data" not in json_response or "pools" not in json_response["data"]:
            raise ValueError(f"Unexpected response format: {json_response}")

        pools = json_response["data"]["pools"]
        LAST_POOL_FETCH_TIME = now

        # ✅ **Fetch WETH price from Chainlink**
        weth_price = get_weth_price()

        # ✅ **Convert Coinbase Pools to Uniswap V2 `pairs` Format**
        #pairs = []
        for pool in pools:
            token0 = pool["token0"]
            token1 = pool["token1"]

            # Get token decimals
            token0_decimals = int(token0["decimals"])
            token1_decimals = int(token1["decimals"])

            # Convert derivedETH to USD price
            token0_price = float(token0["derivedETH"]) * weth_price if float(token0["derivedETH"]) > 0 else 0
            token1_price = float(token1["derivedETH"]) * weth_price if float(token1["derivedETH"]) > 0 else 0

            # Construct Uniswap V2-like pair structure
            pair = {
                "id": pool["id"],
                "token0": {
                    "id": token0["id"],
                    "symbol": token0["symbol"],
                    "decimals": token0_decimals
                },
                "token1": {
                    "id": token1["id"],
                    "symbol": token1["symbol"],
                    "decimals": token1_decimals
                },
                "reserveUSD": float(pool["liquidity"]),
                "token0Price": token0_price,
                "token1Price": token1_price
            }
            pairs.append(pair)

        # **Cache the response**
        with open(POOLS_CACHE_FILE, "w") as f:
            json.dump(pairs, f)

        return pairs

    except Exception as e:
        print(f"⚠️ Error fetching POOLS: {e}")
        return []



def discover_token_pairs_coinbase(force_refresh=False):
    """Fetch Coinbase token pairs and return in Uniswap V2 format (caches results for 1 hour)."""
    global LAST_PAIR_FETCH_TIME
    now = time.time()

    # **Check if last fetch was within 1 hour**
    if not force_refresh and now - LAST_PAIR_FETCH_TIME < 3600:
        try:
            with open(TOKEN_PAIRS_CACHE_FILE, "r") as f:
                return json.load(f)  # Load from cache
        except FileNotFoundError:
            pass  # If cache not found, fetch fresh data

    # ✅ **GraphQL Query for Coinbase Token Pairs**
    query = """
    {
      pools(first: 1000, where: { liquidity_gte: "1000000" }) {
        id
        token0 {
          id
          symbol
          decimals
          derivedETH
          volumeUSD
        }
        token1 {
          id
          symbol
          decimals
          derivedETH
          volumeUSD
        }
        liquidity
      }
    }
    """

    try:
        response = requests.post(THEGRAPH_COINBASE_URL, json={"query": query})
        response.raise_for_status()
        data = response.json()

        # **Check if response contains expected data**
        if "data" not in data or "pools" not in data["data"]:
            raise ValueError(f"Unexpected response format: {data}")

        pools = data["data"]["pools"]
        token_pairs = []

        # ✅ **Fetch WETH price from Chainlink**
        weth_price = get_weth_price()

        for pool in pools:
            token0 = pool["token0"]
            token1 = pool["token1"]

            # Get token decimals
            token0_decimals = int(token0["decimals"])
            token1_decimals = int(token1["decimals"])

            # Convert derivedETH to USD price
            token0_price = float(token0["derivedETH"]) * weth_price if float(token0["derivedETH"]) > 0 else 0
            token1_price = float(token1["derivedETH"]) * weth_price if float(token1["derivedETH"]) > 0 else 0

            token_pairs.append({
                "token0": {
                    "id": token0["id"],
                    "symbol": token0["symbol"]
                },
                "token1": {
                    "id": token1["id"],
                    "symbol": token1["symbol"]
                },
                "pairId": pool["id"],
                "liquidity": int(float(pool["liquidity"])),
                "token0Price": token0_price,
                "token1Price": token1_price
            })

        # **Update Cache**
        LAST_PAIR_FETCH_TIME = now
        with open(TOKEN_PAIRS_CACHE_FILE, "w") as f:
            json.dump(token_pairs, f)

        return token_pairs

    except Exception as e:
        logging.error(f"❌ Error discovering token pairs: {e}")
        return []

def fetch_pairs_coinbase():
    """Fetch trading pairs from Coinbase and return in the same format as Uniswap V2."""
    try:
        query = """
        {
          pools(first: 1000, where: { liquidity_gte: "1000000" }) {
            token0 { id symbol decimals derivedETH }
            token1 { id symbol decimals derivedETH }
            token0Price
            token1Price
          }
        }
        """

        response = requests.post(THEGRAPH_COINBASE_URL, json={"query": query})
        response.raise_for_status()
        data = response.json()

        # **Check if response contains expected data**
        if "data" not in data or "pools" not in data["data"]:
            raise ValueError(f"Unexpected response format: {data}")

        pools = data["data"]["pools"]
        token_pairs = []

        for pool in pools:
            token0 = pool["token0"]
            token1 = pool["token1"]

            token0_price = float(pool.get("token0Price", "0"))  # Ensure float
            token1_price = float(pool.get("token1Price", "0"))  # Ensure float

            token_pairs.append({
                "token0": {
                    "id": token0["id"],
                    "symbol": token0["symbol"]
                },
                "token1": {
                    "id": token1["id"],
                    "symbol": token1["symbol"]
                },
                "token0Price": token0_price,
                "token1Price": token1_price
            })

        return token_pairs

    except Exception as e:
        logging.error(f"❌ Unexpected error fetching Coinbase PAIR PRICES: {e}")
        return []



def calculate_all_token_prices_coinbase(pairs, base_tokens):
    """
    Compute the price of all tokens in USD, even if they are not paired with base tokens.
    """
    token_prices_in_usd = {}

    # Step 1: Initialize base tokens with known USD prices
    for base_token, base_info in base_tokens.items():
        token_prices_in_usd[base_info["id"].lower()] = base_info["token_price"]

    # Step 2: First pass - Direct price assignments from base tokens
    for pair in pairs:
        token0_id = pair["token0"]["id"].lower()
        token1_id = pair["token1"]["id"].lower()
        token0_price = float(pair["token0Price"])
        token1_price = float(pair["token1Price"])

        if token0_id in token_prices_in_usd:
            token_prices_in_usd[token1_id] = token_prices_in_usd[token0_id] * token0_price
        elif token1_id in token_prices_in_usd:
            token_prices_in_usd[token0_id] = token_prices_in_usd[token1_id] * token1_price

    # Step 3: Second pass - Fill missing values indirectly
    for _ in range(3):  # Repeat up to 3 times to fill missing prices via connected pairs
        for pair in pairs:
            token0_id = pair["token0"]["id"].lower()
            token1_id = pair["token1"]["id"].lower()
            token0_price = float(pair["token0Price"])
            token1_price = float(pair["token1Price"])

            if token0_id in token_prices_in_usd and token1_id not in token_prices_in_usd:
                token_prices_in_usd[token1_id] = token_prices_in_usd[token0_id] * token0_price
            elif token1_id in token_prices_in_usd and token0_id not in token_prices_in_usd:
                token_prices_in_usd[token0_id] = token_prices_in_usd[token1_id] * token1_price

    return token_prices_in_usd



# **DETERMINE TOKEN PRICES (CACHE)**
TOKEN_PRICE_CACHE = {}

# Main loop


TOKEN_PRICES = {
    BASE_TOKENS["USDC"]["id"]: 1.00,  # USDC = $1.00
    BASE_TOKENS["WETH"]["id"]: 3000.00,  # WETH = $2500.00
    BASE_TOKENS["USDT"]["id"]: 1.0,  # WMATIC = $0.40
    BASE_TOKENS["WBTC"]["id"]: 100000.00,  # WETH = $2500.00
}

# Load mock data from the JSON file
#with open("mock_data_polygon_final.json", "r") as f:
#    mock_data = json.load(f)
#for pool in mock_data["pools"]:
#    print(f"🔍 Pool Liquidity Debug: {pool.get('pairId', 'MISSING pairId')} -> Liquidity: {pool.get('liquidity', 'MISSING')}")
# Extract data from the mock JSON
#token_prices = mock_data["token_prices"]
#price_history = mock_data["price_history"]
# Define pools (Mock pool structure should match what's expected in your function)
#pools = mock_data["pools"]
#token_pairs=mock_data["token_pairs"]
# **Initialize price history**
price_history = load_price_history()
#held_tokens = set()
# Dictionary to track the purchase price of tokens
#held_token_prices = {}  
# { token_id: buy_price }
#token_pairs = discover_token_pairs()
#print(token_pairs)
#pools = fetch_all_pools()
#print(pools)
# Fetch all token prices dynamically
#token_prices_in_base = fetch_token_prices_from_graph()
#print("✅ All Token Prices in token_prices_in_base:", token_prices_in_base)
# Define base token prices (manually or via Chainlink)
# ✅ Correct way to set base token prices
# Convert prices to USD
#token_prices_in_usd = convert_to_usd(token_prices_in_base)
#print("✅ All Token Prices in token_prices_in_usd:", token_prices_in_usd)
#token_prices_in_usd = calculate_all_token_prices(token_pairs, BASE_TOKENS, base_token_prices)
#print(token_prices_in_usd)
# ✅ Load held tokens when script starts
load_held_tokens()
while True:
    try:
        update_base_tokens()
        pools = fetch_all_pools_coinbase_subgraph()
        token_pairs = discover_token_pairs_coinbase()
        pairs = fetch_pairs_coinbase()
        token_prices_in_usd = calculate_all_token_prices_coinbase(pairs, BASE_TOKENS)
        trades = decide_trades(token_pairs= token_pairs, price_history=price_history, token_prices_in_usd=token_prices_in_usd,
                           base_tokens=BASE_TOKENS, pools=pools, base_token_prices= TOKEN_PRICES,
                           threshold=0.03, slippage_tolerance=0.2, min_liquidity=500_000)
        print(f"✅ {len(trades)} Trades Generated!")
        print(trades)
        execute_trades(trades)
        save_price_history(price_history)
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        
    time.sleep(60)  # Check prices and execute trades every minute
    
