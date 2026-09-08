import os
import sys
import time
import pandas as pd


# ============================================================
# ST5 LIVE — CORE26 5M DATA UPDATER
# ============================================================
#
# Mục đích:
# - Cập nhật dữ liệu 5M cho CORE26 trong phiên
# - Không tạo downloader riêng cho từng strategy
# - Giữ dữ liệu lịch sử cục bộ để indicator có đủ warm-up
# - Mỗi lần chạy chỉ MERGE dữ liệu mới vào file hiện tại
#
# Không xử lý BUY/SELL.
# Không gửi Telegram.
# Không xử lý T+2.5.
#
# ============================================================


# ============================================================
# ROOT
# ============================================================

ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

sys.path.insert(
    0,
    ROOT_DIR
)


# ============================================================
# IMPORT
# ============================================================

from config import CORE26
from data import get_5m_data


# ============================================================
# CONFIG
# ============================================================

OUTPUT_DIR = os.path.join(
    ROOT_DIR,
    "data",
    "INTRADAY_5M"
)

# Giữ 30 ngày dữ liệu local.
# Đây là lịch sử đủ rộng cho indicator 5M + 15M.
FETCH_DAYS = 5

# Nghỉ giữa các mã để tránh gọi API quá dồn.
REQUEST_DELAY = 2


# ============================================================
# PREPARE DATA
# ============================================================

def prepare_5m_dataframe(df):
    """
    Chuẩn hóa dữ liệu 5M trước khi merge.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Thiếu cột: {missing}"
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
        subset=["Date"],
        keep="last"
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# MERGE LOCAL + NEW DATA
# ============================================================

def merge_5m_data(
    local_df,
    new_df
):
    """
    Merge dữ liệu cũ + dữ liệu mới.

    Nếu cùng timestamp:
    - dữ liệu mới giữ quyền ưu tiên.
    """

    frames = []

    if (
        local_df is not None
        and not local_df.empty
    ):
        frames.append(
            local_df
        )

    if (
        new_df is not None
        and not new_df.empty
    ):
        frames.append(
            new_df
        )

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(
        frames,
        ignore_index=True
    )

    combined = prepare_5m_dataframe(
        combined
    )

    return combined


# ============================================================
# LOAD LOCAL
# ============================================================

def load_local_file(
    output_file
):

    if not os.path.exists(
        output_file
    ):
        return pd.DataFrame()

    try:

        df = pd.read_csv(
            output_file
        )

        return prepare_5m_dataframe(
            df
        )

    except Exception as e:

        print(
            f"⚠️ Không đọc được file local: "
            f"{output_file}"
        )

        print(
            f"   {type(e).__name__}: {e}"
        )

        return pd.DataFrame()


# ============================================================
# UPDATE ONE TICKER
# ============================================================

def update_ticker(
    ticker
):

    print()
    print("-" * 70)
    print(
        f"[UPDATE] {ticker}"
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{ticker}_5m.csv"
    )

    # --------------------------------------------------------
    # LOCAL
    # --------------------------------------------------------

    local_df = load_local_file(
        output_file
    )

    old_rows = len(local_df)

    old_last = (
        local_df["Date"].max()
        if not local_df.empty
        else None
    )

    # --------------------------------------------------------
    # DOWNLOAD RECENT WINDOW
    # --------------------------------------------------------

    try:

        new_df = get_5m_data(
            ticker,
            days=FETCH_DAYS
        )

    except Exception as e:

        print(
            f"❌ {ticker}: download lỗi"
        )

        print(
            f"   {type(e).__name__}: {e}"
        )

        return False

    if new_df is None or new_df.empty:

        print(
            f"⚠️ {ticker}: "
            "API không trả dữ liệu"
        )

        return False

    new_df = prepare_5m_dataframe(
        new_df
    )

    if new_df.empty:

        print(
            f"⚠️ {ticker}: "
            "dữ liệu sau chuẩn hóa rỗng"
        )

        return False

    new_last = new_df["Date"].max()

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    merged = merge_5m_data(
        local_df,
        new_df
    )

    if merged.empty:

        print(
            f"❌ {ticker}: "
            "merge tạo dữ liệu rỗng"
        )

        return False

    # --------------------------------------------------------
    # SAVE ATOMICALLY
    # --------------------------------------------------------

    temp_file = (
        output_file
        + ".tmp"
    )

    merged.to_csv(
        temp_file,
        index=False
    )

    os.replace(
        temp_file,
        output_file
    )

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    new_rows = len(merged)

    added_rows = max(
        0,
        new_rows - old_rows
    )

    final_last = merged["Date"].max()

    file_size = os.path.getsize(
        output_file
    )

    print(
        f"   Local rows : {old_rows:,}"
    )

    print(
        f"   API rows   : {len(new_df):,}"
    )

    print(
        f"   Added rows : {added_rows:,}"
    )

    print(
        f"   Total rows : {new_rows:,}"
    )

    if old_last is not None:

        print(
            f"   Old last   : {old_last}"
        )

    print(
        f"   API last   : {new_last}"
    )

    print(
        f"   Final last : {final_last}"
    )

    print(
        f"   File size  : {file_size:,} bytes"
    )

    print(
        f"✅ {ticker}: UPDATE OK"
    )

    return True


# ============================================================
# UPDATE CORE26
# ============================================================

def update_core26():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    print()
    print("=" * 70)
    print("ST5 LIVE — CORE26 5M DATA UPDATE")
    print("=" * 70)

    print(
        f"CORE26       : {len(CORE26)} ticker"
    )

    print(
        f"Fetch window : {FETCH_DAYS} days"
    )

    print(
        f"Output       : {OUTPUT_DIR}"
    )

    success = []
    failed = []

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    for i, ticker in enumerate(
        CORE26,
        1
    ):

        print()
        print(
            f"Progress: "
            f"{i}/{len(CORE26)}"
        )

        try:

            ok = update_ticker(
                ticker
            )

            if ok:

                success.append(
                    ticker
                )

            else:

                failed.append(
                    ticker
                )

        except Exception as e:

            print(
                f"❌ {ticker}: "
                f"{type(e).__name__}: {e}"
            )

            failed.append(
                ticker
            )

        # Không delay sau ticker cuối.
        if (
            i < len(CORE26)
        ):

            time.sleep(
                REQUEST_DELAY
            )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("CORE26 UPDATE RESULT")
    print("=" * 70)

    print(
        f"Success : "
        f"{len(success)}/{len(CORE26)}"
    )

    print(
        f"Failed  : "
        f"{len(failed)}/{len(CORE26)}"
    )

    print()
    print(
        "SUCCESS:"
    )

    print(
        success
    )

    print()
    print(
        "FAILED:"
    )

    print(
        failed
    )

    print()
    print(
        f"DATA ROOT: {OUTPUT_DIR}"
    )

    print("=" * 70)

    # Nếu có mã thất bại thì báo lỗi cho caller.
    return len(failed) == 0


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    ok = update_core26()

    if not ok:

        sys.exit(1)
