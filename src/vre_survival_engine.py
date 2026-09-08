# ============================================================
# VRE SURVIVAL V1.8 — STEP 2
# STATE ENGINE
#
# Frozen rules:
# ENTRY:
#   ADX14 > 40 AND MACD_HIST_SLOPE > 0
#
# EXIT:
#   MACD_HIST <= 0 OR ROC10 <= 2 OR ADX14 <= 30
#
# Step 2:
#   - Daily data
#   - 7 CORE tickers
#   - Persistent state
#   - No Telegram
#   - No Paper Trade
#   - No Auto Order
#   - Do not modify MSR/CII
# ============================================================

from pathlib import Path
from datetime import datetime, timezone

import json
import numpy as np
import pandas as pd

from vnstock import Quote


# ============================================================
# CONFIG
# ============================================================

TICKERS = [
    "VIX",
    "ABB",
    "AAS",
    "SHS",
    "NKG",
    "HPG",
    "DXG",
]

SOURCE = "KBS"

ROC10_MIN = 2.0

ENTRY_ADX_MIN = 40.0
EXIT_ADX_MIN = 30.0

DATA_START = "2010-01-01"

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT_DIR / "data"
STATE_FILE = STATE_DIR / "vre_survival_state.json"


# ============================================================
# HELPERS
# ============================================================

def normalize_columns(df):
    df = df.copy()

    rename_map = {}

    for c in df.columns:
        lc = str(c).lower().strip()

        if lc in ["time", "date", "datetime"]:
            rename_map[c] = "date"
        elif lc == "open":
            rename_map[c] = "open"
        elif lc == "high":
            rename_map[c] = "high"
        elif lc == "low":
            rename_map[c] = "low"
        elif lc in ["close", "closing_price"]:
            rename_map[c] = "close"
        elif lc in ["volume", "vol"]:
            rename_map[c] = "volume"

    df = df.rename(columns=rename_map)

    required = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}. "
            f"Available: {list(df.columns)}"
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(
        subset=[
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    )

    df = df.sort_values("date")
    df = df.drop_duplicates("date")
    df = df.reset_index(drop=True)

    return df


# ============================================================
# INDICATORS — EXACT ST5 V1.8
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # ROC10
    # --------------------------------------------------------

    df["ROC10"] = (
        df["close"] / df["close"].shift(10) - 1
    ) * 100.0

    # --------------------------------------------------------
    # MACD 12 / 26 / 9
    # --------------------------------------------------------

    ema12 = df["close"].ewm(
        span=12,
        adjust=False,
        min_periods=12
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False,
        min_periods=26
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACD_SIGNAL"] = df["MACD"].ewm(
        span=9,
        adjust=False,
        min_periods=9
    ).mean()

    df["MACD_HIST"] = (
        df["MACD"] - df["MACD_SIGNAL"]
    )

    # Current histogram - previous histogram
    df["MACD_HIST_SLOPE"] = (
        df["MACD_HIST"]
        - df["MACD_HIST"].shift(1)
    )

    # --------------------------------------------------------
    # ADX14 — EXACT ST5 EWM
    # --------------------------------------------------------

    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    df["TR"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where(
        (up_move > down_move) & (up_move > 0),
        up_move,
        0.0
    )

    minus_dm = np.where(
        (down_move > up_move) & (down_move > 0),
        down_move,
        0.0
    )

    plus_dm = pd.Series(
        plus_dm,
        index=df.index
    )

    minus_dm = pd.Series(
        minus_dm,
        index=df.index
    )

    atr = df["TR"].ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    plus_di = (
        100.0
        * plus_dm.ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14
        ).mean()
        / atr
    )

    minus_di = (
        100.0
        * minus_dm.ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14
        ).mean()
        / atr
    )

    denominator = plus_di + minus_di

    dx = (
        100.0
        * (plus_di - minus_di).abs()
        / denominator.replace(0, np.nan)
    )

    df["ADX14"] = dx.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    return df


# ============================================================
# V1.8 DECISION
# ============================================================

def evaluate_v18(row):

    adx = float(row["ADX14"])
    hist = float(row["MACD_HIST"])
    slope = float(row["MACD_HIST_SLOPE"])
    roc10 = float(row["ROC10"])

    # --------------------------------------------------------
    # EXIT
    # --------------------------------------------------------

    exit_signal = (
        hist <= 0
        or roc10 <= ROC10_MIN
        or adx <= EXIT_ADX_MIN
    )

    if exit_signal:
        return "EXIT"

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    entry_signal = (
        adx > ENTRY_ADX_MIN
        and slope > 0
    )

    if entry_signal:
        return "BUY"

    # --------------------------------------------------------
    # Otherwise
    # --------------------------------------------------------

    return "HOLD"


# ============================================================
# LOAD STATE
# ============================================================

def load_state():

    if not STATE_FILE.exists():
        return {
            "version": "V1.8",
            "updated_at": None,
            "tickers": {}
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            state = json.load(f)

        if not isinstance(state, dict):
            raise ValueError("Invalid state format")

        if "tickers" not in state:
            state["tickers"] = {}

        return state

    except Exception as e:

        print(
            f"[WARNING] Cannot load state: {e}"
        )

        return {
            "version": "V1.8",
            "updated_at": None,
            "tickers": {}
        }


# ============================================================
# SAVE STATE
# ============================================================

def save_state(state):

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    tmp_file = STATE_FILE.with_suffix(".tmp")

    with open(
        tmp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )

    tmp_file.replace(STATE_FILE)


# ============================================================
# DOWNLOAD DAILY
# ============================================================

def download_daily(ticker):

    print()
    print(
        f"[{ticker}] Download Daily..."
    )

    q = Quote(
        symbol=ticker,
        source=SOURCE
    )

    df = q.history(
        start=DATA_START,
        end=datetime.now().strftime("%Y-%m-%d"),
        interval="1D"
    )

    if df is None or len(df) == 0:
        raise ValueError(
            f"{ticker}: empty data"
        )

    df = normalize_columns(df)

    df = calculate_indicators(df)

    return df


# ============================================================
# PROCESS ONE TICKER
# ============================================================

def process_ticker(ticker, state):

    df = download_daily(ticker)

    valid = df.dropna(
        subset=[
            "ROC10",
            "MACD_HIST",
            "MACD_HIST_SLOPE",
            "ADX14",
        ]
    )

    if len(valid) == 0:
        raise ValueError(
            f"{ticker}: no valid indicator rows"
        )

    row = valid.iloc[-1]

    decision = evaluate_v18(row)

    last_date = row["date"]

    # Convert timestamp safely to string
    if hasattr(last_date, "isoformat"):
        last_date_str = last_date.isoformat()
    else:
        last_date_str = str(last_date)

    previous = state["tickers"].get(
        ticker,
        {}
    )

    previous_decision = previous.get(
        "decision"
    )

    decision_changed = (
        previous_decision is None
        or previous_decision != decision
        or previous.get("last_date") != last_date_str
    )

    ticker_state = {
        "last_date": last_date_str,
        "close": float(row["close"]),
        "adx14": float(row["ADX14"]),
        "macd_hist": float(row["MACD_HIST"]),
        "macd_hist_slope": float(
            row["MACD_HIST_SLOPE"]
        ),
        "roc10": float(row["ROC10"]),
        "decision": decision,
        "previous_decision": previous_decision,
        "decision_changed": bool(decision_changed),
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    state["tickers"][ticker] = ticker_state

    print()
    print("-" * 78)
    print(ticker)

    print(
        f"Last date : {last_date_str}"
    )

    print(
        f"Close     : {row['close']:.4f}"
    )

    print(
        f"ADX14     : {row['ADX14']:.4f}"
    )

    print(
        f"MACD_HIST : {row['MACD_HIST']:.6f}"
    )

    print(
        f"HIST_SLOPE: {row['MACD_HIST_SLOPE']:.6f}"
    )

    print(
        f"ROC10     : {row['ROC10']:.4f}"
    )

    print(
        f"PREVIOUS  : {previous_decision}"
    )

    print(
        f"DECISION  : {decision}"
    )

    print(
        f"CHANGED   : {decision_changed}"
    )

    return ticker_state


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 78)
    print(
        "VRE SURVIVAL V1.8 — STEP 2"
    )
    print(
        "STATE ENGINE"
    )
    print("=" * 78)

    print(
        f"State file : {STATE_FILE}"
    )

    state = load_state()

    state["version"] = "V1.8"

    success = 0
    failed = 0

    results = []

    for ticker in TICKERS:

        try:

            result = process_ticker(
                ticker,
                state
            )

            results.append(
                (ticker, result)
            )

            success += 1

        except Exception as e:

            failed += 1

            print()
            print(
                f"[ERROR] {ticker}: {e}"
            )

    state["updated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    save_state(state)

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 78)
    print(
        "VRE SURVIVAL V1.8 — STEP 2 SUMMARY"
    )
    print("=" * 78)

    print(
        f"{'Ticker':<8}"
        f"{'LastDate':<28}"
        f"{'Decision':<10}"
        f"{'Changed':<10}"
        f"{'Status'}"
    )

    for ticker, result in results:

        print(
            f"{ticker:<8}"
            f"{result['last_date']:<28}"
            f"{result['decision']:<10}"
            f"{str(result['decision_changed']):<10}"
            f"OK"
        )

    print()
    print(
        f"Success : {success}"
    )

    print(
        f"Failed  : {failed}"
    )

    print()
    print(
        f"STATE FILE: {STATE_FILE}"
    )

    print()
    print("=" * 78)
    print(
        "STEP 2 FINISHED"
    )
    print("=" * 78)

    print(
        "Chua Telegram."
    )

    print(
        "Chua Paper Trade."
    )

    print(
        "Chua Auto Order."
    )

    print(
        "Chua sua MSR/CII."
    )


if __name__ == "__main__":
    main() 
