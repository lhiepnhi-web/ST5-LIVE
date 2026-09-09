# ============================================================
# ST5 — V1.1 DAILY LIVE ENGINE
# DÙNG DAILY CANDLE ĐANG HÌNH THÀNH TRONG PHIÊN
# ============================================================

import os
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from vnstock import Quote

TICKERS = [
    "NVL", "VND", "ABB", "BFC", "C69", "CEO",
    "CII", "DXG", "HPG", "NAF", "OIL", "SHS",
    "VIX", "VPB",
]

STATE_FILE = "data/v11_daily_state.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ thiếu Telegram secrets")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=20,
        )
        return response.ok
    except Exception as e:
        print(f"❌ Telegram: {e}")
        return False


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_trading_hours():
    """Kiểm tra giờ giao dịch VN"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return (
        "09:15" <= t <= "11:30"
        or "13:00" <= t <= "14:30"
    )


def get_live_indicators(ticker):
    """
    Lấy dữ liệu INTRADAY 5M → build Daily candle ĐANG HÌNH THÀNH
    """
    try:
        quote = Quote(symbol=ticker, source="KBS")
        df5 = quote.history(
            start=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
            end=datetime.now().strftime("%Y-%m-%d"),
            interval="5m",
        )
        
        if df5 is None or df5.empty:
            return None
        
        df5["Date"] = pd.to_datetime(df5["time"])
        df5 = df5.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })
        
        # Build Daily đang hình thành
        df5["Day"] = df5["Date"].dt.date
        
        daily = df5.groupby("Day").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
            "Date": "last",
        }).reset_index(drop=True)
        
        daily = daily.tail(30).reset_index(drop=True)
        
        # Tính indicators
        daily = add_indicators(daily)
        
        return daily.iloc[-1] if len(daily) > 0 else None
    except:
        return None


def add_indicators(df):
    df = df.copy()
    
    # Volume Ratio
    df["VolumeRatio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    
    # MACD
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD_Hist"] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()
    
    # ROC10
    df["ROC10"] = df["Close"].pct_change(10) * 100
    
    # ADX14 Wilder
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    atr14 = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm).ewm(alpha=1/14, adjust=False).mean() / atr14
    minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1/14, adjust=False).mean() / atr14
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df["ADX14"] = pd.Series(dx).ewm(alpha=1/14, adjust=False).mean()
    
    return df


def run_v11_live():
    if not is_trading_hours():
        print("❌ Ngoài giờ giao dịch")
        return
    
    state = load_state()
    signals = 0
    
    for ticker in TICKERS:
        row = get_live_indicators(ticker)
        if row is None:
            continue
        
        entry_now = (
            row["VolumeRatio"] > 1
            and row["MACD_Hist"] > 0
            and row["ROC10"] > 2
            and row["ADX14"] > 30
        )
        
        ticker_state = state.get(ticker, {})
        in_position = ticker_state.get("in_position", False)
        today = datetime.now().strftime("%Y-%m-%d")
        
        if not in_position and entry_now:
            # BUY SIGNAL
            if ticker_state.get("last_event_date") != today:
                msg = (
                    f"🟢 ST5 V1.1 — BUY\n"
                    f"Ticker: {ticker}\n"
                    f"Close: {row['Close']}\n"
                    f"VolumeRatio: {row['VolumeRatio']:.2f}\n"
                    f"MACD: {row['MACD_Hist']:.4f}\n"
                    f"ROC10: {row['ROC10']:.2f}\n"
                    f"ADX14: {row['ADX14']:.2f}"
                )
                if send_telegram(msg):
                    state[ticker] = {
                        "in_position": True,
                        "last_event": "BUY",
                        "last_event_date": today,
                    }
                    signals += 1
        
        elif in_position and not entry_now:
            # SELL SIGNAL
            if ticker_state.get("last_event_date") != today:
                msg = (
                    f"🔴 ST5 V1.1 — SELL\n"
                    f"Ticker: {ticker}\n"
                    f"Close: {row['Close']}\n"
                    f"Reason: 1/4 điều kiện FALSE"
                )
                if send_telegram(msg):
                    state[ticker] = {
                        "in_position": False,
                        "last_event": "SELL",
                        "last_event_date": today,
                    }
                    signals += 1
    
    save_state(state)
    print(f"✅ {signals} tín hiệu đã gửi")


if __name__ == "__main__":
    run_v11_live()
