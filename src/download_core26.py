import os
import time
from config import CORE26
from data import get_5m_data


OUTPUT_DIR = "data/INTRADAY_5M"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("ST5 — DOWNLOAD CORE26 5M")
print("=" * 70)

print(f"Số mã: {len(CORE26)}")
print(f"Thư mục: {OUTPUT_DIR}")

success = []
failed = []

for i, ticker in enumerate(CORE26, 1):

    print()
    print("-" * 70)
    print(f"[{i}/{len(CORE26)}] {ticker}")

    try:
        df = get_5m_data(
            ticker,
            days=30
        )

        if df.empty:
            print(f"❌ {ticker}: KHÔNG CÓ DỮ LIỆU")
            failed.append(ticker)
            continue

        output_file = os.path.join(
            OUTPUT_DIR,
            f"{ticker}_5m.csv"
        )

        df.to_csv(
            output_file,
            index=False
        )

        print(f"✅ {ticker}")
        print(f"   Số nến : {len(df):,}")
        print(f"   Từ     : {df['Date'].min()}")
        print(f"   Đến    : {df['Date'].max()}")
        print(f"   File   : {output_file}")

        success.append(ticker)

        time.sleep(1)

    except Exception as e:

        print(f"❌ {ticker}: LỖI")
        print(f"   {type(e).__name__}: {e}")

        failed.append(ticker)

print()
print("=" * 70)
print("KẾT QUẢ")
print("=" * 70)

print(f"Thành công : {len(success)}/{len(CORE26)}")
print(f"Thất bại   : {len(failed)}/{len(CORE26)}")

print()
print("SUCCESS:")
print(success)

print()
print("FAILED:")
print(failed)

print("=" * 70)import os
import time
from config import CORE26
from data import get_5m_data


OUTPUT_DIR = "data/INTRADAY_5M"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("ST5 — DOWNLOAD CORE26 5M")
print("=" * 70)

print(f"Số mã: {len(CORE26)}")
print(f"Thư mục: {OUTPUT_DIR}")

success = []
failed = []

for i, ticker in enumerate(CORE26, 1):

    print()
    print("-" * 70)
    print(f"[{i}/{len(CORE26)}] {ticker}")

    try:
        df = get_5m_data(
            ticker,
            days=30
        )

        if df.empty:
            print(f"❌ {ticker}: KHÔNG CÓ DỮ LIỆU")
            failed.append(ticker)
            continue

        output_file = os.path.join(
            OUTPUT_DIR,
            f"{ticker}_5m.csv"
        )

        df.to_csv(
            output_file,
            index=False
        )

        print(f"✅ {ticker}")
        print(f"   Số nến : {len(df):,}")
        print(f"   Từ     : {df['Date'].min()}")
        print(f"   Đến    : {df['Date'].max()}")
        print(f"   File   : {output_file}")

        success.append(ticker)

        time.sleep(1)

    except Exception as e:

        print(f"❌ {ticker}: LỖI")
        print(f"   {type(e).__name__}: {e}")

        failed.append(ticker)

print()
print("=" * 70)
print("KẾT QUẢ")
print("=" * 70)

print(f"Thành công : {len(success)}/{len(CORE26)}")
print(f"Thất bại   : {len(failed)}/{len(CORE26)}")

print()
print("SUCCESS:")
print(success)

print()
print("FAILED:")
print(failed)

print("=" * 70)  
