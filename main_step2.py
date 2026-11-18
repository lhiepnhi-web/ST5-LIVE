"""
ST5 STREAMLINED ENGINE - Yahoo Finance (Wilder ADX + Optimized Multi-Strategy)
Hệ thống giao dịch định lượng DUNGSI (Production)
"""
import sys
import os, json, time
from datetime import datetime, timedelta
import pytz, requests
import pandas as pd
import numpy as np
import warnings
import logging
import yfinance as yf

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_step2 import (
    RULES, POSITION_SIZE, MAX_POSITIONS, CAPITAL_INITIAL,
    TIMEZONE, STATE_FILE, TELEGRAM_TITLE, DELAY_BETWEEN_TICKERS,
)

# ============ DATA PULLING (YAHOO FINANCE) ============
def get_intraday_data(ticker, days=400):
    end = datetime.now()
    start = end - timedelta(days=days)
    yf_ticker = f"{ticker}.VN"
    try:
        df = yf.download(yf_ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d", progress=False)
        if df is None or len(df) == 0:
            return pd.DataFrame()
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        col_map = {}
        for c in df.columns:
            c_lower = str(c).lower()
            if 'date' in c_lower: col_map[c] = 'Date'
            elif 'open' in c_lower: col_map[c] = 'Open'
            elif 'high' in c_lower: col_map[c] = 'High'
            elif 'low' in c_lower: col_map[c] = 'Low'
            elif 'close' in c_lower and 'adj' not in c_lower: col_map[c] = 'Close'
            elif 'volume' in c_lower: col_map[c] = 'Volume'
        df = df.rename(columns=col_map)
        
        required_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        if not all(rc in df.columns for rc in required_cols):
            return pd.DataFrame()
            
        df = df[required_cols].copy()
        if df["Date"].dt.tz is not None:
            df["Date"] = df["Date"].dt.tz_localize(None)
        df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
        
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            
        return df.dropna().drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    except Exception as e:
        print(f"[{ticker}] Lỗi tải dữ liệu: {e}")
        return pd.DataFrame()

# ============ TÍNH CHỈ BÁO (CHUẨN WILDER'S SMOOTHING) ============
def _calc_indicators_fallback(df):
    d = df.copy()
    d['MA50'] = d['Close'].rolling(50).mean()
    d['MA200'] = d['Close'].rolling(200).mean()
    d['Vol_MA20'] = d['Volume'].rolling(20).mean()
    d['VolumeRatio'] = d['Volume'] / d['Vol_MA20']
    d['ROC10'] = (d['Close'] / d['Close'].shift(10) - 1) * 100
    
    exp12 = d['Close'].ewm(span=12, adjust=False).mean()
    exp26 = d['Close'].ewm(span=26, adjust=False).mean()
    d['MACD'] = exp12 - exp26
    d['MACD_Signal'] = d['MACD'].ewm(span=9, adjust=False).mean()
    d['MACD_Hist'] = d['MACD'] - d['MACD_Signal']
    
    high, low, close = d['High'], d['Low'], d['Close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    def wilder_smooth(series):
        return series.ewm(alpha=1/14, adjust=False).mean()
        
    d['ATR14'] = wilder_smooth(tr)
    d['Plus_DI'] = 100 * (pd.Series(plus_dm, index=d.index).pipe(wilder_smooth) / d['ATR14'])
    d['Minus_DI'] = 100 * (pd.Series(minus_dm, index=d.index).pipe(wilder_smooth) / d['ATR14'])
    
    di_sum = d['Plus_DI'] + d['Minus_DI']
    di_sum = di_sum.replace(0, np.nan)
    dx = 100 * (d['Plus_DI'] - d['Minus_DI']).abs() / di_sum
    d['ADX14'] = dx.pipe(wilder_smooth)
    
    return d

# ============ SETUP ============
VN_TZ = pytz.timezone(TIMEZONE)
now = datetime.now(VN_TZ)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
state_path = os.path.join(BASE_DIR, STATE_FILE)

print(f"===== {TELEGRAM_TITLE} - {now.strftime('%Y-%m-%d %H:%M:%S %Z')} =====")

if now.weekday() >= 5:
    print("Cuối tuần - Bỏ qua.")
    sys.exit(0)

current_time = now.hour * 100 + now.minute
if current_time < 900 or current_time > 1500:
    print(f"[{now.strftime('%H:%M')}] Ngoài giờ giao dịch (09:00 - 15:00). Bỏ qua.")
    sys.exit(0)

state = {"positions": {}, "last_signals": {}, "cash": CAPITAL_INITIAL, "last_run": None}
if os.path.exists(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            for k in state: 
                if k in loaded: state[k] = loaded[k]
    except Exception as e:
        print(f"[state load fail] {e}")

ticker_cache = {}
success_tickers = set()
fail_tickers = set()

def get_cached_data(tk, days=400):
    if tk in ticker_cache:
        return ticker_cache[tk]
    df = get_intraday_data(tk, days=days)
    ticker_cache[tk] = df
    return df

def check_signal(df, p):
    d = df.copy()
    d = _calc_indicators_fallback(d)
    d = d.dropna().reset_index(drop=True)
    if len(d) == 0: return None, None
    
    r = d.iloc[-1]
    conds = [
        r["VolumeRatio"] > p["volr"],
        r["ROC10"]       > p["roc"],
        r["MACD_Hist"]   > p["macd"],
        r["ADX14"]       > p["adx"],
    ]
    if p.get("ma200"): conds.append(r["Close"] > r["MA200"])
    if p.get("ma50"):  conds.append(r["Close"] > r["MA50"])
    return bool(all(conds)), r

def business_days_since(date_str, now_dt):
    try:
        d1 = datetime.strptime(date_str, "%Y-%m-%d")
        n = 0; cur = d1
        while cur.date() < now_dt.date():
            cur += timedelta(days=1)
            if cur.weekday() < 5: n += 1
        return n
    except Exception:
        return 999

def send_telegram(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat  = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(f"[TG SKIP]\n{msg}"); return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"[TG FAIL] {e}")

signal_map = {}

for rule_name, rule in RULES.items():
    print(f"\n--- Quét nhóm chiến lược tối ưu: {rule_name} ({len(rule['tickers'])} mã) ---")
    for tk in rule["tickers"]:
        key = f"{tk}__{rule_name}"
        try:
            df = get_cached_data(tk)
            if len(df) < 50: 
                fail_tickers.add(tk)
                print(f"  [{tk}] Bỏ qua (không đủ dữ liệu)")
                continue
            
            success_tickers.add(tk)
            sig, r = check_signal(df, rule)
            if sig is None: continue
                
            status_icon = "MUA" if sig else "Không"
            print(f"  [{tk}] {status_icon} | VolR={r['VolumeRatio']:.2f} ADX={r['ADX14']:.1f} ROC={r['ROC10']:.1f}")
            
            prev = state["last_signals"].get(key, False)
            pos = state["positions"].get(key)
            
            if sig and not prev and not pos:
                already_held = any(k.startswith(f"{tk}__") for k in state["positions"])
                if already_held:
                    state["last_signals"][key] = sig
                    continue
                if len(state["positions"]) < MAX_POSITIONS and state["cash"] >= POSITION_SIZE:
                    state["cash"] -= POSITION_SIZE
                    state["positions"][key] = {
                        "entry_date": str(now.date()), "entry_price": float(r["Close"]),
                        "size": POSITION_SIZE, "volr": round(float(r["VolumeRatio"]), 2),
                        "adx": round(float(r["ADX14"]), 2),
                    }
                    signal_map.setdefault(tk, []).append({
                        "rule": rule_name, "action": "BUY",
                        "volr": float(r["VolumeRatio"]), "adx": float(r["ADX14"]), "roc": float(r["ROC10"]),
                    })
            elif (not sig) and prev and pos:
                hold = business_days_since(pos["entry_date"], now)
                if hold >= rule["mh"]:
                    ret = float(r["Close"]) / float(pos["entry_price"])
                    state["cash"] += float(pos["size"]) * ret
                    signal_map.setdefault(tk, []).append({
                        "rule": rule_name, "action": "SELL", "ret": ret - 1, "hold": hold,
                    })
                    del state["positions"][key]
            state["last_signals"][key] = sig
            time.sleep(DELAY_BETWEEN_TICKERS)
        except Exception as e:
            print(f"  [{tk}] Lỗi: {e}")
            fail_tickers.add(tk)
            time.sleep(DELAY_BETWEEN_TICKERS)

state["last_run"] = str(now)
buys = {tk: sigs for tk, sigs in signal_map.items() if any(s["action"]=="BUY" for s in sigs)}
sells = {tk: sigs for tk, sigs in signal_map.items() if any(s["action"]=="SELL" for s in sigs)}

with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

if buys or sells:
    lines = [f"<b>{TELEGRAM_TITLE}</b> - {now.strftime('%Y-%m-%d %H:%M')}"]
    if buys:
        lines.append(f"\n<b>MUA ({len(buys)}):</b>")
        for tk, sigs in sorted(buys.items(), key=lambda x: -len([s for s in x[1] if s["action"]=="BUY"])):
            buy_sigs = [s for s in sigs if s["action"]=="BUY"]
            strength = "🔥" * min(len(buy_sigs), 3)
            rules_str = " + ".join(s["rule"] for s in buy_sigs)
            volr = buy_sigs[0]["volr"]; adx = buy_sigs[0]["adx"]; roc = buy_sigs[0]["roc"]
            lines.append(f"  {strength} <b>{tk}</b> ({rules_str})")
            lines.append(f"     VolR={volr:.2f} ADX={adx:.1f} ROC={roc:.1f}")
    if sells:
        lines.append(f"\n<b>BÁN ({len(sells)}):</b>")
        for tk, sigs in sells.items():
            sell_sigs = [s for s in sigs if s["action"]=="SELL"]
            for s in sell_sigs:
                lines.append(f"  - {tk} - {s['rule']} (giữ {s['hold']} phiên, {s['ret']*100:+.2f}%)")
    lines.append(f"\nCash: {state['cash']/1e9:.4f} tỷ | Pos: {len(state['positions'])}")
    send_telegram("\n".join(lines))
else:
    msg = f"<b>{TELEGRAM_TITLE}</b> - {now.strftime('%H:%M')}\nTrạng thái: Không có tín hiệu mới.\nCash: {state['cash']/1e9:.4f} tỷ | Đang giữ: {len(state['positions'])} mã"
    send_telegram(msg)
    print("\nKhông có tín hiệu mới - Đã gửi tin nhắn Heartbeat.")

print(f"\n===== DONE - {len(buys)} BUY signals, {len(sells)} SELL signals =====")
"""
ST5 STREAMLINED ENGINE - Yahoo Finance (Wilder ADX + Optimized Multi-Strategy)
Hệ thống giao dịch định lượng DUNGSI (Production)
"""
import sys
import os, json, time
from datetime import datetime, timedelta
import pytz, requests
import pandas as pd
import numpy as np
import warnings
import logging
import yfinance as yf

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_step2 import (
    RULES, POSITION_SIZE, MAX_POSITIONS, CAPITAL_INITIAL,
    TIMEZONE, STATE_FILE, TELEGRAM_TITLE, DELAY_BETWEEN_TICKERS,
)

# ============ DATA PULLING (YAHOO FINANCE) ============
def get_intraday_data(ticker, days=400):
    end = datetime.now()
    start = end - timedelta(days=days)
    yf_ticker = f"{ticker}.VN"
    try:
        df = yf.download(yf_ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d", progress=False)
        if df is None or len(df) == 0:
            return pd.DataFrame()
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        col_map = {}
        for c in df.columns:
            c_lower = str(c).lower()
            if 'date' in c_lower: col_map[c] = 'Date'
            elif 'open' in c_lower: col_map[c] = 'Open'
            elif 'high' in c_lower: col_map[c] = 'High'
            elif 'low' in c_lower: col_map[c] = 'Low'
            elif 'close' in c_lower and 'adj' not in c_lower: col_map[c] = 'Close'
            elif 'volume' in c_lower: col_map[c] = 'Volume'
        df = df.rename(columns=col_map)
        
        required_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        if not all(rc in df.columns for rc in required_cols):
            return pd.DataFrame()
            
        df = df[required_cols].copy()
        if df["Date"].dt.tz is not None:
            df["Date"] = df["Date"].dt.tz_localize(None)
        df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
        
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            
        return df.dropna().drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    except Exception as e:
        print(f"[{ticker}] Lỗi tải dữ liệu: {e}")
        return pd.DataFrame()

# ============ TÍNH CHỈ BÁO (CHUẨN WILDER'S SMOOTHING) ============
def _calc_indicators_fallback(df):
    d = df.copy()
    d['MA50'] = d['Close'].rolling(50).mean()
    d['MA200'] = d['Close'].rolling(200).mean()
    d['Vol_MA20'] = d['Volume'].rolling(20).mean()
    d['VolumeRatio'] = d['Volume'] / d['Vol_MA20']
    d['ROC10'] = (d['Close'] / d['Close'].shift(10) - 1) * 100
    
    exp12 = d['Close'].ewm(span=12, adjust=False).mean()
    exp26 = d['Close'].ewm(span=26, adjust=False).mean()
    d['MACD'] = exp12 - exp26
    d['MACD_Signal'] = d['MACD'].ewm(span=9, adjust=False).mean()
    d['MACD_Hist'] = d['MACD'] - d['MACD_Signal']
    
    high, low, close = d['High'], d['Low'], d['Close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    def wilder_smooth(series):
        return series.ewm(alpha=1/14, adjust=False).mean()
        
    d['ATR14'] = wilder_smooth(tr)
    d['Plus_DI'] = 100 * (pd.Series(plus_dm, index=d.index).pipe(wilder_smooth) / d['ATR14'])
    d['Minus_DI'] = 100 * (pd.Series(minus_dm, index=d.index).pipe(wilder_smooth) / d['ATR14'])
    
    di_sum = d['Plus_DI'] + d['Minus_DI']
    di_sum = di_sum.replace(0, np.nan)
    dx = 100 * (d['Plus_DI'] - d['Minus_DI']).abs() / di_sum
    d['ADX14'] = dx.pipe(wilder_smooth)
    
    return d

# ============ SETUP ============
VN_TZ = pytz.timezone(TIMEZONE)
now = datetime.now(VN_TZ)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
state_path = os.path.join(BASE_DIR, STATE_FILE)

print(f"===== {TELEGRAM_TITLE} - {now.strftime('%Y-%m-%d %H:%M:%S %Z')} =====")

if now.weekday() >= 5:
    print("Cuối tuần - Bỏ qua.")
    sys.exit(0)

current_time = now.hour * 100 + now.minute
if current_time < 900 or current_time > 1500:
    print(f"[{now.strftime('%H:%M')}] Ngoài giờ giao dịch (09:00 - 15:00). Bỏ qua.")
    sys.exit(0)

state = {"positions": {}, "last_signals": {}, "cash": CAPITAL_INITIAL, "last_run": None}
if os.path.exists(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            for k in state: 
                if k in loaded: state[k] = loaded[k]
    except Exception as e:
        print(f"[state load fail] {e}")

ticker_cache = {}
success_tickers = set()
fail_tickers = set()

def get_cached_data(tk, days=400):
    if tk in ticker_cache:
        return ticker_cache[tk]
    df = get_intraday_data(tk, days=days)
    ticker_cache[tk] = df
    return df

def check_signal(df, p):
    d = df.copy()
    d = _calc_indicators_fallback(d)
    d = d.dropna().reset_index(drop=True)
    if len(d) == 0: return None, None
    
    r = d.iloc[-1]
    conds = [
        r["VolumeRatio"] > p["volr"],
        r["ROC10"]       > p["roc"],
        r["MACD_Hist"]   > p["macd"],
        r["ADX14"]       > p["adx"],
    ]
    if p.get("ma200"): conds.append(r["Close"] > r["MA200"])
    if p.get("ma50"):  conds.append(r["Close"] > r["MA50"])
    return bool(all(conds)), r

def business_days_since(date_str, now_dt):
    try:
        d1 = datetime.strptime(date_str, "%Y-%m-%d")
        n = 0; cur = d1
        while cur.date() < now_dt.date():
            cur += timedelta(days=1)
            if cur.weekday() < 5: n += 1
        return n
    except Exception:
        return 999

def send_telegram(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat  = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(f"[TG SKIP]\n{msg}"); return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"[TG FAIL] {e}")

signal_map = {}

for rule_name, rule in RULES.items():
    print(f"\n--- Quét nhóm chiến lược tối ưu: {rule_name} ({len(rule['tickers'])} mã) ---")
    for tk in rule["tickers"]:
        key = f"{tk}__{rule_name}"
        try:
            df = get_cached_data(tk)
            if len(df) < 50: 
                fail_tickers.add(tk)
                print(f"  [{tk}] Bỏ qua (không đủ dữ liệu)")
                continue
            
            success_tickers.add(tk)
            sig, r = check_signal(df, rule)
            if sig is None: continue
                
            status_icon = "MUA" if sig else "Không"
            print(f"  [{tk}] {status_icon} | VolR={r['VolumeRatio']:.2f} ADX={r['ADX14']:.1f} ROC={r['ROC10']:.1f}")
            
            prev = state["last_signals"].get(key, False)
            pos = state["positions"].get(key)
            
            if sig and not prev and not pos:
                already_held = any(k.startswith(f"{tk}__") for k in state["positions"])
                if already_held:
                    state["last_signals"][key] = sig
                    continue
                if len(state["positions"]) < MAX_POSITIONS and state["cash"] >= POSITION_SIZE:
                    state["cash"] -= POSITION_SIZE
                    state["positions"][key] = {
                        "entry_date": str(now.date()), "entry_price": float(r["Close"]),
                        "size": POSITION_SIZE, "volr": round(float(r["VolumeRatio"]), 2),
                        "adx": round(float(r["ADX14"]), 2),
                    }
                    signal_map.setdefault(tk, []).append({
                        "rule": rule_name, "action": "BUY",
                        "volr": float(r["VolumeRatio"]), "adx": float(r["ADX14"]), "roc": float(r["ROC10"]),
                    })
            elif (not sig) and prev and pos:
                hold = business_days_since(pos["entry_date"], now)
                if hold >= rule["mh"]:
                    ret = float(r["Close"]) / float(pos["entry_price"])
                    state["cash"] += float(pos["size"]) * ret
                    signal_map.setdefault(tk, []).append({
                        "rule": rule_name, "action": "SELL", "ret": ret - 1, "hold": hold,
                    })
                    del state["positions"][key]
            state["last_signals"][key] = sig
            time.sleep(DELAY_BETWEEN_TICKERS)
        except Exception as e:
            print(f"  [{tk}] Lỗi: {e}")
            fail_tickers.add(tk)
            time.sleep(DELAY_BETWEEN_TICKERS)

state["last_run"] = str(now)
buys = {tk: sigs for tk, sigs in signal_map.items() if any(s["action"]=="BUY" for s in sigs)}
sells = {tk: sigs for tk, sigs in signal_map.items() if any(s["action"]=="SELL" for s in sigs)}

with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

if buys or sells:
    lines = [f"<b>{TELEGRAM_TITLE}</b> - {now.strftime('%Y-%m-%d %H:%M')}"]
    if buys:
        lines.append(f"\n<b>MUA ({len(buys)}):</b>")
        for tk, sigs in sorted(buys.items(), key=lambda x: -len([s for s in x[1] if s["action"]=="BUY"])):
            buy_sigs = [s for s in sigs if s["action"]=="BUY"]
            strength = "🔥" * min(len(buy_sigs), 3)
            rules_str = " + ".join(s["rule"] for s in buy_sigs)
            volr = buy_sigs[0]["volr"]; adx = buy_sigs[0]["adx"]; roc = buy_sigs[0]["roc"]
            lines.append(f"  {strength} <b>{tk}</b> ({rules_str})")
            lines.append(f"     VolR={volr:.2f} ADX={adx:.1f} ROC={roc:.1f}")
    if sells:
        lines.append(f"\n<b>BÁN ({len(sells)}):</b>")
        for tk, sigs in sells.items():
            sell_sigs = [s for s in sigs if s["action"]=="SELL"]
            for s in sell_sigs:
                lines.append(f"  - {tk} - {s['rule']} (giữ {s['hold']} phiên, {s['ret']*100:+.2f}%)")
    lines.append(f"\nCash: {state['cash']/1e9:.4f} tỷ | Pos: {len(state['positions'])}")
    send_telegram("\n".join(lines))
else:
    msg = f"<b>{TELEGRAM_TITLE}</b> - {now.strftime('%H:%M')}\nTrạng thái: Không có tín hiệu mới.\nCash: {state['cash']/1e9:.4f} tỷ | Đang giữ: {len(state['positions'])} mã"
    send_telegram(msg)
    print("\nKhông có tín hiệu mới - Đã gửi tin nhắn Heartbeat.")

print(f"\n===== DONE - {len(buys)} BUY signals, {len(sells)} SELL signals =====")
