 from data import get_5m_data


print("=" * 60)
print("ST5 — TEST 5M DATA")
print("=" * 60)

ticker = "SSI"

print(f"\nĐang lấy dữ liệu 5M: {ticker}")

try:
    df = get_5m_data(ticker, days=30)
    if df.empty:
        print("\n❌ KHÔNG CÓ DỮ LIỆU")
    else:
        print("\n✅ CÓ DỮ LIỆU")
        print(f"\nSố nến: {len(df):,}")
        print(f"Từ: {df['Date'].min()}")
        print(f"Đến: {df['Date'].max()}")

        print("\n5 dòng đầu:")
        print(df.head().to_string(index=False))

        print("\n5 dòng cuối:")
        print(df.tail().to_string(index=False))

except Exception as e:
    print("\n❌ LỖI:")
    print(type(e).__name__)
    print(str(e))
