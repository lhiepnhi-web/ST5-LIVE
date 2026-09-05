
import os
import pandas as pd

from config import (
    CORE26,
    MORNING_START,
    MORNING_END,
    AFTERNOON_START,
    AFTERNOON_END,
)

from indicators import add_v14_indicators, v14_signal


INPUT_DIR = "data/INTRADAY_5M"
OUTPUT_DIR = "data/SIGNALS"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def in_trading_session(timestamp):
    t = timestamp.time()

    morning = (
        pd.Timestamp(MORNING_START).time()
        <= t
        <= pd.Timestamp(MORNING_END).time()
    )

    afternoon = (
        pd.Timestamp(AFTERNOON_START).time()
        <= t
        <= pd.Timestamp(AFTERNOON_END).time()
    )

    return morning or afternoon


def build_15m(df5):
    df = df5.copy()

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    df = df.drop_duplicates("Date")
    df = df.set_index("Date")

    df15 = df.resample("15min").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })

    df15 = df15.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    return df15.reset_index()


def prepare_15m_confirmation(df15):
    """
    Tính indicator trên nến 15M đã hoàn tất.

    QUAN TRỌNG:
    Confirmation được shift(1), tức 5M không được
    sử dụng nến 15M đang hình thành.
    """

    df15 = add_v14_indicators(df15)

    df15["Confirm"] = v14_signal(df15)

    df15["Confirm"] = df15["Confirm"].shift(1)

    return df15


def process_ticker(ticker):

    input_file = os.path.join(
        INPUT_DIR,
        f"{ticker}_5m.csv"
    )

    if not os.path.exists(input_file):
        print(f"❌ {ticker}: không có file 5M")
        return None

    df5 = pd.read_csv(input_file)

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing = [
        c for c in required
        if c not in df5.columns
    ]

    if missing:
        print(
            f"❌ {ticker}: thiếu cột {missing}"
        )
        return None

    df5["Date"] = pd.to_datetime(
        df5["Date"],
        errors="coerce"
    )

    df5 = df5.dropna(
        subset=required
    )

    df5 = df5.sort_values("Date")
    df5 = df5.drop_duplicates("Date")

    if len(df5) < 100:
        print(
            f"❌ {ticker}: quá ít nến 5M"
        )
        return None

    # --------------------------------------------------------
    # 1. TẠO 15M
    # --------------------------------------------------------

    df15 = build_15m(df5)

    # --------------------------------------------------------
    # 2. TÍNH V1.4 TRÊN 15M
    # --------------------------------------------------------

    df15 = prepare_15m_confirmation(
        df15
    )

    confirm = df15[
        ["Date", "Confirm"]
    ].copy()

    confirm["Confirm"] = (
        confirm["Confirm"]
        .fillna(False)
        .astype(bool)
    )

    # --------------------------------------------------------
    # 3. TÍNH V1.4 TRÊN 5M
    # --------------------------------------------------------

    df5 = add_v14_indicators(df5)

    df5["Trigger"] = v14_signal(df5)

    # --------------------------------------------------------
    # 4. GHÉP CONFIRMATION 15M
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 5. TÍN HIỆU
    # --------------------------------------------------------

    df5["BUY"] = (
        df5["Trigger"]
        & df5["Confirm"]
    )

    # SELL khi điều kiện BUY không còn đúng
    df5["SELL"] = ~(
        df5["Trigger"]
        & df5["Confirm"]
    )

    # --------------------------------------------------------
    # 6. CHỈ LẤY GIỜ GIAO DỊCH
    # --------------------------------------------------------

    df5["InSession"] = (
        df5["Date"]
        .apply(in_trading_session)
    )

    df5["BUY"] = (
        df5["BUY"]
        & df5["InSession"]
    )

    df5["SELL"] = (
        df5["SELL"]
        & df5["InSession"]
    )

    # --------------------------------------------------------
    # 7. GIỮ CÁC CỘT QUAN TRỌNG
    # --------------------------------------------------------

    result = df5[
        [
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "VolumeRatio",
            "ROC10",
            "MACD_Hist",
            "ADX14",
            "Trigger",
            "Confirm",
            "BUY",
            "SELL",
        ]
    ].copy()

    # --------------------------------------------------------
    # 8. CHỈ LƯU NHỮNG DÒNG CÓ TÍN HIỆU
    # --------------------------------------------------------

    signals = result[
        result["BUY"] | result["SELL"]
    ].copy()

    signals.insert(
        0,
        "Ticker",
        ticker
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{ticker}_signals.csv"
    )

    signals.to_csv(
        output_file,
        index=False
    )

    print(
        f"✅ {ticker}: "
        f"{len(signals)} tín hiệu"
    )

    return signals


def main():

    print("=" * 70)
    print("ST5 LIVE")
    print("CORE26 — 5M TRIGGER + 15M CONFIRMATION")
    print("V1.4 FROZEN")
    print("=" * 70)

    all_signals = []

    for ticker in CORE26:

        try:

            result = process_ticker(
                ticker
            )

            if result is not None and not result.empty:
                all_signals.append(
                    result
                )

        except Exception as e:

            print(
                f"❌ {ticker}: "
                f"{type(e).__name__}: {e}"
            )

    # --------------------------------------------------------
    # TỔNG HỢP CORE26
    # --------------------------------------------------------

    if all_signals:

        combined = pd.concat(
            all_signals,
            ignore_index=True
        )

        combined = combined.sort_values(
            ["Date", "Ticker"]
        )

    else:

        combined = pd.DataFrame(
            columns=[
                "Ticker",
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "VolumeRatio",
                "ROC10",
                "MACD_Hist",
                "ADX14",
                "Trigger",
                "Confirm",
                "BUY",
                "SELL",
            ]
        )

    output_file = os.path.join(
        OUTPUT_DIR,
        "CORE26_SIGNALS.csv"
    )

    combined.to_csv(
        output_file,
        index=False
    )

    print()
    print("=" * 70)
    print("KẾT QUẢ")
    print("=" * 70)

    print(
        f"Tổng tín hiệu: {len(combined)}"
    )

    if not combined.empty:

        print(
            f"BUY : "
            f"{int(combined['BUY'].sum())}"
        )

        print(
            f"SELL: "
            f"{int(combined['SELL'].sum())}"
        )

        print()
        print(
            combined[
                [
                    "Ticker",
                    "Date",
                    "Close",
                    "BUY",
                    "SELL",
                ]
            ]
            .tail(20)
            .to_string(index=False)
        )

    print()
    print(
        f"File: {output_file}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
