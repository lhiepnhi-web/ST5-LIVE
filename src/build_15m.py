import os
import pandas as pd

INPUT_DIR = "data/INTRADAY_5M"
OUTPUT_DIR = "data/INTRADAY_15M"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("ST5 — BUILD 15M FROM 5M")
print("=" * 70)

files = sorted(
    f for f in os.listdir(INPUT_DIR)
    if f.endswith("_5m.csv")
)

success = []
failed = []

for i, filename in enumerate(files, 1):

    ticker = filename.replace("_5m.csv", "")

    print(f"[{i}/{len(files)}] {ticker}")

    try:
        path = os.path.join(INPUT_DIR, filename)

        df = pd.read_csv(path)

        df["Date"] = pd.to_datetime(df["Date"])

        df = df.sort_values("Date")
        df = df.drop_duplicates("Date")

        df = df.set_index("Date")

        df15 = df.resample(
            "15min",
            origin="start_day"
        ).agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        })

        df15 = df15.dropna(
            subset=["Open", "High", "Low", "Close"]
        )

        df15 = df15.reset_index()

        output = os.path.join(
            OUTPUT_DIR,
            f"{ticker}_15m.csv"
        )

        df15.to_csv(
            output,
            index=False
        )

        print(f"  OK — {len(df15):,} nến 15M")

        success.append(ticker)

    except Exception as e:

        print(f"  LOI — {type(e).__name__}: {e}")
        failed.append(ticker)

print()
print("=" * 70)
print("KET QUA")
print("=" * 70)
print(f"Thanh cong : {len(success)}")
print(f"That bai   : {len(failed)}")

print()
print("FAILED:")
print(failed) 
