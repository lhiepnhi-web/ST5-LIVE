# ============================================================
# ST5 LIVE — MSR C4 LIVE
# ============================================================
# PURPOSE:
#   MSR C4 frozen strategy
#   - Uses historical Daily + developing Daily candle built from 5M
#   - Intraday BUY signal
#   - Telegram BUY only
#   - No auto order
#   - One BUY notification per day
#
# IMPORTANT:
#   Strategy logic is NOT changed.
#   Only live Daily data construction is changed.
# ============================================================

import os
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests
import pandas as pd

from msr_step5_engine import add_indicators
from live_daily_data import get_live_daily


# ============================================================
# CONFIG
# ============================================================

SYMBOL = "MSR"

STATE_FILE = "data/msr_live_state.json"

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

MORNING_START = time(9, 15)
MORNING_END = time(11, 30)

AFTERNOON_START = time(13, 0)
AFTERNOON_END = time(14, 30)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message: str) -> bool:

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15,
        )

        if response.ok:
            print("Telegram sent.")
            return True

        print(
            "Telegram failed:",
            response.status_code,
            response.text,
        )

    except Exception as e:

        print(
            "Telegram exception:",
            repr(e),
        )

    return False


# ============================================================
# STATE
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {
            "last_buy_date": None,
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            state = json.load(f)

        if not isinstance(state, dict):
            raise ValueError("Invalid state format.")

        state.setdefault(
            "last_buy_date",
            None,
        )

        return state

    except Exception as e:

        print(
            "State load failed:",
            repr(e),
        )

        return {
            "last_buy_date": None,
        }


def save_state(state):

    os.makedirs(
        os.path.dirname(STATE_FILE),
        exist_ok=True,
    )

    temp_file = STATE_FILE + ".tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temp_file,
        STATE_FILE,
    )


# ============================================================
# SESSION
# ============================================================

def is_trading_session(now_vn: datetime) -> bool:

    current_time = now_vn.time()

    morning = (
        MORNING_START
        <= current_time
        <= MORNING_END
    )

    afternoon = (
        AFTERNOON_START
        <= current_time
        <= AFTERNOON_END
    )

    return morning or afternoon


# ============================================================
# LIVE DATA
# ============================================================

def load_live_daily():

    today = datetime.now(VN_TZ).date()

    print()
    print("=" * 72)
    print("MSR LIVE DAILY DATA")
    print("=" * 72)

    print("Today VN :", today)

    result = get_live_daily(
        SYMBOL,
    )

    if not result.get("ok"):

        error = result.get(
            "error",
            "unknown error",
        )

        print()
        print("FAIL SAFE")
        print("Reason :", error)

        return None

    df = result.get("data")

    if df is None or df.empty:

        print()
        print("FAIL SAFE")
        print("Reason : empty live daily dataframe")

        return None

    # --------------------------------------------------------
    # HARD VALIDATION
    # --------------------------------------------------------

    if not result.get("is_current_day", False):

        print()
        print("FAIL SAFE")
        print(
            "Reason : latest Daily candle is NOT current day"
        )

        return None

    latest_date = pd.Timestamp(
        df["Date"].iloc[-1]
    ).date()

    if latest_date != today:

        print()
        print("FAIL SAFE")

        print(
            "Latest date :",
            latest_date,
        )

        print(
            "Expected    :",
            today,
        )

        return None

    print()
    print("Latest Daily :", latest_date)

    print(
        "Current candle:",
        "YES",
    )

    return df


# ============================================================
# SIGNAL
# ============================================================

def calculate_live_signal(df):

    # --------------------------------------------------------
    # IMPORTANT:
    # EXACT SAME INDICATOR ENGINE AS MSR C4
    # --------------------------------------------------------

    data = add_indicators(
        df.copy()
    )

    if data.empty:
        return None

    latest = data.iloc[-1]

    required_columns = [
        "ENTRY_SIGNAL",
        "Volume_Ratio",
        "MACD_HIST",
        "ROC10",
        "ADX14",
        "Close",
    ]

    for col in required_columns:

        if col not in data.columns:

            raise ValueError(
                f"MSR C4: missing column {col}"
            )

    signal = bool(
        latest["ENTRY_SIGNAL"]
    )

    return {
        "date": pd.Timestamp(
            latest["Date"]
        ).date(),

        "close": float(
            latest["Close"]
        ),

        "volume_ratio": float(
            latest["Volume_Ratio"]
        ),

        "macd_hist": float(
            latest["MACD_HIST"]
        ),

        "roc10": float(
            latest["ROC10"]
        ),

        "adx14": float(
            latest["ADX14"]
        ),

        "signal": signal,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    now_vn = datetime.now(VN_TZ)

    print()
    print("=" * 72)
    print("ST5 LIVE — MSR C4")
    print("=" * 72)

    print(
        "VN time :",
        now_vn.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )

    # --------------------------------------------------------
    # SESSION GATE
    # --------------------------------------------------------

    if not is_trading_session(now_vn):

        print(
            "Outside trading session."
        )

        return

    today = now_vn.date()

    # --------------------------------------------------------
    # LOAD CURRENT DAILY
    # --------------------------------------------------------

    df = load_live_daily()

    if df is None:

        print(
            "MSR LIVE STOPPED — FAIL SAFE"
        )

        return

    # --------------------------------------------------------
    # CALCULATE C4 SIGNAL
    # --------------------------------------------------------

    result = calculate_live_signal(
        df
    )

    if result is None:

        print(
            "MSR signal calculation failed."
        )

        return

    print()
    print("=" * 72)
    print("MSR C4 CURRENT SIGNAL")
    print("=" * 72)

    print(
        "Date        :",
        result["date"],
    )

    print(
        "Close       :",
        result["close"],
    )

    print(
        "VolumeRatio :",
        result["volume_ratio"],
    )

    print(
        "MACD Hist   :",
        result["macd_hist"],
    )

    print(
        "ROC10       :",
        result["roc10"],
    )

    print(
        "ADX14       :",
        result["adx14"],
    )

    print(
        "C4 SIGNAL   :",
        result["signal"],
    )

    # --------------------------------------------------------
    # EXTRA SAFETY
    # --------------------------------------------------------

    if result["date"] != today:

        print()
        print(
            "FAIL SAFE: signal date != today"
        )

        return

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state = load_state()

    last_buy_date = state.get(
        "last_buy_date"
    )

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if result["signal"]:

        if last_buy_date == str(today):

            print()
            print(
                "BUY condition TRUE."
            )

            print(
                "Telegram BUY already sent today."
            )

            return

        message = (
            "🟢 MSR — C4 BUY\n\n"
            f"Date: {result['date']}\n"
            f"Close: {result['close']:.2f}\n"
            f"Volume Ratio: {result['volume_ratio']:.4f}\n"
            f"MACD Hist: {result['macd_hist']:.6f}\n"
            f"ROC10: {result['roc10']:.4f}\n"
            f"ADX14: {result['adx14']:.4f}\n\n"
            "ENTRY:\n"
            "Volume Ratio > 1\n"
            "MACD Histogram > 0\n"
            "ROC10 > 2\n"
            "ADX14 > 30"
        )

        sent = send_telegram(
            message
        )

        if sent:

            state["last_buy_date"] = str(
                today
            )

            save_state(
                state
            )

            print()
            print(
                "BUY notification recorded."
            )

        return

    # --------------------------------------------------------
    # NO SIGNAL
    # --------------------------------------------------------

    print()
    print(
        "No BUY signal."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
