import os
import sys
import json
import pandas as pd
import numpy as np

# ============================================================
# ST5 — V1.1 DAILY ENGINE
# ============================================================

ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

sys.path.insert(0, ROOT_DIR)

from vnstock import Quote


# ============================================================
# CONFIG — FROZEN V1.1
# ============================================================

TICKERS = [
    "NVL",
    "VND",
    "ABB",
    "BFC",
    "C69",
    "CEO",
    "CII",
    "DXG",
    "HPG",
    "NAF",
    "OIL",
    "SHS",
    "VIX",
    "VPB",
]

STATE_FILE = os.path.join(
    ROOT_DIR,
    "data",
    "v11_daily_state.json"
)

# Cần đủ dữ liệu cho:
# EMA26 + MACD signal + ROC10 + ADX14 + Volume MA20
LOOKBACK_DAYS = 180


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
    """
    Gửi Telegram.
    Không làm engine chết nếu Telegram lỗi.
    """

    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN chưa có")
        return False

    if not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_CHAT_ID chưa có")
        return False

    try:
        import requests

        url = (
            "https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        }

        r = requests.post(
            url,
            json=payload,
            timeout=15
        )

        if r.ok:
            print("📨 Telegram: OK")
            return True

        print(
            "❌ Telegram lỗi:",
            r.status_code,
            r.text
        )

        return False

    except Exception as e:
        print(
            "❌ Telegram exception:",
            type(e).__name__,
            e
        )

        return False


# ============================================================
# LOAD STATE
# ============================================================

def load_state():

    os.makedirs(
        os.path.dirname(STATE_FILE),
        exist_ok=True
    )

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(
            "⚠️ Không đọc được state:",
            type(e).__name__,
            e
        )

    return {}


def save_state(state):

    os.makedirs(
        os.path.dirname(STATE_FILE),
        exist_ok=True
    )

    temp_file = STATE_FILE + ".tmp"

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
# LOAD DAILY DATA — KBS
# ============================================================

def get_daily_data(ticker):

    print(
        f"   Download DAILY {ticker} "
        f"from KBS..."
    )

    end = pd.Timestamp.now()

    start = (
        end -
        pd.Timedelta(
            days=LOOKBACK_DAYS
        )
    )

    quote = Quote(
        symbol=ticker,
        source="KBS"
    )

    df = quote.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1D"
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # Normalize columns
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

    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"{ticker}: thiếu cột {col}"
            )

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
        subset=["Date"]
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # VOLUME RATIO
    # Volume Ratio = Volume / MA20 Volume
    # --------------------------------------------------------

    df["Volume_MA20"] = (
        df["Volume"]
        .rolling(20)
        .mean()
    )

    df["Volume_Ratio"] = (
        df["Volume"] /
        df["Volume_MA20"]
    )

    # --------------------------------------------------------
    # MACD
    # EMA12 - EMA26
    # Histogram = MACD - Signal
    # --------------------------------------------------------

    ema12 = (
        df["Close"]
        .ewm(
            span=12,
            adjust=False
        )
        .mean()
    )

    ema26 = (
        df["Close"]
        .ewm(
            span=26,
            adjust=False
        )
        .mean()
    )

    df["MACD"] = (
        ema12 - ema26
    )

    df["MACD_Signal"] = (
        df["MACD"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["MACD_Hist"] = (
        df["MACD"] -
        df["MACD_Signal"]
    )

    # --------------------------------------------------------
    # ROC10
    # --------------------------------------------------------

    df["ROC10"] = (
        (
            df["Close"] /
            df["Close"].shift(10)
        ) - 1
    ) * 100

    # --------------------------------------------------------
    # ADX14
    # Wilder-style calculation
    # --------------------------------------------------------

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - prev_close
    ).abs()

    tr3 = (
        low - prev_close
    ).abs()

    df["TR"] = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    up_move = (
        high -
        high.shift(1)
    )

    down_move = (
        low.shift(1) -
        low
    )

    plus_dm = np.where(
        (
            (up_move > down_move) &
            (up_move > 0)
        ),
        up_move,
        0.0
    )

    minus_dm = np.where(
        (
            (down_move > up_move) &
            (down_move > 0)
        ),
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

    tr14 = (
        df["TR"]
        .ewm(
            alpha=1 / 14,
            adjust=False
        )
        .mean()
    )

    plus_dm14 = (
        plus_dm
        .ewm(
            alpha=1 / 14,
            adjust=False
        )
        .mean()
    )

    minus_dm14 = (
        minus_dm
        .ewm(
            alpha=1 / 14,
            adjust=False
        )
        .mean()
    )

    df["PLUS_DI14"] = (
        100 *
        plus_dm14 /
        tr14
    )

    df["MINUS_DI14"] = (
        100 *
        minus_dm14 /
        tr14
    )

    di_sum = (
        df["PLUS_DI14"] +
        df["MINUS_DI14"]
    )

    df["DX"] = np.where(
        di_sum != 0,
        100 *
        (
            (
                df["PLUS_DI14"] -
                df["MINUS_DI14"]
            ).abs()
            / di_sum
        ),
        np.nan
    )

    df["ADX14"] = (
        pd.Series(
            df["DX"],
            index=df.index
        )
        .ewm(
            alpha=1 / 14,
            adjust=False
        )
        .mean()
    )

    return df


# ============================================================
# V1.1 LAW
# ============================================================

def v11_conditions(row):

    volume_ok = (
        row["Volume_Ratio"] > 1
    )

    macd_ok = (
        row["MACD_Hist"] > 0
    )

    roc_ok = (
        row["ROC10"] > 2
    )

    adx_ok = (
        row["ADX14"] > 30
    )

    all_ok = (
        volume_ok and
        macd_ok and
        roc_ok and
        adx_ok
    )

    return {
        "volume": bool(volume_ok),
        "macd": bool(macd_ok),
        "roc": bool(roc_ok),
        "adx": bool(adx_ok),
        "all": bool(all_ok),
    }


# ============================================================
# FORMAT TELEGRAM
# ============================================================

def format_buy_message(
    ticker,
    row,
    trade_date
):

    return (
        "🟢 ST5 V1.1 — BUY\n\n"
        f"Mã: {ticker}\n"
        f"Ngày: {trade_date}\n"
        f"Giá đóng cửa: {row['Close']:.2f}\n\n"
        "Điều kiện:\n"
        f"Volume Ratio: {row['Volume_Ratio']:.2f} > 1 ✅\n"
        f"MACD Histogram: {row['MACD_Hist']:.4f} > 0 ✅\n"
        f"ROC10: {row['ROC10']:.2f} > 2 ✅\n"
        f"ADX14: {row['ADX14']:.2f} > 30 ✅"
    )


def format_exit_message(
    ticker,
    row,
    trade_date
):

    return (
        "🔴 ST5 V1.1 — EXIT\n\n"
        f"Mã: {ticker}\n"
        f"Ngày: {trade_date}\n"
        f"Giá đóng cửa: {row['Close']:.2f}\n\n"
        "V1.1: ít nhất 1 điều kiện đã FALSE.\n"
        f"Volume Ratio: {row['Volume_Ratio']:.2f} "
        f"{'✅' if row['Volume_Ratio'] > 1 else '❌'}\n"
        f"MACD Histogram: {row['MACD_Hist']:.4f} "
        f"{'✅' if row['MACD_Hist'] > 0 else '❌'}\n"
        f"ROC10: {row['ROC10']:.2f} "
        f"{'✅' if row['ROC10'] > 2 else '❌'}\n"
        f"ADX14: {row['ADX14']:.2f} "
        f"{'✅' if row['ADX14'] > 30 else '❌'}"
    )


# ============================================================
# PROCESS ONE TICKER
# ============================================================

def process_ticker(
    ticker,
    state
):

    print()
    print("-" * 70)
    print(f"Ticker: {ticker}")

    try:

        df = get_daily_data(
            ticker
        )

        if df.empty:
            print(
                f"❌ {ticker}: "
                "không có daily data"
            )
            return

        df = calculate_indicators(
            df
        )

        # ----------------------------------------------------
        # Chỉ dùng cây DAILY cuối cùng.
        # ----------------------------------------------------

        row = df.iloc[-1]

        trade_date = (
            pd.Timestamp(
                row["Date"]
            )
            .strftime("%Y-%m-%d")
        )

        conditions = v11_conditions(
            row
        )

        current_signal = conditions[
            "all"
        ]

        previous = state.get(
            ticker,
            {}
        )

        previous_date = previous.get(
            "date"
        )

        previous_signal = bool(
            previous.get(
                "signal",
                False
            )
        )

        print(
            f"Date       : {trade_date}"
        )

        print(
            f"Close      : {row['Close']:.2f}"
        )

        print(
            f"VolumeRatio: "
            f"{row['Volume_Ratio']:.4f}"
        )

        print(
            f"MACD Hist  : "
            f"{row['MACD_Hist']:.6f}"
        )

        print(
            f"ROC10      : "
            f"{row['ROC10']:.4f}"
        )

        print(
            f"ADX14      : "
            f"{row['ADX14']:.4f}"
        )

        print()
        print(
            "V1.1:"
        )

        print(
            f"  Volume > 1 : "
            f"{'PASS' if conditions['volume'] else 'FAIL'}"
        )

        print(
            f"  MACD > 0   : "
            f"{'PASS' if conditions['macd'] else 'FAIL'}"
        )

        print(
            f"  ROC10 > 2  : "
            f"{'PASS' if conditions['roc'] else 'FAIL'}"
        )

        print(
            f"  ADX14 > 30 : "
            f"{'PASS' if conditions['adx'] else 'FAIL'}"
        )

        print()
        print(
            f"V1.1 SIGNAL : "
            f"{'TRUE' if current_signal else 'FALSE'}"
        )

        # ----------------------------------------------------
        # QUAN TRỌNG:
        #
        # Nếu cùng một ngày đã xử lý rồi,
        # không gửi lại BUY/EXIT.
        # ----------------------------------------------------

        if previous_date == trade_date:

            print(
                "⏭ Đã xử lý ngày này."
            )

            return

        # ----------------------------------------------------
        # BUY:
        # FALSE -> TRUE
        # ----------------------------------------------------

        if (
            not previous_signal
            and current_signal
        ):

            print(
                f"🟢 BUY SIGNAL: {ticker}"
            )

            message = format_buy_message(
                ticker,
                row,
                trade_date
            )

            send_telegram(
                message
            )

        # ----------------------------------------------------
        # EXIT:
        # TRUE -> FALSE
        #
        # Theo luật V1.1:
        # exit bắt đầu từ phiên tiếp theo sau BUY.
        #
        # State chỉ chuyển BUY ở phiên trước,
        # nên khi ngày mới FALSE -> EXIT.
        # ----------------------------------------------------

        elif (
            previous_signal
            and not current_signal
        ):

            print(
                f"🔴 EXIT SIGNAL: {ticker}"
            )

            message = format_exit_message(
                ticker,
                row,
                trade_date
            )

            send_telegram(
                message
            )

        else:

            print(
                "ℹ️ Không có tín hiệu mới."
            )

        # ----------------------------------------------------
        # SAVE STATE
        # ----------------------------------------------------

        state[ticker] = {
            "date": trade_date,
            "signal": bool(
                current_signal
            ),
            "close": float(
                row["Close"]
            ),
            "volume_ratio": float(
                row["Volume_Ratio"]
            ),
            "macd_hist": float(
                row["MACD_Hist"]
            ),
            "roc10": float(
                row["ROC10"]
            ),
            "adx14": float(
                row["ADX14"]
            ),
        }

    except Exception as e:

        print(
            f"❌ {ticker}: ERROR"
        )

        print(
            f"   {type(e).__name__}: {e}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "ST5 — V1.1 DAILY ENGINE"
    )
    print(
        "14 SURVIVOR TICKERS"
    )
    print("=" * 70)

    print(
        f"Root : {ROOT_DIR}"
    )

    print(
        f"State: {STATE_FILE}"
    )

    print()
    print(
        "FROZEN V1.1:"
    )

    print(
        "Volume Ratio > 1"
    )

    print(
        "MACD Histogram > 0"
    )

    print(
        "ROC10 > 2"
    )

    print(
        "ADX14 > 30"
    )

    print()
    print(
        f"Số mã: {len(TICKERS)}"
    )

    state = load_state()

    for ticker in TICKERS:

        process_ticker(
            ticker,
            state
        )

    save_state(
        state
    )

    print()
    print("=" * 70)
    print(
        "V1.1 DAILY ENGINE FINISHED"
    )
    print("=" * 70)

    print(
        f"State saved: {STATE_FILE}"
    )


if __name__ == "__main__":
    main() 
