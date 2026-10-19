# ==============================================================================
# 🟡 TWELVE DATA
# ==============================================================================
def _fetch_twelve(symbol, interval="1h", period="3mo",
                  start_date=None, end_date=None):
    """Twelve Data API."""
    try:
        from twelvedata import TDClient
    except ImportError:
        raise ImportError("Ku shub: pip install twelvedata")

    td = TDClient(apikey=TWELVE_DATA_API_KEY)
    
    tf = _timeframe_twelve(interval)
    sym = _symbol_twelve(symbol)

    # 🎯 إعداد المعاملات الأساسية
    kwargs = {
        "symbol": sym,
        "interval": tf,
        "timezone": "UTC"
    }

    # 🎯 إذا تم تحديد تاريخ بداية ونهاية (في الاختبار الرجعي)، نمررها للـ API
    if start_date and end_date:
        kwargs["start_date"] = start_date
        kwargs["end_date"] = end_date
    else:
        # في الماسح الحي، نجلب آخر 5000 شمعة
        kwargs["outputsize"] = 5000

    # استدعاء الـ API
    ts = td.time_series(**kwargs)

    df = ts.as_pandas()

    if df is None or df.empty:
        return None

    # Twelve Data wuxuu soo celiyaa xogta kor ilaa hoos, marka waa in la rogaa
    df = df.iloc[::-1]

    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }, inplace=True)

    # XALKII DIHBAATADA RATE LIMIT
    time.sleep(8)  # Sug 8 ilbirqsi ka hor inta aadan lammaanaha xigta soo qaadin

    return df
