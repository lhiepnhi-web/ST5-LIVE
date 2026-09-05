from data import get_5m_data

print("=" * 60)
print("ST5 - TEST 5M DATA")
print("=" * 60)

ticker = "SSI"

print(f"Đang lấy dữ liệu 5M: {ticker}")

try:
    df = get_5m_data(ticker, days=30)

    if df.empty:
        print("KHONG CO DU LIEU")
    else:
        print("CO DU LIEU")
        print(f"So nen: {len(df):,}")
        print(f"Tu: {df['Date'].min()}")
        print(f"Den: {df['Date'].max()}")

        print("\n5 dong cuoi:")
        print(df.tail().to_string(index=False))

except Exception as e:
    print("LOI:")
    print(type(e).__name__)
    print(str(e)) 
