import os
import sys
import time

# Tự động trỏ lên thư mục gốc để tìm file config.py và data.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
        df = get_5m_data(ticker, days=30)

        if df is None or df.empty:
            print(f"❌ {ticker}: KHÔNG CÓ DỮ LIỆU")
            failed.append(ticker)
            continue

        date_col = None
        for col in ['Date', 'date', 'Timestamp', 'timestamp', 'Datetime', 'datetime']:
            if col in df.columns:
                date_col = col
                break

        if date_col:
            min_date = df[date_col].min()
            max_date = df[date_col].max()
            index_flag = False
        else:
            min_date = df.index.min()
            max_date = df.index.max()
            index_flag = True

        output_file = os.path.join(OUTPUT_DIR, f"{ticker}_5m.csv")
        df.to_csv(output_file, index=index_flag)

        print(f"✅ {ticker}")
        print(f"   Số nến : {len(df):,}")
        print(f"   Từ     : {min_date}")
        print(f"   Đến    : {max_date}")
        print(f"   File   : {output_file}")

        success.append(ticker)
        time.sleep(4)

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
 
