# ============================================================
# VRE SURVIVAL V1.8 — LIVE ENGINE
#
# V1.8 FROZEN
#
# ENTRY:
#   ADX14 > 40 AND MACD_HIST_SLOPE > 0
#
# EXIT:
#   MACD_HIST <= 0
#   OR ROC10 <= 2
#   OR ADX14 <= 30
#
# LIVE:
#   Daily timeframe
#   7 CORE tickers
#   Persistent state
#   Signal de-duplication
#   Telegram
#
# NO:
#   TP / SL
#   RSI
#   Volume
#   VNINDEX filter
#   MA20
#   Auto Order
#   MSR/CII modification
# ============================================================

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from vnstock import Quote


# ============================================================
# CONFIG
# ============================================================

TICKERS = [
    "VIX",
    "ABB",
    "AAS",
    "SHS",
    "NKG",
    "HPG",
    "DXG",
]

SOURCE = "KBS"

DATA_START = "2010-01-01"

ENTRY_ADX_MIN = 40.0
EXIT_ADX_MIN = 30.0
ROC10_MIN = 2.0

ROOT_DIR = Path(__file__).resolve().parent.parent

STATE_DIR = ROOT_DIR / "data"
STATE_FILE = STATE_DIR / "vre_survival_state.json"


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
)


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] Secrets not available -> skip")
        return False

    try:

        url = (
            "https://api.telegram.org/bot"
            + TELEGRAM_BOT_TOKEN
            + "/sendMessage"
        )

        payload = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        }).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=payload,
            method="POST"
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            body = response.read().decode("utf-8")

        result = json.loads(body)

        if result.get("ok"):
            print("[TELEGRAM] SENT")
            return True

        print(
            f"[TELEGRAM] FAILED: {result}"
        )
        return False

    except Exception as e:

        print(
            f"[TELEGRAM] ERROR: {e}"
        )

        return False


# ============================================================
# DATA NORMALIZATION
# ============================================================

def normalize_columns(df):

    df = df.copy()

    rename_map = {}

    for c in df.columns:

        lc = str(c).lower().strip()

        if lc in ["time", "date", "datetime"]:
            rename_map[c] = "date"

        elif lc == "open":
            rename_map[c] = "open"

        elif lc == "high":
            rename_map[c] = "high"

        elif lc == "low":
            rename_map[c] = "low"

        elif lc in ["close", "closing_price"]:
            rename_map[c] = "close"

        elif lc in ["volume", "vol"]:
            rename_map[c] = "volume"

    df = df.rename(
        columns=rename_map
    )

    required = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    for c in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:

        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    )

    df = df.sort_values(
        "date"
    )

    df = df.drop_duplicates(
        "date"
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# ST5 INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # ROC10
    # --------------------------------------------------------

    df["ROC10"] = (
        df["close"]
        / df["close"].shift(10)
        - 1
    ) * 100.0

    # --------------------------------------------------------
    # MACD 12 / 26 / 9
    # --------------------------------------------------------

    ema12 = df["close"].ewm(
        span=12,
        adjust=False,
        min_periods=12
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False,
        min_periods=26
    ).mean()

    df["MACD"] = (
        ema12 - ema26
    )

    df["MACD_SIGNAL"] = df[
        "MACD"
    ].ewm(
        span=9,
        adjust=False,
        min_periods=9
    ).mean()

    df["MACD_HIST"] = (
        df["MACD"]
        - df["MACD_SIGNAL"]
    )

    # Current - previous
    df["MACD_HIST_SLOPE"] = (
        df["MACD_HIST"]
        - df["MACD_HIST"].shift(1)
    )

    # --------------------------------------------------------
    # ADX14 — EXACT ST5 EWM
    # --------------------------------------------------------

    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - prev_close
    ).abs()

    tr3 = (
        low - prev_close
    ).abs()

    df["TR"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = high.diff()

    down_move = -low.diff()

    plus_dm = np.where(
        (up_move > down_move)
        & (up_move > 0),
        up_move,
        0.0
    )

    minus_dm = np.where(
        (down_move > up_move)
        & (down_move > 0),
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

    atr = df["TR"].ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    plus_di = (
        100.0
        * plus_dm.ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14
        ).mean()
        / atr
    )

    minus_di = (
        100.0
        * minus_dm.ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14
        ).mean()
        / atr
    )

    denominator = (
        plus_di + minus_di
    )

    dx = (
        100.0
        * (plus_di - minus_di).abs()
        / denominator.replace(
            0,
            np.nan
        )
    )

    df["ADX14"] = dx.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    return df


# ============================================================
# V1.8 DECISION
# ============================================================

def evaluate_v18(row):

    adx = float(row["ADX14"])
    hist = float(row["MACD_HIST"])
    slope = float(row["MACD_HIST_SLOPE"])
    roc10 = float(row["ROC10"])

    # EXIT
    if (
        hist <= 0
        or roc10 <= ROC10_MIN
        or adx <= EXIT_ADX_MIN
    ):
        return "EXIT"

    # ENTRY
    if (
        adx > ENTRY_ADX_MIN
        and slope > 0
    ):
        return "BUY"

    return "HOLD"


# ============================================================
# STATE
# ============================================================

def default_state():

    return {
        "version": "V1.8",
        "updated_at": None,
        "tickers": {}
    }


def load_state():

    if not STATE_FILE.exists():

        print(
            "[STATE] No existing state -> create new"
        )

        return default_state()

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

            raise ValueError(
                "Invalid state format"
            )

        if "tickers" not in state:
            state["tickers"] = {}

        return state

    except Exception as e:

        print(
            f"[STATE] Load error: {e}"
        )

        return default_state()


def save_state(state):

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    tmp_file = STATE_FILE.with_suffix(
        ".tmp"
    )

    with open(
        tmp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )

    tmp_file.replace(
        STATE_FILE
    )

    print(
        f"[STATE] Saved: {STATE_FILE}"
    )


# ============================================================
# DAILY DATA
# ============================================================

def download_daily(ticker):

    print()
    print(
        f"[{ticker}] Download Daily..."
    )

    quote = Quote(
        symbol=ticker,
        source=SOURCE
    )

    df = quote.history(
        start=DATA_START,
        end=datetime.now().strftime(
            "%Y-%m-%d"
        ),
        interval="1D"
    )

    if df is None or len(df) == 0:

        raise ValueError(
            f"{ticker}: empty data"
        )

    df = normalize_columns(df)

    df = calculate_indicators(df)

    return df


# ============================================================
# PROCESS TICKER
# ============================================================

def process_ticker(
    ticker,
    state
):

    df = download_daily(
        ticker
    )

    valid = df.dropna(
        subset=[
            "ROC10",
            "MACD_HIST",
            "MACD_HIST_SLOPE",
            "ADX14",
        ]
    )

    if len(valid) == 0:

        raise ValueError(
            f"{ticker}: no valid indicator rows"
        )

    row = valid.iloc[-1]

    decision = evaluate_v18(
        row
    )

    last_date = row["date"]

    if hasattr(
        last_date,
        "isoformat"
    ):

        last_date_str = (
            last_date.isoformat()
        )

    else:

        last_date_str = str(
            last_date
        )

    old = state[
        "tickers"
    ].get(
        ticker,
        {}
    )

    old_position = bool(
        old.get(
            "position",
            False
        )
    )

    old_decision = old.get(
        "decision"
    )

    # --------------------------------------------------------
    # REAL SIGNAL LOGIC
    #
    # BUY only when:
    #   current BUY
    #   AND currently not holding
    #
    # EXIT only when:
    #   current EXIT
    #   AND currently holding
    #
    # HOLD = no signal
    # --------------------------------------------------------

    signal = None

    if (
        decision == "BUY"
        and not old_position
    ):

        signal = "BUY"

    elif (
        decision == "EXIT"
        and old_position
    ):

        signal = "SELL"

    # --------------------------------------------------------
    # Update position state
    # --------------------------------------------------------

    new_position = old_position

    if signal == "BUY":
        new_position = True

    elif signal == "SELL":
        new_position = False

    # --------------------------------------------------------
    # Save ticker state
    # --------------------------------------------------------

    ticker_state = {

        "last_date":
            last_date_str,

        "close":
            float(row["close"]),

        "adx14":
            float(row["ADX14"]),

        "macd_hist":
            float(row["MACD_HIST"]),

        "macd_hist_slope":
            float(
                row["MACD_HIST_SLOPE"]
            ),

        "roc10":
            float(row["ROC10"]),

        "decision":
            decision,

        "previous_decision":
            old_decision,

        "position":
            bool(new_position),

        "signal":
            signal,

        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    state[
        "tickers"
    ][ticker] = ticker_state

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    print()
    print("-" * 78)
    print(ticker)

    print(
        f"Last date : {last_date_str}"
    )

    print(
        f"Close     : {row['close']:.4f}"
    )

    print(
        f"ADX14     : {row['ADX14']:.4f}"
    )

    print(
        f"MACD_HIST : {row['MACD_HIST']:.6f}"
    )

    print(
        f"HIST_SLOPE: {row['MACD_HIST_SLOPE']:.6f}"
    )

    print(
        f"ROC10     : {row['ROC10']:.4f}"
    )

    print(
        f"PREVIOUS  : {old_decision}"
    )

    print(
        f"POSITION  : {old_position}"
    )

    print(
        f"DECISION  : {decision}"
    )

    print(
        f"SIGNAL    : {signal}"
    )

    print(
        f"NEW POS   : {new_position}"
    )

    return ticker_state


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def build_signal_message(
    ticker,
    result
):

    signal = result["signal"]

    if signal == "BUY":

        title = "🟢 VRE SURVIVAL — BUY"

    elif signal == "SELL":

        title = "🔴 VRE SURVIVAL — SELL"

    else:

        return None

    return (
        f"{title}\n"
        f"\n"
        f"Mã: {ticker}\n"
        f"Ngày: {result['last_date']}\n"
        f"Giá: {result['close']:.4f}\n"
        f"\n"
        f"ADX14: {result['adx14']:.4f}\n"
        f"MACD Hist: {result['macd_hist']:.6f}\n"
        f"Hist Slope: {result['macd_hist_slope']:.6f}\n"
        f"ROC10: {result['roc10']:.4f}\n"
        f"\n"
        f"VRE Survival V1.8\n"
        f"Daily Signal"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 78)
    print(
        "VRE SURVIVAL V1.8 — LIVE ENGINE"
    )
    print("=" * 78)

    print(
        f"State file : {STATE_FILE}"
    )

    print(
        f"Tickers    : {', '.join(TICKERS)}"
    )

    print(
        "Timeframe  : DAILY"
    )

    print(
        "Source     : KBS"
    )

    print()

    state = load_state()

    state["version"] = "V1.8"

    success = 0
    failed = 0

    results = []

    # --------------------------------------------------------
    # PROCESS ALL TICKERS
    # --------------------------------------------------------

    for ticker in TICKERS:

        try:

            result = process_ticker(
                ticker,
                state
            )

            results.append(
                (ticker, result)
            )

            success += 1

        except Exception as e:

            failed += 1

            print()
            print(
                f"[ERROR] {ticker}: {e}"
            )

    # --------------------------------------------------------
    # SEND TELEGRAM
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("TELEGRAM SIGNALS")
    print("=" * 78)

    telegram_count = 0

    for ticker, result in results:

        message = build_signal_message(
            ticker,
            result
        )

        if message is None:

            print(
                f"{ticker}: NO SIGNAL"
            )

            continue

        print(
            f"{ticker}: {result['signal']}"
        )

        sent = send_telegram(
            message
        )

        if sent:
            telegram_count += 1

    # --------------------------------------------------------
    # UPDATE GLOBAL STATE
    # --------------------------------------------------------

    state["updated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    save_state(
        state
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print(
        "VRE SURVIVAL V1.8 — SUMMARY"
    )
    print("=" * 78)

    print(
        f"{'Ticker':<8}"
        f"{'Decision':<10}"
        f"{'Position':<10}"
        f"{'Signal':<10}"
        f"{'Status'}"
    )

    for ticker, result in results:

        signal_text = (
            result["signal"]
            if result["signal"]
            else "-"
        )

        print(
            f"{ticker:<8}"
            f"{result['decision']:<10}"
            f"{str(result['position']):<10}"
            f"{signal_text:<10}"
            f"OK"
        )

    print()
    print(
        f"Success          : {success}"
    )

    print(
        f"Failed           : {failed}"
    )

    print(
        f"Telegram signals : {telegram_count}"
    )

    print()
    print(
        f"State file: {STATE_FILE}"
    )

    print()
    print("=" * 78)
    print(
        "VRE SURVIVAL V1.8 FINISHED"
    )
    print("=" * 78)


if __name__ == "__main__":
    main()
