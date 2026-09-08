# ============================================================
# ST5 LIVE — SHARED DAILY LIVE DATA
# ============================================================
# Purpose:
#   Build a Daily dataframe containing:
#   - historical Daily candles
#   - today's developing Daily candle reconstructed from 5M
#
# IMPORTANT:
#   - Does NOT change any strategy rules.
#   - Does NOT fabricate today's candle.
#   - If today's 5M data is unavailable, returns FAIL SAFE.
# ============================================================

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
from vnstock import Quote


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

HISTORY_START = "2015-01-01"
INTRADAY_DAYS = 5


# ------------------------------------------------------------
# NORMALIZE OHLCV
# ------------------------------------------------------------

def normalize_ohlcv(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    df.columns = [str(c).strip().lower() for c in df.columns]

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

    df = df.rename(columns=rename)

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"Thiếu cột OHLCV: {missing}"
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

    df = df.dropna(subset=required)

    df = df.sort_values("Date")

    df = df.drop_duplicates(
        subset=["Date"],
        keep="last"
    )

    return df.reset_index(drop=True)


# ------------------------------------------------------------
# DOWNLOAD DAILY HISTORY
# ------------------------------------------------------------

def download_daily_history(symbol, today):
    quote = Quote(
        symbol=symbol,
        source="KBS"
    )

    df = quote.history(
        start=HISTORY_START,
        end=today.strftime("%Y-%m-%d"),
        interval="1D"
    )

    df = normalize_ohlcv(df)

    if df.empty:
        raise ValueError(
            f"{symbol}: Daily history empty"
        )

    return df


# ------------------------------------------------------------
# DOWNLOAD 5M DATA
# ------------------------------------------------------------

def download_5m(symbol, today):
    quote = Quote(
        symbol=symbol,
        source="KBS"
    )

    start = (
        pd.Timestamp(today)
        - pd.Timedelta(days=INTRADAY_DAYS)
    )

    end = (
        pd.Timestamp(today)
        + pd.Timedelta(days=1)
    )

    df = quote.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="5m"
    )

    df = normalize_ohlcv(df)

    if df.empty:
        return pd.DataFrame()

    return df


# ------------------------------------------------------------
# FIND TODAY'S 5M
# ------------------------------------------------------------

def get_today_5m(df_5m, today):
    if df_5m.empty:
        return pd.DataFrame()

    df = df_5m.copy()

    # Convert timestamp to Vietnam local date.
    #
    # KBS may return timezone-aware or naive timestamps.
    # We deliberately avoid inventing timezone information
    # when the source is already naive.
    if getattr(df["Date"].dt, "tz", None) is not None:
        df["VN_Date"] = (
            df["Date"]
            .dt.tz_convert(VN_TZ)
            .dt.date
        )
    else:
        df["VN_Date"] = df["Date"].dt.date

    return df[
        df["VN_Date"] == today
    ].copy()


# ------------------------------------------------------------
# BUILD TODAY'S DEVELOPING DAILY CANDLE
# ------------------------------------------------------------

def build_today_daily_candle(df_today_5m, today):
    if df_today_5m.empty:
        return None

    df = df_today_5m.sort_values("Date")

    candle = {
        "Date": pd.Timestamp(today),

        "Open": float(
            df.iloc[0]["Open"]
        ),

        "High": float(
            df["High"].max()
        ),

        "Low": float(
            df["Low"].min()
        ),

        "Close": float(
            df.iloc[-1]["Close"]
        ),

        "Volume": float(
            df["Volume"].sum()
        ),
    }

    return candle


# ------------------------------------------------------------
# MAIN FUNCTION
# ------------------------------------------------------------

def get_live_daily(symbol):
    """
    Return:
        {
            "ok": bool,
            "symbol": str,
            "date": date,
            "is_current_day": bool,
            "data": DataFrame,
            "today_candle": dict | None,
            "error": str | None,
        }

    FAIL SAFE:
        If today's 5M data is unavailable, today's candle is NOT
        fabricated and the function returns ok=False.
    """

    now = datetime.now(VN_TZ)
    today = now.date()

    print(
        f"[{symbol}] Live Daily"
    )

    print(
        f"   Vietnam time : {now.isoformat()}"
    )

    # --------------------------------------------------------
    # 1. DAILY HISTORY
    # --------------------------------------------------------

    try:
        daily = download_daily_history(
            symbol,
            today
        )

    except Exception as e:
        return {
            "ok": False,
            "symbol": symbol,
            "date": None,
            "is_current_day": False,
            "data": pd.DataFrame(),
            "today_candle": None,
            "error": (
                f"Daily download failed: {e}"
            ),
        }

    # --------------------------------------------------------
    # 2. 5M DATA
    # --------------------------------------------------------

    try:
        df_5m = download_5m(
            symbol,
            today
        )

    except Exception as e:
        return {
            "ok": False,
            "symbol": symbol,
            "date": None,
            "is_current_day": False,
            "data": daily,
            "today_candle": None,
            "error": (
                f"5M download failed: {e}"
            ),
        }

    # --------------------------------------------------------
    # 3. TODAY 5M
    # --------------------------------------------------------

    today_5m = get_today_5m(
        df_5m,
        today
    )

    if today_5m.empty:
        latest_date = (
            daily["Date"]
            .max()
            .date()
        )

        return {
            "ok": False,
            "symbol": symbol,
            "date": latest_date,
            "is_current_day": False,
            "data": daily,
            "today_candle": None,
            "error": (
                f"NO 5M DATA FOR TODAY "
                f"{today}. "
                f"Latest Daily={latest_date}"
            ),
        }

    # --------------------------------------------------------
    # 4. BUILD CURRENT DAILY CANDLE
    # --------------------------------------------------------

    today_candle = build_today_daily_candle(
        today_5m,
        today
    )

    if today_candle is None:
        return {
            "ok": False,
            "symbol": symbol,
            "date": None,
            "is_current_day": False,
            "data": daily,
            "today_candle": None,
            "error": "Cannot build today's candle",
        }

    # --------------------------------------------------------
    # 5. REMOVE EXISTING TODAY ROW
    # --------------------------------------------------------

    daily["DateOnly"] = (
        pd.to_datetime(
            daily["Date"]
        ).dt.date
    )

    daily = daily[
        daily["DateOnly"] != today
    ].copy()

    daily = daily.drop(
        columns=["DateOnly"]
    )

    # --------------------------------------------------------
    # 6. APPEND CURRENT DAILY CANDLE
    # --------------------------------------------------------

    today_df = pd.DataFrame(
        [today_candle]
    )

    daily = pd.concat(
        [
            daily,
            today_df
        ],
        ignore_index=True
    )

    daily = daily.sort_values(
        "Date"
    )

    daily = daily.drop_duplicates(
        subset=["Date"],
        keep="last"
    )

    daily = daily.reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # 7. FINAL VALIDATION
    # --------------------------------------------------------

    latest_date = (
        pd.to_datetime(
            daily["Date"]
        ).max().date()
    )

    if latest_date != today:
        return {
            "ok": False,
            "symbol": symbol,
            "date": latest_date,
            "is_current_day": False,
            "data": daily,
            "today_candle": today_candle,
            "error": (
                f"FINAL VALIDATION FAILED: "
                f"latest={latest_date}, "
                f"today={today}"
            ),
        }

    print(
        f"   TODAY       : {today}"
    )

    print(
        f"   5M bars     : {len(today_5m)}"
    )

    print(
        f"   Open        : {today_candle['Open']:.4f}"
    )

    print(
        f"   High        : {today_candle['High']:.4f}"
    )

    print(
        f"   Low         : {today_candle['Low']:.4f}"
    )

    print(
        f"   Close       : {today_candle['Close']:.4f}"
    )

    print(
        f"   Volume      : {today_candle['Volume']:.0f}"
    )

    print(
        f"   Latest Daily: {latest_date}"
    )

    print(
        "   STATUS      : CURRENT DAILY CANDLE = PASS"
    )

    return {
        "ok": True,
        "symbol": symbol,
        "date": latest_date,
        "is_current_day": True,
        "data": daily,
        "today_candle": today_candle,
        "error": None,
    }


# ------------------------------------------------------------
# SIMPLE CLI TEST
# ------------------------------------------------------------

if __name__ == "__main__":

    SYMBOL = "CII"

    result = get_live_daily(
        SYMBOL
    )

    print()
    print("=" * 70)
    print("LIVE DAILY DATA TEST")
    print("=" * 70)

    print(
        f"Symbol          : {result['symbol']}"
    )

    print(
        f"OK              : {result['ok']}"
    )

    print(
        f"Latest date     : {result['date']}"
    )

    print(
        f"Current candle  : "
        f"{result['is_current_day']}"
    )

    if result["error"]:
        print(
            f"ERROR           : "
            f"{result['error']}"
        )

    if result["today_candle"]:
        print()
        print(
            "TODAY CANDLE:"
        )

        for key, value in result[
            "today_candle"
        ].items():
            print(
                f"  {key:<10}: {value}"
            )

    print("=" * 70) 
