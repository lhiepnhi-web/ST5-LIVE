"""
MSR STEP 5 ENGINE
ST5 LIVE

Validated baseline:
    MSR Step 5 Round C.4 — PASS

Purpose:
    Generate MSR signals and execute the validated Step 5 trade logic.

This module does NOT optimize the strategy.
It is a production-oriented version of the validated C4 engine.

Expected input columns:
    Date, Open, High, Low, Close, Volume

Entry:
    Volume Ratio > 1
    MACD Histogram > 0
    ROC10 > 2
    ADX14 > 30

Execution:
    Entry at signal-bar Close
    One position at a time
    No overlap
    TP20 based on intraday High
    TP exit price = exact +20% target
    LOSS_OF_LAW when any entry condition becomes false
    MAX_HOLD = 10 bars
    END_OF_DATA for an open position at the final bar

Costs:
    Buy fee  = 0.15%
    Sell fee = 0.15%
    Sell tax = 0.10%

Important:
    Entry-day High is NOT allowed to trigger TP because entry occurs
    at the signal-bar Close.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ================================================================================================
# CONFIG
# ================================================================================================

BUY_FEE = 0.0015
SELL_FEE = 0.0015
SELL_TAX = 0.0010

TP_PCT = 0.20
MAX_HOLD = 10


# ================================================================================================
# INDICATORS
# ================================================================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add the validated MSR Step 5 indicators.

    Returns a copy of the input dataframe.
    """

    required = {
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    out = df.copy()

    out["Date"] = pd.to_datetime(out["Date"])

    out = (
        out
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------------------------------------------
    # MACD 12 / 26 / 9
    # --------------------------------------------------------------------------------------------

    ema12 = out["Close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = out["Close"].ewm(
        span=26,
        adjust=False
    ).mean()

    out["MACD"] = ema12 - ema26

    out["MACD_SIGNAL"] = out["MACD"].ewm(
        span=9,
        adjust=False
    ).mean()

    out["MACD_HIST"] = (
        out["MACD"] - out["MACD_SIGNAL"]
    )

    # --------------------------------------------------------------------------------------------
    # ROC10
    # --------------------------------------------------------------------------------------------

    out["ROC10"] = (
        out["Close"].pct_change(10) * 100
    )

    # --------------------------------------------------------------------------------------------
    # VOLUME RATIO
    # --------------------------------------------------------------------------------------------

    out["VOL_MA20"] = (
        out["Volume"].rolling(20).mean()
    )

    out["VOLUME_RATIO"] = (
        out["Volume"] / out["VOL_MA20"]
    )

    # --------------------------------------------------------------------------------------------
    # ADX14 — WILDER
    # --------------------------------------------------------------------------------------------

    high = out["High"]
    low = out["Low"]
    close = out["Close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
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

    period = 14

    atr14 = tr.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_dm14 = pd.Series(
        plus_dm,
        index=out.index
    ).ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    minus_dm14 = pd.Series(
        minus_dm,
        index=out.index
    ).ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_di = (
        100 * plus_dm14 / atr14
    )

    minus_di = (
        100 * minus_dm14 / atr14
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di)
    )

    out["ADX14"] = dx.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    # --------------------------------------------------------------------------------------------
    # ENTRY SIGNAL
    # --------------------------------------------------------------------------------------------

    out["ENTRY_SIGNAL"] = (
        (out["VOLUME_RATIO"] > 1)
        & (out["MACD_HIST"] > 0)
        & (out["ROC10"] > 2)
        & (out["ADX14"] > 30)
    )

    return out


# ================================================================================================
# SIGNAL CHECK
# ================================================================================================

def get_signal_count(df: pd.DataFrame) -> int:
    """Return number of valid MSR entry signals."""

    if "ENTRY_SIGNAL" not in df.columns:
        raise ValueError(
            "ENTRY_SIGNAL not found. Run add_indicators() first."
        )

    return int(df["ENTRY_SIGNAL"].sum())


# ================================================================================================
# LAW CHECK
# ================================================================================================

def law_is_alive(row: pd.Series) -> bool:
    """
    Check whether all four MSR entry conditions remain valid.
    """

    return bool(
        (row["VOLUME_RATIO"] > 1)
        and (row["MACD_HIST"] > 0)
        and (row["ROC10"] > 2)
        and (row["ADX14"] > 30)
    )


# ================================================================================================
# RETURN CALCULATION
# ================================================================================================

def calculate_net_return(
    entry_price: float,
    exit_price: float,
) -> float:
    """
    Calculate net trade return after:
        Buy fee  : 0.15%
        Sell fee : 0.15%
        Sell tax : 0.10%
    """

    return (
        exit_price * (1 - SELL_FEE - SELL_TAX)
    ) / (
        entry_price * (1 + BUY_FEE)
    ) - 1


# ================================================================================================
# TRADE ENGINE
# ================================================================================================

def run_engine(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the validated MSR Step 5 trade engine.

    Returns:
        data_with_indicators
        trades

    Trade logic:
        - one position at a time
        - entry at signal-bar Close
        - TP20 checked using future bars only
        - TP20 exit at exact target price
        - LOSS_OF_LAW at current Close
        - MAX_HOLD at current Close
        - END_OF_DATA at final Close
    """

    data = add_indicators(df)

    trades = []

    position: Optional[dict] = None
    trade_id = 0

    for i in range(len(data)):

        row = data.iloc[i]

        # ========================================================================================
        # ENTRY
        # ========================================================================================

        if position is None:

            if bool(row["ENTRY_SIGNAL"]):

                trade_id += 1

                position = {
                    "TradeID": trade_id,
                    "EntryIndex": i,
                    "EntryDate": row["Date"],
                    "EntryPrice": float(row["Close"]),
                }

                # Entry happens at CLOSE.
                # Do not evaluate the entry bar's High for TP.
                continue

        # ========================================================================================
        # POSITION MANAGEMENT
        # ========================================================================================

        if position is None:
            continue

        entry_index = position["EntryIndex"]
        entry_price = position["EntryPrice"]

        hold_bars = i - entry_index

        target_price = (
            entry_price * (1 + TP_PCT)
        )

        # ----------------------------------------------------------------------------------------
        # TP20
        # ----------------------------------------------------------------------------------------

        tp_hit = (
            i > entry_index
            and float(row["High"]) >= target_price
        )

        # ----------------------------------------------------------------------------------------
        # LOSS OF LAW
        # ----------------------------------------------------------------------------------------

        law_alive = law_is_alive(row)
        law_broken = not law_alive

        # ----------------------------------------------------------------------------------------
        # EXIT
        # ----------------------------------------------------------------------------------------

        exit_reason = None
        exit_price = None

        # TP has priority.
        if tp_hit:

            exit_reason = "TP20"
            exit_price = target_price

        elif law_broken:

            exit_reason = "LOSS_OF_LAW"
            exit_price = float(row["Close"])

        elif hold_bars >= MAX_HOLD:

            exit_reason = "MAX_HOLD"
            exit_price = float(row["Close"])

        elif i == len(data) - 1:

            exit_reason = "END_OF_DATA"
            exit_price = float(row["Close"])

        # ----------------------------------------------------------------------------------------
        # RECORD
        # ----------------------------------------------------------------------------------------

        if exit_reason is not None:

            gross_return = (
                exit_price / entry_price
            ) - 1

            net_return = calculate_net_return(
                entry_price,
                exit_price
            )

            trades.append({
                "TradeID": trade_id,

                "EntryIndex": entry_index,
                "ExitIndex": i,

                "EntryDate": position["EntryDate"],
                "ExitDate": row["Date"],

                "EntryPrice": entry_price,
                "ExitPrice": exit_price,

                "HoldBars": hold_bars,

                "TargetPrice": target_price,
                "ExitHigh": float(row["High"]),

                "ExitReason": exit_reason,

                "GrossReturnPct": gross_return * 100,
                "NetReturnPct": net_return * 100,

                "BuyFeePct": BUY_FEE * 100,
                "SellFeePct": SELL_FEE * 100,
                "SellTaxPct": SELL_TAX * 100,

                "EntryVolumeRatio": float(
                    data.iloc[entry_index]["VOLUME_RATIO"]
                ),

                "EntryMACDHist": float(
                    data.iloc[entry_index]["MACD_HIST"]
                ),

                "EntryROC10": float(
                    data.iloc[entry_index]["ROC10"]
                ),

                "EntryADX14": float(
                    data.iloc[entry_index]["ADX14"]
                ),
            })

            position = None

    trades_df = pd.DataFrame(trades)

    return data, trades_df


# ================================================================================================
# SUMMARY
# ================================================================================================

def summarize_trades(
    trades: pd.DataFrame,
) -> dict:
    """
    Return standard MSR Step 5 performance summary.
    """

    if trades.empty:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "profit_factor": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "TP20": 0,
            "LOSS_OF_LAW": 0,
            "MAX_HOLD": 0,
            "END_OF_DATA": 0,
        }

    returns = trades["NetReturnPct"]

    wins = int((returns > 0).sum())
    losses = int((returns <= 0).sum())

    gross_profit = float(
        returns[returns > 0].sum()
    )

    gross_loss = float(
        -returns[returns < 0].sum()
    )

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.inf
    )

    return {
        "trades": int(len(trades)),
        "wins": wins,
        "losses": losses,

        "win_rate_pct": (
            wins / len(trades) * 100
        ),

        "avg_return_pct": float(
            returns.mean()
        ),

        "median_return_pct": float(
            returns.median()
        ),

        "profit_factor": (
            None
            if np.isinf(profit_factor)
            else float(profit_factor)
        ),

        "best_trade_pct": float(
            returns.max()
        ),

        "worst_trade_pct": float(
            returns.min()
        ),

        "TP20": int(
            (trades["ExitReason"] == "TP20").sum()
        ),

        "LOSS_OF_LAW": int(
            (trades["ExitReason"] == "LOSS_OF_LAW").sum()
        ),

        "MAX_HOLD": int(
            (trades["ExitReason"] == "MAX_HOLD").sum()
        ),

        "END_OF_DATA": int(
            (trades["ExitReason"] == "END_OF_DATA").sum()
        ),
    }


# ================================================================================================
# SIMPLE PUBLIC API
# ================================================================================================

def run_msr(
    df: pd.DataFrame,
) -> dict:
    """
    Main public entry point for ST5 LIVE.

    Returns:
        {
            "data": dataframe_with_indicators,
            "trades": trade_dataframe,
            "summary": performance_summary
        }
    """

    data, trades = run_engine(df)

    summary = summarize_trades(trades)

    return {
        "data": data,
        "trades": trades,
        "summary": summary,
    }


# ================================================================================================
# LOCAL TEST
# ================================================================================================

if __name__ == "__main__":

    print("=" * 80)
    print("MSR STEP 5 ENGINE")
    print("ST5 LIVE")
    print("=" * 80)
    print()
    print("Module loaded successfully.")
    print()
    print("Public functions:")
    print("  add_indicators(df)")
    print("  get_signal_count(df)")
    print("  law_is_alive(row)")
    print("  calculate_net_return(entry_price, exit_price)")
    print("  run_engine(df)")
    print("  summarize_trades(trades)")
    print("  run_msr(df)") 
