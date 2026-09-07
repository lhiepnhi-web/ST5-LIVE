import os
import sys
import time


# ============================================================
# ST5 — DOWNLOAD CORE26 5M
# ============================================================

# Thư mục gốc ST5-LIVE
ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

# Cho phép import config.py và data.py
sys.path.insert(
    0,
    ROOT_DIR
)

from config import CORE26
from data import get_5m_data


# ============================================================
# OUTPUT
# ============================================================

OUTPUT_DIR = os.path.join(
    ROOT_DIR,
    "data",
    "INTRADAY_5M"
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# ============================================================
# START
# ============================================================

print("=" * 70)
print("ST5 — DOWNLOAD CORE26 5M")
print("=" * 70)

print(
    f"Số mã      : {len(CORE26)}"
)

print(
    f"Thư mục gốc: {ROOT_DIR}"
)

print(
    f"Thư mục data: {OUTPUT_DIR}"
)


# ============================================================
# DOWNLOAD
# ============================================================

success = []
failed = []


for i, ticker in enumerate(
    CORE26,
    1
):

    print()
    print("-" * 70)
    print(
        f"[{i}/{len(CORE26)}] {ticker}"
    )

    try:

        df = get_5m_data(
            ticker,
            days=30
        )

        if df is None or df.empty:

            print(
                f"❌ {ticker}: "
                "KHÔNG CÓ DỮ LIỆU"
            )

            failed.append(
                ticker
            )

            continue


        # ----------------------------------------------------
        # FIND DATE COLUMN
        # ----------------------------------------------------

        date_col = None

        for col in [
            "Date",
            "date",
            "Timestamp",
            "timestamp",
            "Datetime",
            "datetime",
        ]:

            if col in df.columns:

                date_col = col

                break


        # ----------------------------------------------------
        # DATE RANGE
        # ----------------------------------------------------

        if date_col:

            min_date = df[
                date_col
            ].min()

            max_date = df[
                date_col
            ].max()

            index_flag = False

        else:

            min_date = df.index.min()

            max_date = df.index.max()

            index_flag = True


        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        output_file = os.path.join(
            OUTPUT_DIR,
            f"{ticker}_5m.csv"
        )

        df.to_csv(
            output_file,
            index=index_flag
        )


        # ----------------------------------------------------
        # VERIFY FILE
        # ----------------------------------------------------

        if not os.path.exists(
            output_file
        ):

            print(
                f"❌ {ticker}: "
                "ghi file thất bại"
            )

            failed.append(
                ticker
            )

            continue


        file_size = os.path.getsize(
            output_file
        )


        if file_size <= 0:

            print(
                f"❌ {ticker}: "
                "file rỗng"
            )

            failed.append(
                ticker
            )

            continue


        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        print(
            f"✅ {ticker}"
        )

        print(
            f"   Số nến : {len(df):,}"
        )

        print(
            f"   Từ     : {min_date}"
        )

        print(
            f"   Đến    : {max_date}"
        )

        print(
            f"   File   : {output_file}"
        )

        print(
            f"   Size   : {file_size:,} bytes"
        )

        success.append(
            ticker
        )


        # Giữ nguyên delay cũ
        time.sleep(4)


    except Exception as e:

        print(
            f"❌ {ticker}: LỖI"
        )

        print(
            f"   {type(e).__name__}: {e}"
        )

        failed.append(
            ticker
        )


# ============================================================
# RESULT
# ============================================================

print()
print("=" * 70)
print("KẾT QUẢ")
print("=" * 70)

print(
    f"Thành công : "
    f"{len(success)}/{len(CORE26)}"
)

print(
    f"Thất bại   : "
    f"{len(failed)}/{len(CORE26)}"
)

print()
print("SUCCESS:")
print(success)

print()
print("FAILED:")
print(failed)

print()
print(
    f"DATA ROOT: {OUTPUT_DIR}"
)

print("=" * 70)
