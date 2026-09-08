"""
ST5 LIVE — MSR Step 5 Engine Test

Purpose:
- Import msr_step5_engine.py
- Load MSR historical CSV
- Run engine
- Validate engine integrity
- Print PASS / FAIL
"""

from pathlib import Path
import sys
import pandas as pd


# ============================================================
# PATH
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ============================================================
# IMPORT ENGINE
# ============================================================

try:
    import msr_step5_engine as engine
except Exception as e:
    print("ENGINE IMPORT: FAIL")
    print(f"Error: {e}")
    raise


# ============================================================
# DATA LOCATION
# ============================================================

DATA_CANDIDATES = [
    ROOT / "data" / "MSR.csv",
    ROOT / "data" / "msr.csv",
]


def find_msr_file():
    for path in DATA_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "MSR.csv not found in repo data/ directory."
    )


# ============================================================
# LOAD DATA
# ============================================================

data_path = find_msr_file()

print("=" * 80)
print("ST5 LIVE — MSR STEP 5 ENGINE TEST")
print("=" * 80)

print(f"Repository : {ROOT}")
print(f"Data       : {data_path}")

df = pd.read_csv(data_path)

print(f"Rows       : {len(df):,}")


# ============================================================
# BASIC DATA CHECK
# ============================================================

required_columns = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]

missing = [
    col for col in required_columns
    if col not in df.columns
]

if missing:
    raise AssertionError(
        f"Missing required columns: {missing}"
    )

print("Required columns : PASS")


# ============================================================
# RUN ENGINE
# ============================================================

result = engine.run_msr(df)

if not isinstance(result, dict):
    raise AssertionError(
        "run_msr() must return a dictionary."
    )

if "data" not in result:
    raise AssertionError(
        "Engine result missing 'data'."
    )

if "trades" not in result:
    raise AssertionError(
        "Engine result missing 'trades'."
    )


data = result["data"]
trades = result["trades"]

print()
print("ENGINE EXECUTION : PASS")


# ============================================================
# SIGNAL CHECK
# ============================================================

signal_count = engine.get_signal_count(data)

print()
print("[SIGNAL]")
print(f"ENTRY_SIGNAL : {signal_count}")

if signal_count < 0:
    raise AssertionError("Invalid signal count.")

print("Signal generation : PASS")


# ============================================================
# TRADE CHECK
# ============================================================

if trades is None:
    raise AssertionError("Trades object is None.")

if not isinstance(trades, pd.DataFrame):
    raise AssertionError(
        "Trades must be a pandas DataFrame."
    )

print()
print("[TRADES]")
print(f"Trades : {len(trades)}")

if len(trades) == 0:
    raise AssertionError(
        "Engine produced zero trades."
    )


# ============================================================
# REQUIRED TRADE COLUMNS
# ============================================================

required_trade_columns = [
    "TradeID",
    "EntryDate",
    "ExitDate",
    "EntryPrice",
    "ExitPrice",
    "HoldBars",
    "Return",
    "ExitReason",
]

missing_trade_columns = [
    col
    for col in required_trade_columns
    if col not in trades.columns
]

if missing_trade_columns:
    raise AssertionError(
        f"Missing trade columns: {missing_trade_columns}"
    )

print("Trade columns : PASS")


# ============================================================
# TRADE ID INTEGRITY
# ============================================================

trade_ids = trades["TradeID"].tolist()

expected_ids = list(range(1, len(trades) + 1))

if trade_ids != expected_ids:
    raise AssertionError(
        "Trade IDs are not sequential."
    )

if trades["TradeID"].is_unique is not True:
    raise AssertionError(
        "Trade IDs are not unique."
    )

print("Trade ID integrity : PASS")


# ============================================================
# ENTRY / EXIT DATE
# ============================================================

trades["EntryDate"] = pd.to_datetime(trades["EntryDate"])
trades["ExitDate"] = pd.to_datetime(trades["ExitDate"])

if (trades["ExitDate"] < trades["EntryDate"]).any():
    raise AssertionError(
        "Found negative holding period."
    )

print("Date integrity : PASS")


# ============================================================
# NO OVERLAP
# ============================================================

ordered = trades.sort_values("EntryDate").reset_index(drop=True)

overlap_count = 0

for i in range(1, len(ordered)):
    previous_exit = ordered.loc[i - 1, "ExitDate"]
    current_entry = ordered.loc[i, "EntryDate"]

    if current_entry <= previous_exit:
        overlap_count += 1

print(f"Overlap count : {overlap_count}")

if overlap_count != 0:
    raise AssertionError(
        f"Found {overlap_count} overlapping trades."
    )

print("No-overlap integrity : PASS")


# ============================================================
# EXIT DISTRIBUTION
# ============================================================

exit_counts = trades["ExitReason"].value_counts()

tp20 = int(exit_counts.get("TP20", 0))
law = int(exit_counts.get("LOSS_OF_LAW", 0))
max_hold = int(exit_counts.get("MAX_HOLD", 0))
eod = int(exit_counts.get("END_OF_DATA", 0))

print()
print("[EXIT DISTRIBUTION]")
print(f"TP20          : {tp20}")
print(f"LOSS_OF_LAW   : {law}")
print(f"MAX_HOLD      : {max_hold}")
print(f"END_OF_DATA   : {eod}")

if tp20 + law + max_hold + eod != len(trades):
    raise AssertionError(
        "Exit reason accounting mismatch."
    )

print("Exit accounting : PASS")


# ============================================================
# RETURN INTEGRITY
# ============================================================

if trades["Return"].isna().any():
    raise AssertionError(
        "Trade Return contains NaN."
    )

if not pd.api.types.is_numeric_dtype(trades["Return"]):
    raise AssertionError(
        "Trade Return is not numeric."
    )

print("Return integrity : PASS")


# ============================================================
# TP20 INTEGRITY
# ============================================================

tp_trades = trades[
    trades["ExitReason"] == "TP20"
].copy()

tp_errors = 0

for _, row in tp_trades.iterrows():

    target = row["EntryPrice"] * 1.20

    if row["ExitPrice"] > target + 1e-9:
        tp_errors += 1

if tp_errors:
    raise AssertionError(
        f"TP20 exit-price errors: {tp_errors}"
    )

print("TP20 integrity : PASS")


# ============================================================
# MAX HOLD INTEGRITY
# ============================================================

max_hold_errors = 0

for _, row in trades[
    trades["ExitReason"] == "MAX_HOLD"
].iterrows():

    if row["HoldBars"] < 10:
        max_hold_errors += 1

if max_hold_errors:
    raise AssertionError(
        f"MAX_HOLD early exits: {max_hold_errors}"
    )

print("MAX_HOLD integrity : PASS")


# ============================================================
# SUMMARY
# ============================================================

summary = engine.summarize_trades(trades)

print()
print("=" * 80)
print("ENGINE SUMMARY")
print("=" * 80)

if isinstance(summary, dict):
    for key, value in summary.items():
        print(f"{key:<25}: {value}")
else:
    print(summary)


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 80)
print("MSR STEP 5 ENGINE TEST : PASS")
print("=" * 80) 
