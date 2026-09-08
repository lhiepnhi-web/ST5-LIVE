"""
ST5 LIVE
MSR STEP 5 — C4 LIVE ADAPTER

LIVE MODE

Historical C4 engine remains unchanged.

During live trading:
    - Use the current trading day's developing daily candle.
    - Reuse the exact C4 indicator calculation.
    - Evaluate ENTRY_SIGNAL on the latest available candle.
    - Send BUY only once per trading day.
    - Never send SELL.
    - Never place an order.

Trading sessions:
    09:15 - 11:30
    13:00 - 14:30
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time as dt_time
from pathlib import Path

import pandas as pd
import pytz
from vnstock import Quote


# ============================================================
# PATH
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ============================================================
# C4 ENGINE
# ============================================================

from msr_step5_engine import add_indicators


# ============================================================
# CONFIG
# ============================================================

TICKER = "MSR"

TZ = pytz.timezone(
    "Asia/Ho_Chi_Minh"
)

STATE_FILE = (
    ROOT_DIR
    / "data"
    / "msr_live_state.json"
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


def save_state(
    state: dict,
):

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = (
        str(STATE_FILE)
        + ".tmp"
    )

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
# DOWNLOAD MSR DAILY DATA
# ============================================================

def load_msr_daily() -> pd.DataFrame:

    print(
        "Downloading MSR daily data from KBS..."
    )

    quote = Quote(
        symbol=TICKER,
        source="KBS",
    )

    df = quote.history(
        start="2015-01-01",
        end=datetime.now(TZ).strftime(
            "%Y-%m-%d"
        ),
        interval="1D",
    )

    if df is None or df.empty:

        raise RuntimeError(
            "KBS không trả dữ liệu MSR."
        )

    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    rename = {
        "time": "Date",
        "datetime": "Date",
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }

    df = df.rename(
        columns=rename
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
        c
        for c in required
        if c not in df.columns
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

    print(
        f"MSR rows: {len(df)}"
    )

    print(
        f"Latest bar: "
        f"{df['Date'].iloc[-1]}"
    )

    return df


# ============================================================
# NORMALIZE TODAY'S DEVELOPING DAILY BAR
# ============================================================

def prepare_live_daily(
    df: pd.DataFrame,
    current: datetime,
) -> pd.DataFrame:

    today = pd.Timestamp(
        current.date()
    )

    out = df.copy()

    # --------------------------------------------------------
    # If KBS already contains today's developing daily bar,
    # use it directly.
    # --------------------------------------------------------

    today_rows = out[
        out["Date"].dt.normalize()
        == today
    ]

    if not today_rows.empty:

        print(
            "Today's developing MSR daily candle found."
        )

        return out.reset_index(
            drop=True
        )

    # --------------------------------------------------------
    # If provider does not return today's daily candle,
    # we cannot manufacture a daily candle from nowhere.
    # Keep historical data only.
    # --------------------------------------------------------

    print(
        "Today's developing daily candle "
        "is not available from KBS."
    )

    return out.reset_index(
        drop=True
    )


# ============================================================
# C4 LIVE SIGNAL
# ============================================================

def calculate_live_signal(
    df: pd.DataFrame,
    current: datetime,
) -> dict | None:

    data = prepare_live_daily(
        df,
        current,
    )

    if len(data) < 50:

        print(
            "MSR: insufficient history."
        )

        return None

    # --------------------------------------------------------
    # IMPORTANT:
    # Indicator formulas come directly from C4.
    # --------------------------------------------------------

    data = add_indicators(
        data
    )

    latest = data.iloc[-1]

    latest_date = pd.Timestamp(
        latest["Date"]
    )

    return {
        "Date": latest_date,
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
# PROCESS MSR
# ============================================================

def process_msr(
    current: datetime,
    state: dict,
) -> bool:

    df = load_msr_daily()

    signal = calculate_live_signal(
        df,
        current,
    )

    if signal is None:
        return False

    signal_date = pd.Timestamp(
        signal["Date"]
    ).strftime(
        "%Y-%m-%d"
    )

    print()
    print(
        "========== MSR C4 LIVE =========="
    )

    print(
        f"Candle date  : {signal_date}"
    )

    print(
        f"Close        : "
        f"{signal['Close']}"
    )

    print(
        f"Volume Ratio : "
        f"{signal['VOLUME_RATIO']:.4f}"
    )

    print(
        f"MACD Hist    : "
        f"{signal['MACD_HIST']:.6f}"
    )

    print(
        f"ROC10        : "
        f"{signal['ROC10']:.4f}"
    )

    print(
        f"ADX14        : "
        f"{signal['ADX14']:.4f}"
    )

    print(
        f"ENTRY_SIGNAL : "
        f"{signal['ENTRY_SIGNAL']}"
    )

    # --------------------------------------------------------
    # NO BUY
    # --------------------------------------------------------

    if not signal["ENTRY_SIGNAL"]:

        return False

    # --------------------------------------------------------
    # ONLY ACCEPT CURRENT TRADING DAY
    # --------------------------------------------------------

    today = current.strftime(
        "%Y-%m-%d"
    )

    if signal_date != today:

        print(
            "MSR: signal belongs to an old candle."
        )

        return False

    # --------------------------------------------------------
    # ONE TELEGRAM BUY PER DAY
    # --------------------------------------------------------

    last_signal_date = state.get(
        "last_entry_signal"
    )

    if last_signal_date == today:

        print(
            "MSR: today's BUY already sent."
        )

        return False

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    message = (
        "🚨 ST5 LIVE — MSR C4 BUY\n\n"
        f"Date: {today}\n"
        f"Close: {signal['Close']}\n\n"
        f"Volume Ratio: "
        f"{signal['VOLUME_RATIO']:.4f}\n"
        f"MACD Hist: "
        f"{signal['MACD_HIST']:.6f}\n"
        f"ROC10: "
        f"{signal['ROC10']:.4f}\n"
        f"ADX14: "
        f"{signal['ADX14']:.4f}\n\n"
        "C4 ENTRY: 4/4 CONDITIONS PASS\n"
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

    state[
        "last_entry_signal"
    ] = today

    state[
        "updated_at"
    ] = current.isoformat()

    save_state(
        state
    )

    print(
        "✅ MSR C4 BUY sent to Telegram."
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    current = now_vietnam()

    print()
    print("=" * 70)
    print("ST5 LIVE — MSR C4 LIVE")
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
