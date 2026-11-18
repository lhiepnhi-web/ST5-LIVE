# ============================================================
# CONFIG MASTER - STEP 2 REFINED SYSTEM
# ============================================================

RULES = {
    "CORE-30": dict(
        tickers=["ABB","HCM","NKG","IDJ","NVL","SSI","CTS","CTR","FRT","NHA"],
        volr=1.2, roc=3.0, macd=0.0, adx=20.0, ma200=False, ma50=True, mh=5,
    ),
    "CORE-SCAN-DCM": dict(
        tickers=["CTS","DGW","HSL","CII","CEO","MCH","DPM","VPB","FRT","BSR","VDS"],
        volr=1.5, roc=4.0, macd=0.0, adx=19.0, ma200=True, ma50=True, mh=3,
    ),
    "CORE-SCAN-GVR": dict(
        tickers=["FRT","CEO","DGW","VPB","VIX","LPB","VCG","DPR","GVR","BFC","OIL"],
        volr=1.2, roc=4.5, macd=0.0, adx=27.0, ma200=False, ma50=False, mh=3,  # Đã nâng ROC từ 4.0 lên 4.5
    ),
    "CORE-MBB": dict(
        tickers=["SSI","FRT","MWG","IMP","DVP","BSR","APG"],
        volr=1.0, roc=1.0, macd=-0.5, adx=18.0, ma200=True, ma50=False, mh=7,  # Đã siết ADX từ 15 lên 18
    ),
    "CORE-TCH": dict(
        tickers=["NHA","FRT","ABB","SCL","MBS","APG","SJS","HAH","SIP","CTR","MCH",
                 "STB","BCM","HTN","GEG","VPB","VDS","APS","TCO"],
        volr=1.2, roc=2.0, macd=0.0, adx=18.0, ma200=False, ma50=False, mh=12, # Đã tăng Hold từ 10 lên 12 phiên
    ),
    "CORE-DGW": dict(
        tickers=["VGI","SCL","CSV","LPB","VTP","SJS","DCM","DPM","BCM","TVS","DGW","APG","VPB"],
        volr=0.7, roc=2.0, macd=-0.5, adx=25.0, ma200=False, ma50=False, mh=7,  # Đã tối ưu VolR=0.7, ROC=2.0
    ),
}

POSITION_SIZE = 100_000_000   # 100 triệu VNĐ mỗi lệnh
MAX_POSITIONS = 10            # Giữ tối đa 10 vị thế toàn danh mục
CAPITAL_INITIAL = 1_000_000_000 # Vốn ban đầu 1 Tỷ

TIMEZONE = "Asia/Ho_Chi_Minh"
STATE_FILE = "live_state_step2.json"
LOG_FILE = "log_step2.csv"
TELEGRAM_TITLE = "ST5 STEP2 REFINED BOT"

DELAY_BETWEEN_TICKERS = 1.5
 
