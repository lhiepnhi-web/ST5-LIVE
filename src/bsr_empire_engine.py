# ============================================================
# BSR EMPIRE — 33 CHIẾN BINH DAILY ENGINE
# Chạy song song với V1.1 CII
# ============================================================

import os
import json
import requests
import numpy as np
import pandas as pd

# ============================================================
# BSR EMPIRE — 33 SURVIVORS FROZEN
# ============================================================

TICKERS = [
    'VND', 'APS', 'CEO', 'SSI', 'SHS', 'VPB', 'GEX', 'IDI', 'NKG', 'CII',
    'LPB', 'NAF', 'CSV', 'FRT', 'CCL', 'HHS', 'TCH', 'VCI', 'VGI', 'BSR',
    'FTS', 'CTF', 'HPG', 'CKG', 'ASP', 'KDC', 'BFC', 'YEG', 'PDR', 'DGC',
    'DXG', 'NVL', 'MWG',
]

# ============================================================
# PATH
# ============================================================

DATA_DIR = "data"
STATE_FILE = "data/bsr_empire_state.json"

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ BSR: thiếu Telegram secrets")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=20,
        )
        if response.ok:
            print("📨 Telegram: OK")
            return True
        print("❌ Telegram lỗi:", response.status_code, response.text)
        return False
    except Exception as e:
        print("❌ Telegram exception:", type(e).__name__, str(e))
        return False


# ============================================================
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            return {}
        return state
    except Exception as e:
        print("⚠️ Không đọc được BSR state:", type(e).__name__, str(e))
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, STATE_FILE)


# ============================================================
# DATA
# ============================================================

def find_data_file(ticker):
    candidates = [
        os.path.join(DATA_DIR, f"{ticker}.csv"),
        os.path.join(DATA_DIR, "DAILY", f"{ticker}.csv"),
        os.path.join(DATA_DIR, "daily", f"{ticker}.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def load_daily(ticker):
    file_path = find_data_file(ticker)
    if file_path is None:
        print(f"⚠️ {ticker}: không tìm thấy daily CSV")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"❌ {ticker}: đọc CSV lỗi:", type(e).__name__, str(e))
        return pd.DataFrame()

    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key == "date":
            rename_map[col] = "Date"
        elif key == "open":
            rename_map[col] = "Open"
        elif key == "high":
            rename_map[col] = "High"
        elif key == "low":
            rename_map[col] = "Low"
        elif key == "close":
            rename_map[col] = "Close"
        elif key == "volume":
            rename_map[col] = "Volume"

    df = df.rename(columns=rename_map)

    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in df.columns]

    if missing:
        print(f"❌ {ticker}: thiếu cột {missing}")
        return pd.DataFrame()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    for col in required[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)
    df = df.sort_values("Date")
    df = df.drop_duplicates(subset=["Date"], keep="last")

    return df.reset_index(drop=True)


# ============================================================
# WILDER RMA
# ============================================================

def wilder_rma(series, period=14):
    return series.ewm(alpha=1/period, adjust=False, min_periods=period).mean()


# ============================================================
# INDICATORS
# ============================================================

def add_indicators(df):
    df = df.copy()

    # Volume Ratio
    volume_ma20 = df["Volume"].rolling(20, min_periods=20).mean()
    df["VolumeRatio"] = df["Volume"] / volume_ma20

    # MACD Histogram
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = macd - macd_signal

    # ROC10
    df["ROC10"] = df["Close"].pct_change(10) * 100

    # ADX14 Wilder
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(((up_move > down_move) & (up_move > 0)), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where(((down_move > up_move) & (down_move > 0)), down_move, 0.0),
        index=df.index,
    )

    atr14 = wilder_rma(tr, 14)
    plus_di = 100 * wilder_rma(plus_dm, 14) / atr14
    minus_di = 100 * wilder_rma(minus_dm, 14) / atr14
    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    df["ADX14"] = wilder_rma(dx, 14)

    return df


# ============================================================
# FROZEN V1.1 LAW
# ============================================================

def v11_entry(row):
    return (
        row["VolumeRatio"] > 1
        and row["MACD_Hist"] > 0
        and row["ROC10"] > 2
        and row["ADX14"] > 30
    )


def indicators_valid(row):
    values = [
        row.get("VolumeRatio"),
        row.get("MACD_Hist"),
        row.get("ROC10"),
        row.get("ADX14"),
    ]
    return all(pd.notna(x) for x in values)


# ============================================================
# FORMAT
# ============================================================

def fmt_date(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def signal_text(ticker, row, action, reason=""):
    vr = row["VolumeRatio"]
    roc = row["ROC10"]
    macd = row["MACD_Hist"]
    adx = row["ADX14"]

    emoji = "🟢" if action == "BUY" else "🔴"

    message = (
        f"{emoji} BSR EMPIRE — {action}\n"
        f"\n"
        f"Ticker: {ticker}\n"
        f"Date: {fmt_date(row['Date'])}\n"
        f"Close: {row['Close']}\n"
        f"\n"
        f"V1.1 FROZEN\n"
        f"Volume Ratio: {vr:.2f}\n"
        f"MACD Histogram: {macd:.4f}\n"
        f"ROC10: {roc:.2f}\n"
        f"ADX14: {adx:.2f}\n"
    )

    if reason:
        message += f"\nReason: {reason}\n"

    return message


# ============================================================
# PROCESS ONE TICKER
# ============================================================

def process_ticker(ticker, state):
    print()
    print("-" * 70)
    print(f"BSR EMPIRE — {ticker}")

    df = load_daily(ticker)

    if df.empty:
        return False

    df = add_indicators(df)

    if len(df) < 2:
        print(f"⚠️ {ticker}: chưa đủ dữ liệu")
        return False

    latest = df.iloc[-1]
    latest_date = pd.Timestamp(latest["Date"])

    print(f"Date : {fmt_date(latest_date)}")
    print(f"Close: {latest['Close']}")

    if not indicators_valid(latest):
        print("⚠️ Indicator chưa đủ")
        return False

    entry_now = v11_entry(latest)

    print(f"VolumeRatio : {latest['VolumeRatio']:.4f} {'✅' if latest['VolumeRatio'] > 1 else '❌'}")
    print(f"MACD Hist   : {latest['MACD_Hist']:.6f} {'✅' if latest['MACD_Hist'] > 0 else '❌'}")
    print(f"ROC10       : {latest['ROC10']:.4f} {'✅' if latest['ROC10'] > 2 else '❌'}")
    print(f"ADX14       : {latest['ADX14']:.4f} {'✅' if latest['ADX14'] > 30 else '❌'}")

    # State
    ticker_state = state.get(ticker, {})
    if not isinstance(ticker_state, dict):
        ticker_state = {}

    in_position = bool(ticker_state.get("in_position", False))
    entry_date = ticker_state.get("entry_date")
    last_event = ticker_state.get("last_event")
    last_event_date = ticker_state.get("last_event_date")

    # CASE 1 — BUY
    if not in_position:
        if not entry_now:
            print("→ WAIT")
            return False

        event_key = f"{ticker}|BUY|{fmt_date(latest_date)}"

        if last_event == "BUY" and last_event_date == fmt_date(latest_date):
            print("⚠️ BUY đã xử lý")
            return False

        message = signal_text(ticker=ticker, row=latest, action="BUY")

        if not send_telegram(message):
            return False

        state[ticker] = {
            "in_position": True,
            "entry_date": fmt_date(latest_date),
            "last_event": "BUY",
            "last_event_date": fmt_date(latest_date),
        }

        print("✅ BUY:", event_key)
        return True

    # CASE 2 — EXIT
    if entry_date is None:
        print("⚠️ State thiếu entry_date")
        return False

    entry_ts = pd.Timestamp(entry_date)

    if latest_date <= entry_ts:
        print("→ HOLD — cùng phiên BUY")
        return False

    exit_reason = None

    if latest["VolumeRatio"] <= 1:
        exit_reason = "Volume Ratio <= 1"
    elif latest["MACD_Hist"] <= 0:
        exit_reason = "MACD Histogram <= 0"
    elif latest["ROC10"] <= 2:
        exit_reason = "ROC10 <= 2"
    elif latest["ADX14"] <= 30:
        exit_reason = "ADX14 <= 30"

    if exit_reason is None:
        print("→ HOLD — đủ 4 điều kiện")
        return False

    event_key = f"{ticker}|EXIT|{fmt_date(latest_date)}"

    if last_event == "EXIT" and last_event_date == fmt_date(latest_date):
        print("⚠️ EXIT đã xử lý")
        return False

    message = signal_text(ticker=ticker, row=latest, action="EXIT", reason=exit_reason)

    if not send_telegram(message):
        return False

    state[ticker] = {
        "in_position": False,
        "entry_date": None,
        "last_event": "EXIT",
        "last_event_date": fmt_date(latest_date),
    }

    print("✅ EXIT:", event_key)
    return True


# ============================================================
# MAIN
# ============================================================

def run_bsr_empire():
    print()
    print("=" * 70)
    print("BSR EMPIRE — DAILY ENGINE")
    print("33 CHIẾN BINH — FROZEN")
    print("=" * 70)

    state = load_state()

    processed = 0
    signals = 0
    errors = 0

    for ticker in TICKERS:
        try:
            result = process_ticker(ticker=ticker, state=state)
            processed += 1
            if result:
                signals += 1
            save_state(state)
        except Exception as e:
            errors += 1
            print()
            print(f"❌ {ticker}: LỖI")
            print(f"   {type(e).__name__}: {e}")

    save_state(state)

    print()
    print("=" * 70)
    print("BSR EMPIRE — RESULT")
    print("=" * 70)
    print(f"Universe : {len(TICKERS)}")
    print(f"Processed: {processed}/{len(TICKERS)}")
    print(f"Signals  : {signals}")
    print(f"Errors   : {errors}")
    print(f"State    : {STATE_FILE}")
    print("=" * 70)

    return {"processed": processed, "signals": signals, "errors": errors}


if __name__ == "__main__":
    run_bsr_empire()
