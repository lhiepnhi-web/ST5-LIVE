import os
import json
import requests
import pandas as pd

from config import CORE26
from indicators import add_v14_indicators, v14_signal


# ============================================================
# ST5 LIVE
# 5M TRIGGER + 15M CONFIRM
# V1.4 FROZEN
# ============================================================

STATE_FILE = "data/live_state.json"
DATA_DIR = "data/INTRADAY_5M"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TIMEZONE = "Asia/Ho_Chi_Minh"


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Thiếu Telegram secrets")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

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

    except Exception as e:

        print(
            "❌ Telegram exception:",
            type(e).__name__,
            str(e)
        )

        return False


# ============================================================
# STATE
# ============================================================

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

    except Exception as e:

        print(
            "⚠️ Không đọc được state:",
            type(e).__name__,
            str(e)
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
# TIME
# ============================================================

def now_vietnam():

    return pd.Timestamp.now(
        tz=TIMEZONE
    ).tz_localize(None)


def in_session(dt):

    t = dt.time()

    morning_start = pd.Timestamp(
        "09:15"
    ).time()

    morning_end = pd.Timestamp(
        "11:30"
    ).time()

    afternoon_start = pd.Timestamp(
        "13:00"
    ).time()

    afternoon_end = pd.Timestamp(
        "14:30"
    ).time()

    return (
        (
            morning_start
            <= t
            <= morning_end
        )
        or
        (
            afternoon_start
            <= t
            <= afternoon_end
        )
    )


# ============================================================
# DATA
# ============================================================

def load_5m_file(ticker):

    file_path = os.path.join(
        DATA_DIR,
        f"{ticker}_5m.csv"
    )

    if not os.path.exists(file_path):

        print(
            f"⚠️ {ticker}: không có file "
            f"{file_path}"
        )

        return pd.DataFrame()

    try:

        df = pd.read_csv(
            file_path
        )

    except Exception as e:

        print(
            f"❌ {ticker}: đọc CSV lỗi:",
            type(e).__name__,
            str(e)
        )

        return pd.DataFrame()

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:

        print(
            f"❌ {ticker}: thiếu cột {missing}"
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
        subset=["Date"]
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# 15M
# ============================================================

def build_15m(df5):

    df = df5.copy()

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]
    )

    df = df.sort_values(
        "Date"
    )

    df = df.set_index(
        "Date"
    )

    df15 = (
        df[
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]
        ]
        .resample(
            "15min",
            origin="start_day",
            offset="15min"
        )
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )
        .reset_index()
    )

    return df15


# ============================================================
# BOOLEAN HELPER
# ============================================================

def safe_bool(series):

    return (
        series
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )


# ============================================================
# PROCESS ONE TICKER
# ============================================================

def process_ticker(
    ticker,
    state,
    current_time
):

    print()
    print("-" * 70)
    print(f"Ticker: {ticker}")

    # --------------------------------------------------------
    # READ LOCAL 5M CSV
    # --------------------------------------------------------

    df5 = load_5m_file(
        ticker
    )

    if df5.empty:

        print(
            f"⚠️ {ticker}: không có dữ liệu"
        )

        return False

    # --------------------------------------------------------
    # ONLY COMPLETED 5M CANDLES
    #
    # Giả định timestamp là thời điểm bắt đầu nến.
    # Ví dụ 10:15 = nến 10:15 → 10:20.
    # --------------------------------------------------------

    df5 = df5[
        (
            df5["Date"]
            + pd.Timedelta(minutes=5)
            <= current_time
        )
    ].copy()

    if df5.empty:

        print(
            f"⚠️ {ticker}: chưa có nến 5M hoàn tất"
        )

        return False

    # --------------------------------------------------------
    # V1.4 INDICATORS ON 5M
    # --------------------------------------------------------

    df5 = add_v14_indicators(
        df5
    )

    df5["Trigger"] = safe_bool(
        v14_signal(df5)
    )

    # --------------------------------------------------------
    # BUILD 15M
    # --------------------------------------------------------

    df15 = build_15m(
        df5
    )

    if df15.empty:

        print(
            f"⚠️ {ticker}: không tạo được 15M"
        )

        return False

    # --------------------------------------------------------
    # ONLY COMPLETED 15M CANDLES
    # --------------------------------------------------------

    df15["AvailableAt"] = (
        df15["Date"]
        + pd.Timedelta(minutes=15)
    )

    df15 = df15[
        df15["AvailableAt"]
        <= current_time
    ].copy()

    if df15.empty:

        print(
            f"⚠️ {ticker}: chưa có nến 15M hoàn tất"
        )

        return False

    # --------------------------------------------------------
    # V1.4 INDICATORS ON 15M
    # --------------------------------------------------------

    df15 = add_v14_indicators(
        df15
    )

    df15["Confirm"] = safe_bool(
        v14_signal(df15)
    )

    # Chỉ giữ dữ liệu cần cho merge
    confirm = df15[
        [
            "AvailableAt",
            "Confirm",
            "VolumeRatio",
            "ROC10",
            "MACD_Hist",
            "ADX14"
        ]
    ].copy()

    confirm = confirm.sort_values(
        "AvailableAt"
    )

    # --------------------------------------------------------
    # MERGE 5M + 15M
    #
    # 5M chỉ được sử dụng confirmation
    # sau khi nến 15M đã hoàn tất.
    # --------------------------------------------------------

    df5 = df5.sort_values(
        "Date"
    )

    merged = pd.merge_asof(
        df5,
        confirm,
        left_on="Date",
        right_on="AvailableAt",
        direction="backward"
    )

    # --------------------------------------------------------
    # 15M CONFIRM
    # --------------------------------------------------------

    merged["Confirm"] = safe_bool(
        merged["Confirm"]
    )

    # --------------------------------------------------------
    # FINAL SIGNAL
    #
    # 5M Trigger
    # AND
    # 15M Confirm
    # --------------------------------------------------------

    merged["Signal"] = (
        merged["Trigger"]
        & merged["Confirm"]
    )

    # --------------------------------------------------------
    # ONLY MARKET SESSION
    # --------------------------------------------------------

    merged = merged[
        merged["Date"].apply(
            in_session
        )
    ].copy()

    if len(merged) < 2:

        print(
            f"⚠️ {ticker}: chưa đủ 2 nến "
            f"để xác định BUY/SELL"
        )

        return False

    # --------------------------------------------------------
    # LATEST + PREVIOUS
    # --------------------------------------------------------

    latest = merged.iloc[-1]
    previous = merged.iloc[-2]

    latest_time = pd.Timestamp(
        latest["Date"]
    )

    latest_signal = bool(
        latest["Signal"]
    )

    previous_signal = bool(
        previous["Signal"]
    )

    trigger = bool(
        latest["Trigger"]
    )

    confirm_signal = bool(
        latest["Confirm"]
    )

    # --------------------------------------------------------
    # STATE MACHINE
    #
    # False → True  = BUY
    # True  → False = SELL
    # --------------------------------------------------------

    action = None

    if (
        latest_signal
        and not previous_signal
    ):

        action = "BUY"

    elif (
        not latest_signal
        and previous_signal
    ):

        action = "SELL"

    # --------------------------------------------------------
    # PRINT STATUS
    # --------------------------------------------------------

    print(
        f"Latest 5M : {latest_time}"
    )

    print(
        f"5M Trigger: "
        f"{'✅' if trigger else '❌'}"
    )

    print(
        f"15M Confirm: "
        f"{'✅' if confirm_signal else '❌'}"
    )

    print(
        f"V1.4 Signal: "
        f"{'✅' if latest_signal else '❌'}"
    )

    if action is None:

        print(
            "→ Không có tín hiệu mới"
        )

        return False

    # --------------------------------------------------------
    # DEDUPLICATION
    # --------------------------------------------------------

    state_key = (
        f"{ticker}_{action}_"
        f"{latest_time.strftime('%Y%m%d_%H%M')}"
    )

    if state.get(ticker) == state_key:

        print(
            f"⚠️ Đã gửi trước đó: "
            f"{state_key}"
        )

        return False

    # --------------------------------------------------------
    # INDICATOR VALUES
    # --------------------------------------------------------

    vr = latest.get(
        "VolumeRatio",
        float("nan")
    )

    roc = latest.get(
        "ROC10",
        float("nan")
    )

    macd = latest.get(
        "MACD_Hist",
        float("nan")
    )

    adx = latest.get(
        "ADX14",
        float("nan")
    )

    # 15M values
    vr15 = latest.get(
        "VolumeRatio_y",
        float("nan")
    )

    roc15 = latest.get(
        "ROC10_y",
        float("nan")
    )

    macd15 = latest.get(
        "MACD_Hist_y",
        float("nan")
    )

    adx15 = latest.get(
        "ADX14_y",
        float("nan")
    )

    # --------------------------------------------------------
    # TELEGRAM MESSAGE
    # --------------------------------------------------------

    emoji = (
        "🟢"
        if action == "BUY"
        else "🔴"
    )

    message = (
        f"{emoji} ST5 LIVE — {action}\n"
        f"\n"
        f"Ticker: {ticker}\n"
        f"Time: "
        f"{latest_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"Price: {latest['Close']}\n"
        f"\n"
        f"V1.4 FROZEN\n"
        f"5M Trigger: "
        f"{'✅' if trigger else '❌'}\n"
        f"15M Confirm: "
        f"{'✅' if confirm_signal else '❌'}\n"
        f"\n"
        f"5M indicators:\n"
        f"VolumeRatio = {vr:.2f}\n"
        f"ROC10 = {roc:.2f}\n"
        f"MACD Hist = {macd:.4f}\n"
        f"ADX14 = {adx:.2f}\n"
        f"\n"
        f"15M indicators:\n"
        f"VolumeRatio = {vr15:.2f}\n"
        f"ROC10 = {roc15:.2f}\n"
        f"MACD Hist = {macd15:.4f}\n"
        f"ADX14 = {adx15:.2f}"
    )

    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------

    sent = send_telegram(
        message
    )

    if not sent:

        print(
            "❌ Không cập nhật state "
            "vì Telegram gửi thất bại"
        )

        return False

    # --------------------------------------------------------
    # SAVE STATE
    # --------------------------------------------------------

    state[ticker] = state_key

    save_state(
        state
    )

    print(
        f"✅ Đã xử lý {action}: "
        f"{state_key}"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("ST5 LIVE — CORE26")
    print("5M TRIGGER + 15M CONFIRM")
    print("V1.4 FROZEN")
    print("=" * 70)

    current_time = now_vietnam()

    print(
        f"Vietnam time: "
        f"{current_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # --------------------------------------------------------
    # KHÔNG CHẠY NGOÀI GIỜ GIAO DỊCH
    # --------------------------------------------------------

    if not in_session(
        current_time
    ):

        print()
        print(
            "⏸ Ngoài giờ giao dịch."
        )
        print(
            "Không xử lý tín hiệu."
        )
        print("=" * 70)

        return

    print(
        f"CORE26: {len(CORE26)} ticker"
    )

    # --------------------------------------------------------
    # LOAD STATE
    # --------------------------------------------------------

    state = load_state()

    signals_sent = 0
    processed = 0
    errors = 0

    # --------------------------------------------------------
    # PROCESS CORE26
    # --------------------------------------------------------

    for ticker in CORE26:

        try:

            result = process_ticker(
                ticker=ticker,
                state=state,
                current_time=current_time
            )

            processed += 1

            if result:
                signals_sent += 1

        except Exception as e:

            errors += 1

            print()
            print(
                f"❌ {ticker}: LỖI"
            )

            print(
                f"   {type(e).__name__}: {e}"
            )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("ST5 LIVE — KẾT QUẢ")
    print("=" * 70)

    print(
        f"Processed    : "
        f"{processed}/{len(CORE26)}"
    )

    print(
        f"Signals sent : "
        f"{signals_sent}"
    )

    print(
        f"Errors       : "
        f"{errors}"
    )

    print(
        f"State file   : "
        f"{STATE_FILE}"
    )

    print("=" * 70)


if __name__ == "__main__":

    main() 
