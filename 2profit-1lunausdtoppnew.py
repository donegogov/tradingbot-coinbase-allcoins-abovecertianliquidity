import pandas as pd

# Load the CSV
df = pd.read_csv("real_luna_arbitrage.csv")

bins = [0, 0.01, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.14, 0.17, 0.2,0.25,0.3,0.35,0.4,0.45,0.5, float("inf")]
labels = ["<0.01", "0.01–0.03", "0.03–0.04", "0.04–0.05", "0.05–0.06",
          "0.06–0.07", "0.07–0.08", "0.08–0.09", "0.09–0.1", "0.1–0.14",
          "0.14–0.17", "0.17–0.2","0.2-0.25","0.25-0.3","0.3-0.35",
          "0.35-0.4","0.4-0.45","0.45-0.5", "0.5+"]

# Create Profit Range column
df["Profit Range"] = pd.cut(df["Profit (USDT)"], bins=bins, labels=labels, include_lowest=True)

# Group and filter
grouped = df.groupby(["Profit Range", "Buy From", "Sell To"]).size().reset_index(name="Count")
filtered = grouped[grouped["Count"] > 1]

# Sort so all ranges appear together
filtered = filtered.sort_values(by=["Profit Range", "Count"], ascending=[True, False])

# Print clean
print("\n📊 All Arbitrage Trades with Count > 1 (Grouped by Range):\n")
print(filtered.to_string(index=False))

# Optional: Save to CSV
filtered.to_csv("1luna_profit_summary_filtered.csv", index=False)

