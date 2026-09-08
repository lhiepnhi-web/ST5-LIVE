"""
ST5 LIVE
MSR STEP 5 — C4 LIVE ADAPTER

C4 remains the validated MSR daily engine.

This adapter:
    - reuses C4 add_indicators()
    - does NOT duplicate indicator formulas
    - does NOT modify C4 trade logic
    - sends Telegram only when a new MSR ENTRY_SIGNAL appears
    - does not place orders

IMPORTANT:
    C4 is a DAILY strategy.
    Therefore this adapter evaluates completed DAILY bars,
    not 5M bars.

The live infrastructure can run during the trading session,
but a new MSR daily signal is only valid when the daily bar
is complete according to the C4 execution model.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time as dt_time
from pathlib import Path

import pandas as pd
import pytz


# ============================================================
# PATH
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ============================================================
# IMPORT C4
# ============================================================

from msr_step5_engine import add_indicators


# ============================================================
# CONFIG
# ============================================================

TZ = pytz.timezone(
    "Asia/Ho_Chi_Minh"
)

STATE_FILE = (
    ROOT_DIR
    / "data"
    / "msr_live_state.json"
)

DATA_DIR = (
    ROOT_DIR
    / "data"
    / "MSR"
)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)


def send_telegram(message: str) -> bool:

    if not TELEGRAM_BOT_TOKEN:
        print(
            "Telegram token chưa được cấu hình."
        )
        return False

    if not TELEGRAM_CHAT_ID:
        print(
            "Telegram chat ID chưa được cấu hình."
        )
        return False

    try:

        import requests

        url = (
            "https://api.telegram.org/"
            f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=15,
        )

        response.raise_for_status()

        return True

    except Exception as exc:

        print(
            f"Telegram error: "
            f"{type(exc).__name__}: {exc}"
        )

        return False


# ============================================================
# TIME
# ============================================================

def now_vietnam() -> datetime:

    return datetime.now(TZ)


def in_trading_session(
    current: datetime,
) -> bool:

    if current.weekday() >= 5:
        return False

    t = current.time()

    morning = (
        dt_time(9, 15)
        <= t
        <= dt_time(11, 30)
    )

    afternoon = (
        dt_time(13, 0)
        <= t
        <= dt_time(14, 30)
    )

    return (
        morning
        or afternoon
    )


# ============================================================
# STATE
# ============================================================

def load_state() -> dict:

    if not STATE_FILE.exists():
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            state = json.load(f)

        if isinstance(state, dict):
            return state

    except Exception as exc:

        print(
            f"State read error: {exc}"
        )

    return {}


def save_state(state: dict):

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = (
        str(STATE_FILE)
        + ".tmp"
    )

    with open(
        temp,
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
        temp,
        STATE_FILE,
    )


# ============================================================
# DATA
# ============================================================

def load_msr_daily_data() -> pd.DataFrame:

    candidates = [
        DATA_DIR / "MSR.csv",
        ROOT_DIR / "data" / "MSR.csv",
        ROOT_DIR / "data" / "MSR_daily.csv",
    ]

    selected = None

    for path in candidates:

        if path.exists():
            selected = path
            break

    if selected is None:

        raise FileNotFoundError(
            "Không tìm thấy dữ liệu MSR daily."
        )

    df = pd.read_csv(
        selected
    )

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:

        raise ValueError(
            f"MSR thiếu cột: {missing}"
        )

    df = df[
        required
    ].copy()

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
    )

    for col in required[1:]:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    df = df.dropna(
        subset=required
    )

    df = (
        df
        .sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ============================================================
# COMPLETED DAILY BAR
# ============================================================

def completed_daily_data(
    df: pd.DataFrame,
    current: datetime,
) -> pd.DataFrame:

    if df.empty:
        return df

    out = df.copy()

    # Data provider normally gives Date as daily session date.
    # During an active trading session, today's daily candle
    # is still incomplete.
    #
    # Therefore only dates strictly before today's Vietnam date
    # are eligible for the C4 signal.

    today = pd.Timestamp(
        current.date()
    )

    out = out[
        out["Date"].dt.normalize()
        < today
    ]

    return out.reset_index(
        drop=True
    )


# ============================================================
# C4 SIGNAL
# ============================================================

def calculate_c4_signal(
    df: pd.DataFrame,
    current: datetime,
):

    completed = completed_daily_data(
        df,
        current,
    )

    if len(completed) < 50:

        return None

    # --------------------------------------------------------
    # IMPORTANT:
    # C4 indicator calculation comes directly
    # from msr_step5_engine.py
    # --------------------------------------------------------

    data = add_indicators(
        completed
    )

    latest = data.iloc[-1]

    return {
        "Date": latest["Date"],
        "Close": float(
            latest["Close"]
        ),
        "ENTRY_SIGNAL": bool(
            latest["ENTRY_SIGNAL"]
        ),
        "VOLUME_RATIO": float(
            latest["VOLUME_RATIO"]
        ),
        "MACD_HIST": float(
            latest["MACD_HIST"]
        ),
        "ROC10": float(
            latest["ROC10"]
        ),
        "ADX14": float(
            latest["ADX14"]
        ),
    }


# ============================================================
# PROCESS
# ============================================================

def process_msr(
    current: datetime,
    state: dict,
):

    df = load_msr_daily_data()

    signal = calculate_c4_signal(
        df,
        current,
    )

    if signal is None:

        print(
            "MSR: chưa đủ dữ liệu."
        )

        return False

    signal_date = pd.Timestamp(
        signal["Date"]
    ).strftime(
        "%Y-%m-%d"
    )

    print()
    print(
        "MSR C4"
    )
    print(
        f"Daily bar : {signal_date}"
    )
    print(
        f"Close     : {signal['Close']}"
    )
    print(
        f"Volume R  : {signal['VOLUME_RATIO']:.4f}"
    )
    print(
        f"MACD Hist : {signal['MACD_HIST']:.6f}"
    )
    print(
        f"ROC10     : {signal['ROC10']:.4f}"
    )
    print(
        f"ADX14     : {signal['ADX14']:.4f}"
    )
    print(
        f"ENTRY     : {signal['ENTRY_SIGNAL']}"
    )

    # --------------------------------------------------------
    # NO SIGNAL
    # --------------------------------------------------------

    if not signal["ENTRY_SIGNAL"]:

        return False

    # --------------------------------------------------------
    # DEDUP
    # --------------------------------------------------------

    last_signal = state.get(
        "last_entry_signal"
    )

    if last_signal == signal_date:

        print(
            "MSR: tín hiệu này đã gửi."
        )

        return False

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    message = (
        "🚨 ST5 LIVE — MSR C4 BUY\n\n"
        f"Date: {signal_date}\n"
        f"Close: {signal['Close']}\n\n"
        f"Volume Ratio: "
        f"{signal['VOLUME_RATIO']:.4f}\n"
        f"MACD Hist: "
        f"{signal['MACD_HIST']:.6f}\n"
        f"ROC10: "
        f"{signal['ROC10']:.4f}\n"
        f"ADX14: "
        f"{signal['ADX14']:.4f}\n\n"
        "C4 ENTRY: PASS\n"
        "⚠️ Paper signal — chưa tự đặt lệnh."
    )

    sent = send_telegram(
        message
    )

    if not sent:

        return False

    # --------------------------------------------------------
    # SAVE STATE
    # --------------------------------------------------------

    state["last_entry_signal"] = (
        signal_date
    )

    state["updated_at"] = (
        current.isoformat()
    )

    save_state(
        state
    )

    print(
        "✅ MSR C4 BUY đã gửi Telegram."
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    current = now_vietnam()

    print()
    print("=" * 70)
    print("ST5 LIVE — MSR C4")
    print("=" * 70)

    print(
        f"Vietnam time: {current}"
    )

    if not in_trading_session(
        current
    ):

        print(
            "Outside trading session."
        )

        return

    state = load_state()

    try:

        process_msr(
            current,
            state,
        )

    except Exception as exc:

        print()
        print(
            f"❌ MSR C4 error: "
            f"{type(exc).__name__}: {exc}"
        )


if __name__ == "__main__":

    main()
