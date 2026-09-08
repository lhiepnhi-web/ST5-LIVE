import os
import sys
import json
from datetime import datetime, time as dt_time

import pandas as pd
import pytz


# ============================================================
# ST5 LIVE — SIGNAL SCANNER
# ============================================================
#
# Luồng:
#
# DATA UPDATE
#      ↓
# 5M completed candle
#      ↓
# 5M indicator / Trigger
#      +
# completed 15M confirmation
#      ↓
# BUY
#      ↓
# Telegram
#
# Không tự đặt lệnh.
# Không gửi SELL.
# Không xử lý T+2.5 ở bước này.
#
# ============================================================


# ============================================================
# ROOT
# ============================================================

ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

sys.path.insert(
    0,
    ROOT_DIR
)


# ============================================================
# IMPORT
# ============================================================

from config import CORE26
from indicators import add_v14_indicators, v14_signal


# ============================================================
# CONFIG
# ============================================================

DATA_DIR = os.path.join(
    ROOT_DIR,
    "data",
    "INTRADAY_5M"
)

STATE_FILE = os.path.join(
    ROOT_DIR,
    "data",
    "live_state.json"
)

TZ = pytz.timezone(
    "Asia/Ho_Chi_Minh"
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


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        print(
            "⚠️ TELEGRAM_BOT_TOKEN chưa được cấu hình."
        )
        return False

    if not TELEGRAM_CHAT_ID:
        print(
            "⚠️ TELEGRAM_CHAT_ID chưa được cấu hình."
        )
        return False

    try:

        import requests

        url = (
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        }

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        response.raise_for_status()

        print(
            "📨 Telegram: SENT"
        )

        return True

    except Exception as e:

        print(
            f"❌ Telegram error: "
            f"{type(e).__name__}: {e}"
        )

        return False


# ============================================================
# TIME
# ============================================================

def now_vietnam():

    return datetime.now(
        TZ
    )


def in_trading_session(
    current_time
):

    current = current_time.time()

    morning = (
        dt_time(9, 15)
        <= current
        <= dt_time(11, 30)
    )

    afternoon = (
        dt_time(13, 0)
        <= current
        <= dt_time(14, 30)
    )

    return (
        morning
        or afternoon
    )


# ============================================================
# STATE
# ============================================================

def load_state():

    if not os.path.exists(
        STATE_FILE
    ):

        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)

        if not isinstance(
            state,
            dict
        ):

            return {}

        return state

    except Exception as e:

        print(
            f"⚠️ State read error: "
            f"{type(e).__name__}: {e}"
        )

        return {}


def save_state(state):

    os.makedirs(
        os.path.dirname(
            STATE_FILE
        ),
        exist_ok=True
    )

    temp_file = (
        STATE_FILE
        + ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp_file,
        STATE_FILE
    )


# ============================================================
# LOAD DATA
# ============================================================

def load_5m_file(
    ticker
):

    file_path = os.path.join(
        DATA_DIR,
        f"{ticker}_5m.csv"
    )

    if not os.path.exists(
        file_path
    ):

        print(
            f"⚠️ {ticker}: "
            "5M file not found"
        )

        return pd.DataFrame()

    try:

        df = pd.read_csv(
            file_path
        )

    except Exception as e:

        print(
            f"❌ {ticker}: "
            f"read error: {e}"
        )

        return pd.DataFrame()

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

        print(
            f"❌ {ticker}: "
            f"missing columns {missing}"
        )

        return pd.DataFrame()

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce"
    )

    for col in required[1:]:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    )

    df = df.sort_values(
        "Date"
    )

    df = df.drop_duplicates(
        subset=["Date"],
        keep="last"
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# COMPLETED 5M CANDLES
# ============================================================

def completed_5m(
    df,
    current_time
):

    if df.empty:
        return df

    df = df.copy()

    # Candle Date = candle open time.
    # Chỉ sử dụng candle đã đóng.
    candle_end = (
        df["Date"]
        + pd.Timedelta(minutes=5)
    )

    df = df[
        candle_end
        <= current_time
    ]

    return df.reset_index(
        drop=True
    )


# ============================================================
# BUILD 15M
# ============================================================

def build_15m(
    df5
):

    if df5.empty:

        return pd.DataFrame()

    x = df5.copy()

    x = x.set_index(
        "Date"
    )

    df15 = x.resample(
        "15min",
        origin="start_day",
        offset="15min"
    ).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )

    df15 = df15.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]
    )

    df15 = df15.reset_index()

    return df15


# ============================================================
# COMPLETED 15M
# ============================================================

def completed_15m(
    df15,
    current_time
):

    if df15.empty:
        return df15

    df15 = df15.copy()

    df15["AvailableAt"] = (
        df15["Date"]
        + pd.Timedelta(minutes=15)
    )

    df15 = df15[
        df15["AvailableAt"]
        <= current_time
    ]

    return df15.reset_index(
        drop=True
    )


# ============================================================
# BUILD LIVE SIGNAL
# ============================================================

def calculate_signal(
    df5,
    current_time
):

    # --------------------------------------------------------
    # COMPLETED 5M
    # --------------------------------------------------------

    df5 = completed_5m(
        df5,
        current_time
    )

    if len(df5) < 50:

        return pd.DataFrame()

    # --------------------------------------------------------
    # 5M TRIGGER
    # --------------------------------------------------------

    df5 = add_v14_indicators(
        df5.copy()
    )

    df5["Trigger"] = (
        v14_signal(
            df5
        )
        .astype(bool)
    )

    # --------------------------------------------------------
    # 15M CONFIRMATION
    # --------------------------------------------------------

    df15 = build_15m(
        df5[
            [
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]
        ].copy()
    )

    df15 = completed_15m(
        df15,
        current_time
    )

    if len(df15) < 20:

        return pd.DataFrame()

    df15 = add_v14_indicators(
        df15
    )

    df15["Confirm"] = (
        v14_signal(
            df15
        )
        .astype(bool)
    )

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    df15_merge = df15[
        [
            "AvailableAt",
            "Confirm",
        ]
    ].sort_values(
        "AvailableAt"
    )

    result = pd.merge_asof(
        df5.sort_values("Date"),
        df15_merge,
        left_on="Date",
        right_on="AvailableAt",
        direction="backward"
    )

    result["Confirm"] = (
        result["Confirm"]
        .fillna(False)
        .astype(bool)
    )

    result["BUY"] = (
        result["Trigger"]
        & result["Confirm"]
    )

    return result


# ============================================================
# PROCESS ONE TICKER
# ============================================================

def process_ticker(
    ticker,
    current_time,
    state
):

    print()
    print(
        f"[SCAN] {ticker}"
    )

    df5 = load_5m_file(
        ticker
    )

    if df5.empty:

        return None

    result = calculate_signal(
        df5,
        current_time
    )

    if result.empty:

        print(
            f"   {ticker}: "
            "not enough completed data"
        )

        return None

    latest = result.iloc[-1]

    signal_time = latest["Date"]

    trigger = bool(
        latest["Trigger"]
    )

    confirm = bool(
        latest["Confirm"]
    )

    buy = bool(
        latest["BUY"]
    )

    print(
        f"   Candle : {signal_time}"
    )

    print(
        f"   Close  : {latest['Close']}"
    )

    print(
        f"   Trigger: {trigger}"
    )

    print(
        f"   Confirm: {confirm}"
    )

    print(
        f"   BUY    : {buy}"
    )

    # --------------------------------------------------------
    # NO BUY
    # --------------------------------------------------------

    if not buy:

        return None

    # --------------------------------------------------------
    # DEDUP
    # --------------------------------------------------------

    ticker_state = state.get(
        ticker,
        {}
    )

    last_buy_time = (
        ticker_state.get(
            "last_buy_signal"
        )
    )

    signal_time_str = (
        pd.Timestamp(
            signal_time
        ).isoformat()
    )

    if (
        last_buy_time
        == signal_time_str
    ):

        print(
            f"   {ticker}: "
            "BUY already sent"
        )

        return None

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    message = (
        "🚨 ST5 LIVE — BUY SIGNAL\n\n"
        f"Ticker: {ticker}\n"
        f"Time: {signal_time}\n"
        f"Close: {latest['Close']}\n"
        f"Trigger: {'PASS' if trigger else 'FAIL'}\n"
        f"15M Confirm: {'PASS' if confirm else 'FAIL'}\n\n"
        "⚠️ Paper signal — chưa tự đặt lệnh."
    )

    sent = send_telegram(
        message
    )

    if not sent:

        print(
            f"   {ticker}: "
            "Telegram failed"
        )

        return None

    # --------------------------------------------------------
    # SAVE STATE
    # --------------------------------------------------------

    state[ticker] = {
        "last_buy_signal": signal_time_str,
        "last_close": float(
            latest["Close"]
        ),
        "updated_at": current_time.isoformat(),
    }

    save_state(
        state
    )

    print(
        f"   ✅ {ticker}: "
        "BUY SENT"
    )

    return {
        "Ticker": ticker,
        "SignalTime": signal_time,
        "Close": float(
            latest["Close"]
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    current_time = now_vietnam()

    print()
    print("=" * 70)
    print("ST5 LIVE — INTRADAY SIGNAL SCANNER")
    print("=" * 70)

    print(
        f"Vietnam time: {current_time}"
    )

    # --------------------------------------------------------
    # WEEKDAY
    # --------------------------------------------------------

    if current_time.weekday() >= 5:

        print(
            "⏸ Weekend — scanner stopped."
        )

        return

    # --------------------------------------------------------
    # SESSION
    # --------------------------------------------------------

    if not in_trading_session(
        current_time
    ):

        print(
            "⏸ Outside trading session."
        )

        return

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state = load_state()

    results = []

    # --------------------------------------------------------
    # SCAN CORE26
    # --------------------------------------------------------

    for ticker in CORE26:

        try:

            signal = process_ticker(
                ticker,
                current_time,
                state
            )

            if signal is not None:

                results.append(
                    signal
                )

        except Exception as e:

            print(
                f"❌ {ticker}: "
                f"{type(e).__name__}: {e}"
            )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SCAN COMPLETE")
    print("=" * 70)

    print(
        f"Tickers scanned : {len(CORE26)}"
    )

    print(
        f"BUY sent        : {len(results)}"
    )

    if results:

        print()
        print(
            "BUY SIGNALS:"
        )

        for item in results:

            print(
                f"  {item['Ticker']} | "
                f"{item['SignalTime']} | "
                f"{item['Close']}"
            )

    else:

        print(
            "No new BUY signal."
        )

    print("=" * 70)


if __name__ == "__main__":

    main()
