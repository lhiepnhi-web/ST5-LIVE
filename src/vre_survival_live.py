# ============================================================
# VRE SURVIVAL V1.8 — BƯỚC 1
# DAILY SIGNAL ENGINE — TECHNICAL TEST ONLY
# ============================================================
#
# MỤC TIÊU:
#   1. Lấy dữ liệu Daily từ KBS
#   2. Tính indicator đúng luật V1.8
#   3. Kiểm tra ENTRY / EXIT
#   4. In trạng thái 7 mã Survivor
#
# CHƯA:
#   - Telegram
#   - State
#   - Paper trade
#   - Auto order
#   - Sửa MSR
#   - Sửa CII
#
# V1.8 FROZEN:
#   ENTRY:
#       ADX14 > 40
#       AND MACD_HIST_SLOPE > 0
#
#   EXIT:
#       MACD_HIST <= 0
#       OR ROC10 <= 2
#       OR ADX14 <= 30
#
# ============================================================

import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from vnstock import Quote
except Exception as e:
    print("ERROR: Không import được vnstock.")
    print(e)
    sys.exit(1)


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

LOOKBACK_DAYS = 3000

# V1.8 FROZEN
ADX_ENTRY = 40.0
ADX_EXIT = 30.0
ROC_EXIT = 2.0


# ============================================================
# LOAD DAILY DATA
# ============================================================

def load_daily(symbol):
    """
    Lấy Daily OHLCV từ KBS.

    Không dùng intraday.
    Không dùng VNINDEX.
    """

    print(f"\n[{symbol}] Download Daily...")

    try:
        q = Quote(
            symbol=symbol,
            source=SOURCE
        )

        df = q.history(
            start="2010-01-01",
            end=datetime.now().strftime("%Y-%m-%d"),
            interval="1D"
        )

    except Exception as e:
        print(f"[{symbol}] ERROR DOWNLOAD: {e}")
        return None

    if df is None or len(df) == 0:
        print(f"[{symbol}] ERROR: Không có dữ liệu.")
        return None

    df = df.copy()

    # --------------------------------------------------------
    # Chuẩn hóa tên cột
    # --------------------------------------------------------

    df.columns = [str(c).strip().lower() for c in df.columns]

    rename_map = {
        "time": "date",
        "timestamp": "date",
        "trading_date": "date",
    }

    df = df.rename(columns=rename_map)

    required = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        print(f"[{symbol}] ERROR thiếu cột: {missing}")
        print("Columns:", list(df.columns))
        return None

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    if "date" in df.columns:
        df["date"] = pd.to_datetime(
            df["date"],
            errors="coerce"
        )
    else:
        df["date"] = pd.RangeIndex(len(df))

    # --------------------------------------------------------
    # Numeric
    # --------------------------------------------------------

    for c in required:
        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Clean
    # --------------------------------------------------------

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
    df = df.drop_duplicates(
        subset=["date"],
        keep="last"
    )

    df = df.reset_index(drop=True)

    if len(df) < 100:
        print(
            f"[{symbol}] WARNING: chỉ có {len(df)} rows."
        )

    return df


# ============================================================
# INDICATORS — EXACT ST5 STYLE
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # ========================================================
    # ROC10
    # ========================================================

    df["ROC10"] = (
        (df["close"] / df["close"].shift(10) - 1.0)
        * 100.0
    )

    # ========================================================
    # MACD 12 / 26 / 9
    # ========================================================

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

    # ========================================================
    # MACD HIST SLOPE
    # ========================================================

    df["MACD_HIST_SLOPE"] = (
        df["MACD_HIST"]
        - df["MACD_HIST"].shift(1)
    )

    # ========================================================
    # ADX14 — ST5 EWM
    # ========================================================

    prev_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()

    df["TR"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = (
        df["high"]
        - df["high"].shift(1)
    )

    down_move = (
        df["low"].shift(1)
        - df["low"]
    )

    df["+DM"] = np.where(
        (up_move > down_move) &
        (up_move > 0),
        up_move,
        0.0
    )

    df["-DM"] = np.where(
        (down_move > up_move) &
        (down_move > 0),
        down_move,
        0.0
    )

    atr = df["TR"].ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    plus_dm = pd.Series(
        df["+DM"],
        index=df.index
    ).ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    minus_dm = pd.Series(
        df["-DM"],
        index=df.index
    ).ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    df["+DI14"] = (
        100.0
        * plus_dm
        / atr
    )

    df["-DI14"] = (
        100.0
        * minus_dm
        / atr
    )

    di_sum = (
        df["+DI14"]
        + df["-DI14"]
    )

    df["DX14"] = np.where(
        di_sum != 0,
        100.0
        * (
            (
                df["+DI14"]
                - df["-DI14"]
            ).abs()
            / di_sum
        ),
        np.nan
    )

    df["ADX14"] = pd.Series(
        df["DX14"],
        index=df.index
    ).ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    return df


# ============================================================
# V1.8 SIGNAL
# ============================================================

def evaluate_signal(df):

    row = df.iloc[-1]

    adx = row["ADX14"]
    macd_hist = row["MACD_HIST"]
    macd_slope = row["MACD_HIST_SLOPE"]
    roc10 = row["ROC10"]

    entry = (
        pd.notna(adx)
        and pd.notna(macd_slope)
        and adx > ADX_ENTRY
        and macd_slope > 0
    )

    exit_signal = (
        (
            pd.notna(macd_hist)
            and macd_hist <= 0
        )
        or
        (
            pd.notna(roc10)
            and roc10 <= ROC_EXIT
        )
        or
        (
            pd.notna(adx)
            and adx <= ADX_EXIT
        )
    )

    if entry:
        decision = "ENTRY"

    elif exit_signal:
        decision = "EXIT"

    else:
        decision = "HOLD"

    return {
        "ENTRY": bool(entry),
        "EXIT": bool(exit_signal),
        "DECISION": decision,
        "ADX14": adx,
        "MACD_HIST": macd_hist,
        "MACD_HIST_SLOPE": macd_slope,
        "ROC10": roc10,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 78)
    print("VRE SURVIVAL V1.8 — BƯỚC 1")
    print("DAILY SIGNAL ENGINE — TECHNICAL TEST")
    print("=" * 78)

    print("\nFROZEN RULE:")
    print("ENTRY = ADX14 > 40 AND MACD_HIST_SLOPE > 0")
    print("EXIT  = MACD_HIST <= 0 OR ROC10 <= 2 OR ADX14 <= 30")

    results = []

    for symbol in TICKERS:

        df = load_daily(symbol)

        if df is None:
            results.append({
                "Ticker": symbol,
                "Status": "DOWNLOAD_ERROR"
            })
            continue

        try:
            df = calculate_indicators(df)

            signal = evaluate_signal(df)

            last = df.iloc[-1]

            last_date = last["date"]

            print("\n" + "-" * 78)
            print(f"{symbol}")
            print(f"Last date : {last_date}")
            print(f"Close     : {last['close']:.4f}")
            print(f"ADX14     : {signal['ADX14']:.4f}")
            print(f"MACD_HIST : {signal['MACD_HIST']:.6f}")
            print(
                f"HIST_SLOPE: "
                f"{signal['MACD_HIST_SLOPE']:.6f}"
            )
            print(f"ROC10     : {signal['ROC10']:.4f}")
            print(f"DECISION  : {signal['DECISION']}")

            results.append({
                "Ticker": symbol,
                "LastDate": last_date,
                "Close": last["close"],
                "ADX14": signal["ADX14"],
                "MACD_HIST": signal["MACD_HIST"],
                "MACD_HIST_SLOPE": signal["MACD_HIST_SLOPE"],
                "ROC10": signal["ROC10"],
                "ENTRY": signal["ENTRY"],
                "EXIT": signal["EXIT"],
                "DECISION": signal["DECISION"],
                "Rows": len(df),
                "Status": "OK",
            })

        except Exception as e:

            print(
                f"[{symbol}] ERROR INDICATOR: {e}"
            )

            results.append({
                "Ticker": symbol,
                "Status": "INDICATOR_ERROR",
                "Error": str(e),
            })

        # Tránh gọi KBS quá dồn
        time.sleep(1.0)

    # ========================================================
    # SUMMARY
    # ========================================================

    result_df = pd.DataFrame(results)

    print("\n")
    print("=" * 78)
    print("VRE SURVIVAL V1.8 — STEP 1 SUMMARY")
    print("=" * 78)

    if len(result_df):

        display_cols = [
            "Ticker",
            "LastDate",
            "Close",
            "ADX14",
            "MACD_HIST",
            "MACD_HIST_SLOPE",
            "ROC10",
            "DECISION",
            "Rows",
            "Status",
        ]

        existing = [
            c for c in display_cols
            if c in result_df.columns
        ]

        print(
            result_df[existing].to_string(
                index=False
            )
        )

    print("\n" + "=" * 78)
    print("STEP 1 FINISHED")
    print("=" * 78)
    print("Chưa gửi Telegram.")
    print("Chưa tạo state.")
    print("Chưa paper trade.")
    print("Chưa sửa MSR/CII.")
    print("=" * 78)


if __name__ == "__main__":
    main() 
