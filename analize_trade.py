import pandas as pd

# Load trade data
def analyze_trades(file_path="trade_history.csv"):
    df = pd.read_csv(file_path)

    # ✅ Count Trade Types
    total_buys = len(df[df["trade_type"] == "buy"])
    total_sells = len(df[df["trade_type"] == "sell"])
    total_take_profits = len(df[df["reason"] == "Take Profit"])
    total_stop_losses = len(df[df["reason"] == "Stop Loss"])

    # ✅ Calculate Profit/Loss
    total_profit_loss = df["profit_loss"].sum()

    # ✅ Display Summary
    summary = {
        "Total Trades": len(df),
        "Total Buys": total_buys,
        "Total Sells": total_sells,
        "Take Profits": total_take_profits,
        "Stop Losses": total_stop_losses,
        "Total Profit (%)": total_profit_loss,
        "Total Profit (if $10 per trade)": total_profit_loss * 10 / 100,
        "Total Profit (if $100 per trade)": total_profit_loss * 100 / 100
    }

    print("📊 Trade Performance Summary:")
    for key, value in summary.items():
        print(f"{key}: {value}")

# Run analysis
analyze_trades()

