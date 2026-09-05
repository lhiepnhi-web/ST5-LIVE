import pandas as pd
from vnstock import Quote


def get_5m_data(ticker, days=30):

    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=days)

    quote = Quote(
        symbol=ticker,
        source="KBS"
    )

    df = quote.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="5m"
    )

    if df is None or df.empty:
        return pd.DataFrame()

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

    df = df.rename(columns=rename)

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
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

    df = df.sort_values("Date")

    df = df.drop_duplicates(
        subset=["Date"]
    )

    return df.reset_index(drop=True) 
