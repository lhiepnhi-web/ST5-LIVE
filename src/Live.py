import os
import json
import requests
import pandas as pd

from config import CORE26
from data import get_5m_data
from indicators import add_v14_indicators, v14_signal


STATE_FILE = "data/live_state.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Thiếu Telegram secrets")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        },
        timeout=20,
    )

    if response.ok:
        print("📨 Telegram: OK")
        return True

    print(
        "❌ Telegram lỗi:",
        response.status_code,
        response.text
    )

    return False


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    os.makedirs(
        os.path.dirname(STATE_FILE),
        exist_ok=True
    )

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


def in_session(dt):
    t = dt.time()

    return (
        (
            pd.Timestamp("09:15").time()
            <= t
            <= pd.Timestamp("11:30").time()
        )
        or
        (
            pd.Timestamp("13:00").time()
            <= t
            <= pd.Timestamp("14:30").time()
        )
    )


def build_15m(df5):
    df = df5.copy()

    df["Date"] = pd.to_datetime(
        df["Date"]
    )

    df = df.sort_values("Date")
    df = df.drop_duplicates("Date")
    df = df.set_index("Date")

    df15 = (
        df.resample(
            "15min",
            origin="start_day",
            offset="15min"
        )
        .agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        })
    )

    df15 = df15.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close"
        ]
    )

    return df15.reset_index()


def process_ticker(ticker):
    print()
    print(f"===== {ticker} =====")

    df5 = get_5m_data(
        ticker,
        days=30
    )

    if df5.empty:
        print("Không có dữ liệu")
        return None

    df5["Date"] = pd.to_datetime(
        df5["Date"]
    )

    df5 = df5.sort_values("Date")
    df5 = df5.drop_duplicates("Date")

    # --------------------------------------------------
    # 15M CONFIRM
    # Chỉ dùng nến 15M đã đóng
    # --------------------------------------------------

    df15 = build_15m(df5)

    df15 = add_v14_indicators(df15)

    df15["Confirm"] = v14_signal(df15)

    # Confirmation của nến 15M hiện tại
    # chỉ có hiệu lực từ nến 5M kế tiếp.
    df15["Confirm"] = (
        df15["Confirm"]
        .shift(1)
        .fillna(False)
        .astype(bool)
    )

    confirm = df15[
        ["Date", "Confirm"]
    ].copy()

    # --------------------------------------------------
    # 5M TRIGGER
    # --------------------------------------------------

    df5 = add_v14_indicators(df5)

    df5["Trigger"] = (
        v14_signal(df5)
        .fillna(False)
        .astype(bool)
    )

    df5 = pd.merge_asof(
        df5.sort_values("Date"),
        confirm.sort_values("Date"),
        on="Date",
        direction="backward",
        allow_exact_matches=True,
    )

    df5["Confirm"] = (
        df5["Confirm"]
        .fillna(False)
        .astype(bool)
    )

    df5["Signal"] = (
        df5["Trigger"]
        & df5["Confirm"]
    )

    # --------------------------------------------------
    # CHỈ LẤY NẾN 5M MỚI NHẤT ĐÃ CÓ
    # --------------------------------------------------

    df5 = df5[
        df5["Date"].apply(in_session)
    ].copy()

    if len(df5) < 2:
        return None

    latest = df5.iloc[-1]
    previous = df5.iloc[-2]

    current_signal = bool(
        latest["Signal"]
    )

    previous_signal = bool(
        previous["Signal"]
    )

    if current_signal and not previous_signal:
        action = "BUY"
    elif not current_signal and previous_signal:
        action = "SELL"
    else:
        action = None

    if action is None:
        print(
            f"{ticker}: không có tín hiệu mới"
        )
        return None

    signal_time = pd.Timestamp(
        latest["Date"]
    ).isoformat()

    return {
        "ticker": ticker,
        "action": action,
        "time": signal_time,
        "price": float(latest["Close"]),
        "volume_ratio": float(
            latest["VolumeRatio"]
        ),
        "roc10": float(
            latest["ROC10"]
        ),
        "macd_hist": float(
            latest["MACD_Hist"]
        ),
        "adx14": float(
            latest["ADX14"]
        ),
    }


def format_message(signal):
    emoji = (
        "🟢"
        if signal["action"] == "BUY"
        else "🔴"
    )

    return (
        f"{emoji} ST5 LIVE — "
        f"{signal['action']}\n\n"
        f"Mã: {signal['ticker']}\n"
        f"Thời gian: {signal['time']}\n"
        f"Giá: {signal['price']:.2f}\n\n"
        f"5M Trigger: ✅\n"
        f"15M Confirm: "
        f"{'✅' if signal['action'] == 'BUY' else '❌'}\n\n"
        f"V1.4\n"
        f"Volume Ratio: "
        f"{signal['volume_ratio']:.2f}\n"
        f"ROC10: "
        f"{signal['roc10']:.2f}\n"
        f"MACD Hist: "
        f"{signal['macd_hist']:.4f}\n"
        f"ADX14: "
        f"{signal['adx14']:.2f}"
    )


def main():
    print("=" * 70)
    print("ST5 LIVE — CORE26")
    print("5M TRIGGER + 15M CONFIRM")
    print("=" * 70)

    state = load_state()

    sent_count = 0

    for ticker in CORE26:

        try:
            signal = process_ticker(
                ticker
            )

            if signal is None:
                continue

            signal_key = (
                f"{signal['ticker']}_"
                f"{signal['action']}_"
                f"{signal['time']}"
            )

            # Chống gửi trùng
            if state.get(ticker) == signal_key:
                print(
                    f"{ticker}: đã gửi trước đó"
                )
                continue

            message = format_message(
                signal
            )

            if send_telegram(message):
                state[ticker] = signal_key
                sent_count += 1

        except Exception as e:
            print(
                f"❌ {ticker}: "
                f"{type(e).__name__}: {e}"
            )

    save_state(state)

    print()
    print("=" * 70)
    print(
        f"Đã gửi Telegram: "
        f"{sent_count}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
