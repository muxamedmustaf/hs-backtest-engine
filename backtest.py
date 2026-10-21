# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st, yfinance as yf, plotly.graph_objects as go, pandas as pd
import numpy as np

# ⬇️⬇️ استيراد صحيح لملف data_provider (بدون get_provider_info) ⬇️⬇️
try:
    from data_provider import fetch_data, get_github_repo, PROVIDER
except ImportError:
    fetch_data = None
    get_github_repo = None
    PROVIDER = None

# ⬇️⬇️ استيراد محرك التحليل ⬇️⬇️
try:
    from engine import run_full_analysis, backtest_strategy, REASON_MAP, diagnose_filters
except ImportError:
    diagnose_filters = None

# ⬇️⬇️ استيراد الشيت ⬇️⬇️
try:
    from ffff import get_symbols_from_sheet
except ImportError:
    def get_symbols_from_sheet(*args, **kwargs): return [["EURUSD=X", "BTC-USD"]]

st.set_page_config(
    page_title="Smart Market Analyzer & Backtest Lab",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ⬇️⬇️ تحسينات CSS للموبايل وإخفاء القوائم الجانبية ⬇️⬇️
st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    .main .block-container { max-width: 100% !important; padding: 0.5rem 1rem !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 15px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    label, .stRadio label, .stTextInput label, .stSelectbox label { direction: rtl; text-align: right; }
    div[data-testid="stMetricLabel"] { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    .stButton > button { direction: rtl; text-align: center; }
    .stAlert, .stInfo, .stSuccess, .stWarning, .stError { direction: rtl; text-align: right; }
    .stDataFrame { direction: ltr; }
    .js-plotly-plot .plotly, .js-plotly-plot .main-svg { touch-action: none !important; }
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"
ALL_GLOBAL_INTERVALS = [
    "1m", "2m", "3m", "4m", "5m", "10m", "15m", "30m", "45m", "1h", "2h", "3h", "4h", "6h", "8h", "12h", "1d", "2d", "3d", "1wk", "1mo", "3mo", "6mo", "1y"
]
INTERVAL_LIMITS = {
    "1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60, "60m": 730, "90m": 60, "1h": 730,
}

IC_MARKETS_SPECS = {
    "BTC-USD": {"contract": 1, "min_lot": 0.01, "step": 0.01, "pip": 1.0, "cat": "🪙 Crypto"},
    "ETH-USD": {"contract": 1, "min_lot": 0.01, "step": 0.01, "pip": 1.0, "cat": "🪙 Crypto"},
    "EURUSD": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "GBPUSD": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "USDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 JPY"},
    "USDCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "USDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "AUDUSD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "NZDUSD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "EURGBP=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "EURCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURAUD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "GBPCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPAUD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "AUDCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "NZDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "NZDCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "NZDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "CADJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "CHFJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "USDTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Exotic"},
    "USDCNH=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Exotic"},
    "USDNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Scandinavian"},
    "USDSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Exotic"},
    "EURDKK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Scandinavian"},
    "CHFSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "🔀 Cross"},
    "SGDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "💴 Cross"},
    "USDHKD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Exotic"},
    "NZDGBP=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURHKD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Exotic"},
    "EURNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Scandinavian"},
    "EURPLN=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Exotic"},
    "EURSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Scandinavian"},
    "GBPSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Exotic"},
    "NOKSEK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Scandinavian"},
    "USDTHB=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01, "cat": "⚠️ Exotic"},
}

def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ["XAUUSD", "XAUUSD=X", "GOLD"]: return "GC=F"
    if sym in ["XAGUSD", "XAGUSD=X", "SILVER"]: return "SI=F"
    if sym == "GBPADY=X": return "GBPNZD=X"
    if len(sym) == 6 and sym.isalpha(): return f"{sym}=X"
    return sym

def pip_size_for(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["pip"]
    if "XAU" in s or "GOLD" in s: return 0.1
    if "XAG" in s or "SILVER" in s: return 0.01
    if any(x in s for x in ["BTC", "ETH"]): return 1.0
    if any(x in s for x in ["US30", "NAS", "SPX", "US100", "US500"]): return 1.0
    if "JPY" in s: return 0.01
    high_price = ["HUF", "TRY", "SEK", "NOK", "CZK", "MXN", "ZAR", "PLN", "INR", "THB", "DKK", "HKD", "SGD", "PHP", "IDR"]
    if any(c in s for c in high_price): return 0.01
    return 0.0001

def get_default_lot_for_symbol(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["min_lot"]
    if any(x in s for x in ["BTC", "ETH"]): return 0.01
    if any(x in s for x in ["US30", "NAS", "SPX"]): return 0.1
    return 0.01

def to_float(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def compute_pips(trades_df):
    if trades_df is None or trades_df.empty: return trades_df
    df = trades_df.copy()
    def pick(row, names):
        for n in names:
            if n in row and pd.notna(row[n]):
                v = to_float(row[n])
                if v is not None: return v
        return None
    pips_l, risk_l, reward_l, rr_l = [], [], [], []
    for _, row in df.iterrows():
        sym = row.get("symbol") or row.get("Symbol") or ""
        pip = pip_size_for(sym)
        entry = pick(row, ["Entry Price", "Entry", "entry"])
        exit_ = pick(row, ["Exit Price", "Exit", "exit", "Close Price"])
        sl = pick(row, ["Stop Loss", "SL", "sl"])
        tp = pick(row, ["Take Profit", "TP", "tp"])
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias
        pips = (entry - exit_) / pip if (entry is not None and exit_ is not None and is_sell) else ((exit_ - entry) / pip if (entry is not None and exit_ is not None) else None)
        risk = (sl - entry) / pip if (entry is not None and sl is not None and is_sell) else ((entry - sl) / pip if (entry is not None and sl is not None) else None)
        risk = abs(risk) if risk else None
        reward = (entry - tp) / pip if (entry is not None and tp is not None and is_sell) else ((tp - entry) / pip if (entry is not None and tp is not None) else None)
        reward = abs(reward) if reward else None
        rr = round(reward / risk, 2) if (risk and reward and risk > 0) else None
        pips_l.append(round(pips, 1) if pips is not None else None)
        risk_l.append(round(risk, 1) if risk is not None else None)
        reward_l.append(round(reward, 1) if reward is not None else None)
        rr_l.append(rr)
    df["Pips"] = pips_l
    df["Risk_Pips"] = risk_l
    df["Reward_Pips"] = reward_l
    df["RR_Ratio"] = rr_l
    return df

def compute_dollar_pnl(trades_df, lot=0.01):
    if trades_df is None or trades_df.empty: return trades_df
    df = trades_df.copy()
    usd_list, pct_list = [], []
    for _, row in df.iterrows():
        sym = str(row.get("symbol") or row.get("Symbol") or "").upper()
        entry = row.get("Entry Price") or row.get("Entry")
        exit_ = row.get("Exit Price") or row.get("Exit")
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias
        entry_f, exit_f = to_float(entry), to_float(exit_)
        if entry_f is None or exit_f is None:
            usd_list.append(None); pct_list.append(None); continue
        price_move = (exit_f - entry_f) if not is_sell else (entry_f - exit_f)
        if any(x in sym for x in ["BTC", "ETH"]): pnl_usd = price_move * lot * 1
        elif any(x in sym for x in ["US30", "NAS", "SPX", "US100", "US500"]): pnl_usd = price_move * lot * 1
        elif "XAU" in sym or "GC=F" in sym: pnl_usd = price_move * lot * 100
        elif "XAG" in sym or "SI=F" in sym: pnl_usd = price_move * lot * 5000
        else:
            if sym.endswith("USD"): pnl_usd = price_move * lot * 100000
            else: pnl_usd = price_move * lot * 100000 / exit_f if exit_f != 0 else None
        pct = (price_move / entry_f * 100) if entry_f != 0 else None
        usd_list.append(round(pnl_usd, 2) if pnl_usd is not None else None)
        pct_list.append(round(pct, 2) if pct is not None else None)
    df["PnL_USD"] = usd_list
    df["PnL_Pct"] = pct_list
    return df

def get_available_symbols():
    symbols_set = set(IC_MARKETS_SPECS.keys())
    try:
        sheet_symbols = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]
        for s in sheet_symbols: symbols_set.add(str(s).strip())
    except Exception: pass
    if "backtest_scanned_signals" in st.session_state:
        for item in st.session_state.backtest_scanned_signals:
            if "symbol" in item: symbols_set.add(item["symbol"])
    if "scanned_signals" in st.session_state:
        for item in st.session_state.scanned_signals:
            if "symbol" in item: symbols_set.add(item["symbol"])
    return sorted(list(symbols_set))

# ⬇️⬇️ إدارة الجلسة ⬇️⬇️
for k, v in [
    ("current_symbol", "NZDCAD=X"), 
    ("status_summary", "⚡ Live Scan & Backtest Lab • جاهز"),
    ("scanned_signals", []), 
    ("backtest_scanned_signals", []), 
    ("backtest_dfs", {}),
    ("backtest_period", ""), 
    ("backtest_start", ""), 
    ("backtest_end", ""),
    ("active_signal_symbol", None), 
    ("active_signal_entry", None), 
    ("active_signal_sl", None),
    ("active_signal_tp", None), 
    ("active_signal_bias", None), 
    ("near_signals", []),
]:
    if k not in st.session_state: st.session_state[k] = v

# ⬇️⬇️ الشريط العلوي وإدارة GitHub ⬇️⬇️
st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;direction:rtl;">
<div style="border:1px solid #DADCE0;background:#FFF;border-radius:16px;padding:8px 14px;font-weight:700;color:#0B57D0;">📈 {st.session_state.current_symbol}</div>
<div style="border:1px solid #DADCE0;background:#FFF;border-radius:30px;padding:8px 14px;font-weight:700;color:#0B57D0;">{st.session_state.status_summary}</div>
</div>''', unsafe_allow_html=True)

if get_github_repo is not None:
    with st.expander("⚙️ إدارة البيانات (GitHub) - اضغط للفتح", expanded=False):
        repo = get_github_repo()
        if repo:
            st.success(f"✅ متصل بـ: {repo.full_name}")
            if st.button("📥 تحديث وحفظ البيانات (الكل)", use_container_width=True):
                av = get_available_symbols()[:10]
                intervals = ["1h", "4h"]
                with st.status("جاري تحديث البيانات وحفظها...", expanded=True) as status:
                    for i, sym in enumerate(av):
                        st.write(f"تحديث {sym}...")
                        for intv in intervals:
                            fetch_data(fix_symbol(sym), interval=intv, start_date="2020-01-01", end_date=datetime.datetime.now().strftime("%Y-%m-%d"), force_download=True)
                    st.cache_data.clear()
                    status.update(label="✅ تم التحديث والحفظ في GitHub!", state="complete", expanded=False)
        else:
            st.warning("⚠️ لم يتم ربط GitHub. يرجى إضافة التوكن في الإعدادات.")

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي للأسواق", "🧪 مختبر الاختبار الرجعي (Backtest)"], horizontal=True)
st.markdown("---")

# ================= BACKTEST MODE =================
if app_mode == "🧪 مختبر الاختبار الرجعي (Backtest)":
    st.markdown("### 🧪 مختبر تحليل الأداء التاريخي")
    bt_scan_mode = st.radio("طريقة الفحص:", ["سهم فردي", "مسح كلي لشيت الأصول"], horizontal=True, key="bt_scan_mode")
    
    if bt_scan_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="EURUSD=X", key="bt_single_symbol")]
    else:
        all_sheet_symbols = get_available_symbols()
        c_sel1, c_sel2 = st.columns(2)
        if c_sel1.button("✅ تحديد كل عملات الشيت", use_container_width=True, key="bt_sel_all"):
            st.session_state["bt_selected_symbols"] = all_sheet_symbols; st.rerun()
        if c_sel2.button("❌ إلغاء التحديد", use_container_width=True, key="bt_clr_all"):
            st.session_state["bt_selected_symbols"] = []; st.rerun()
        if "bt_selected_symbols" not in st.session_state: st.session_state["bt_selected_symbols"] = ["EURUSD=X"]
        bt_symbols = st.multiselect("اختر الأصول للفحص:", all_sheet_symbols, key="bt_selected_symbols")

    now = datetime.datetime.now()
    available_years = [now.year, now.year - 1, now.year - 2]
    st.markdown("#### 📅 اختيار الفترة الزمنية")
    period_mode = st.radio("نمط الفترة:", ["📆 شهر واحد", "🗓️ نطاق مخصص", "📊 أشهر متعددة", "🗓️ سنة كاملة"], horizontal=True, key="bt_period_mode")
    
    start_date = None; end_date = None; period_label = ""
    months_dict = {1: "01 - يناير", 2: "02 - فبراير", 3: "03 - مارس", 4: "04 - إبريل", 5: "05 - مايو", 6: "06 - يونيو", 7: "07 - يوليو", 8: "08 - أغسطس", 9: "09 - سبتمبر", 10: "10 - أكتوبر", 11: "11 - نوفمبر", 12: "12 - ديسمبر"}

    if period_mode == "📆 شهر واحد":
        c_yr, c_mo = st.columns(2)
        selected_year = c_yr.selectbox("📅 السنة:", available_years, index=0, key="bt_single_year")
        selected_month = c_mo.selectbox("🗓️ الشهر:", list(months_dict.keys()), format_func=lambda x: months_dict[x], index=now.month - 1, key="bt_single_month")
        _, last_day = calendar.monthrange(selected_year, selected_month)
        start_date = f"{selected_year}-{selected_month:02d}-01"; end_date = f"{selected_year}-{selected_month:02d}-{last_day:02d}"
        period_label = f"{months_dict[selected_month]} {selected_year}"
    elif period_mode == "🗓️ نطاق مخصص":
        c1, c2 = st.columns(2)
        start_pick = c1.date_input("📅 من تاريخ:", value=datetime.date(now.year, max(1, now.month - 1), 1), key="bt_custom_start")
        end_pick = c2.date_input("📅 إلى تاريخ:", value=datetime.date.today(), key="bt_custom_end")
        if start_pick < end_pick:
            start_date = start_pick.strftime("%Y-%m-%d"); end_date = end_pick.strftime("%Y-%m-%d")
            period_label = f"من {start_date} إلى {end_date}"
        else: st.error("⚠️ تاريخ البداية يجب أن يكون قبل تاريخ النهاية")
    elif period_mode == "📊 أشهر متعددة":
        c_yr, c_months = st.columns([1, 2])
        multi_year = c_yr.selectbox("📅 السنة:", available_years, index=0, key="bt_multi_year")
        selected_months = c_months.multiselect("🗓️ اختر الأشهر:", options=list(months_dict.keys()), format_func=lambda x: months_dict[x], default=[now.month], key="bt_multi_months")
        if selected_months:
            sm = sorted(selected_months)
            _, last_last = calendar.monthrange(multi_year, sm[-1])
            start_date = f"{multi_year}-{sm[0]:02d}-01"; end_date = f"{multi_year}-{sm[-1]:02d}-{last_last:02d}"
            period_label = f"{' + '.join([months_dict[m] for m in sm])} {multi_year}"
        else: st.warning("⚠️ اختر شهراً واحداً على الأقل")
    elif period_mode == "🗓️ سنة كاملة":
        year_pick = st.selectbox("📅 السنة:", available_years, index=0, key="bt_full_year")
        start_date = f"{year_pick}-01-01"; end_date = f"{year_pick}-12-31"
        period_label = f"السنة {year_pick} كاملة"

    selected_interval = st.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=9, key="bt_interval")
    lot_size = st.number_input("💵 حجم اللوت لكل صفقة:", min_value=0.01, max_value=100.0, value=0.01, step=0.01, format="%.2f", key="bt_lot_size")

    if start_date and end_date:
        st.success(f"✅ الفترة: **{period_label}**")
        if st.button("📊 بدء محاكاة الاختبار الرجعي", use_container_width=True) and bt_symbols:
            results, dfs = [], {}
            p_bar = st.progress(0); s_txt = st.empty(); error_log = []
            
            for idx, sym in enumerate(bt_symbols):
                s_txt.text(f"محاكاة ({idx+1}/{len(bt_symbols)}): {sym}...")
                p_bar.progress((idx + 1) / len(bt_symbols))
                try:
                    # ⬇️⬇️ استخدام fetch_data من data_provider بدلاً من yf ⬇️⬇️
                    df = fetch_data(sym, interval=selected_interval, start_date=start_date, end_date=end_date) if fetch_data else yf.download(fix_symbol(sym), start=start_date, end=end_date, interval=selected_interval, progress=False, auto_adjust=False)
                    
                    if df is not None and not df.empty:
                        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                        trades = backtest_strategy(df, interval=selected_interval, symbol=sym)
                        if trades:
                            tdf = pd.DataFrame(trades)
                            if "symbol" not in tdf.columns: tdf["symbol"] = sym
                            results.append({"symbol": sym, "trades_df": tdf, "total_signals": len(tdf)})
                        dfs[sym] = df
                    else: error_log.append(f"⚠️ {sym}: لا توجد بيانات")
                except Exception as e: error_log.append(f"❌ {sym}: {type(e).__name__}: {e}")
            s_txt.empty(); p_bar.empty()
            
            st.session_state.backtest_scanned_signals = results
            st.session_state.backtest_dfs = dfs
            st.session_state.backtest_period = period_label
            st.session_state.backtest_start = start_date
            st.session_state.backtest_end = end_date
            
            if error_log:
                with st.expander(f"⚠️ تحذيرات ({len(error_log)})"):
                    for msg in error_log: st.text(msg)

    if st.session_state.backtest_scanned_signals:
        res_list = st.session_state.backtest_scanned_signals
        dfs_dict = st.session_state.backtest_dfs
        period_display = st.session_state.get("backtest_period", "غير محدد")
        all_dfs = [i["trades_df"] for i in res_list if "trades_df" in i and not i["trades_df"].empty]
        
        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            combined_df = compute_pips(combined_df)
            combined_df = compute_dollar_pnl(combined_df, lot=lot_size)
            
            g_res_col = "Result" if "Result" in combined_df.columns else "Head Result" if "Head Result" in combined_df.columns else None
            if g_res_col:
                g_series = combined_df[g_res_col].astype(str).str.upper()
                g_wins, g_losses, g_opens = len(combined_df[g_series.str.contains("WIN")]), len(combined_df[g_series.str.contains("LOSS")]), len(combined_df[g_series.str.contains("OPEN")])
            else: g_wins = g_losses = g_opens = 0
                
            g_closed = g_wins + g_losses
            g_win_rate = round((g_wins / g_closed) * 100, 1) if g_closed > 0 else 0.0
            g_loss_rate = round((g_losses / g_closed) * 100, 1) if g_closed > 0 else 0.0
            total_pips = combined_df["Pips"].dropna().sum()
            total_usd = combined_df["PnL_USD"].dropna().sum()
            wins_usd = combined_df.loc[g_series.str.contains("WIN"), "PnL_USD"].dropna().sum() if g_res_col else 0
            losses_usd = combined_df.loc[g_series.str.contains("LOSS"), "PnL_USD"].dropna().sum() if g_res_col else 0
            profit_factor = round(abs(wins_usd / losses_usd), 2) if losses_usd != 0 else float("inf")
            
            st.markdown(f"#### 🌐 الملخص الإجمالي — **{period_display}**")
            gm1, gm2, gm3, gm4 = st.columns(4)
            gm1.metric("📊 إجمالي الصفقات", len(combined_df))
            gm2.metric("✅ ناجحة", g_wins, delta=f"{g_win_rate}%")
            gm3.metric("❌ خاسرة", g_losses, delta=f"{g_loss_rate}%", delta_color="inverse")
            gm4.metric("⏳ مفتوحة", g_opens)
            gm5, gm6, gm7, gm8 = st.columns(4)
            gm5.metric("📉 إجمالي النقاط", f"{total_pips:+.1f}")
            gm6.metric("📊 متوسط النقاط", f"{combined_df['Pips'].dropna().mean():+.1f}")
            gm7.metric(f"💵 صافي الربح (لوت {lot_size})", f"{total_usd:+.2f} $")
            gm8.metric("⚖️ Profit Factor", f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞")
            
            st.markdown("---")
            if bt_scan_mode == "مسح كلي لشيت الأصول":
                opts = [f"{i['symbol']} | الصفقات: {i['total_signals']}" for i in res_list]
                active_item = res_list[opts.index(st.selectbox("👇 اختر الأصل:", opts))]
            else: active_item = res_list[0]
                
            active_sym = active_item["symbol"]
            trades_df = compute_dollar_pnl(compute_pips(active_item["trades_df"]), lot=lot_size)
            st.session_state.current_symbol = active_sym
            
            if len(trades_df) > 0:
                last_row = trades_df.iloc[-1]
                st.session_state.update({
                    "active_signal_symbol": active_sym, "active_signal_entry": last_row.get("Entry Price") or last_row.get("Entry"),
                    "active_signal_sl": last_row.get("Stop Loss") or last_row.get("SL"),
                    "active_signal_tp": last_row.get("Take Profit") or last_row.get("TP"),
                    "active_signal_bias": last_row.get("bias") or last_row.get("Bias")
                })
                
            res_col = "Result" if "Result" in trades_df.columns else "Head Result" if "Head Result" in trades_df.columns else None
            if res_col:
                res_series = trades_df[res_col].astype(str).str.upper()
                wins, losses, opens = len(trades_df[res_series.str.contains("WIN")]), len(trades_df[res_series.str.contains("LOSS")]), len(trades_df[res_series.str.contains("OPEN")])
            else: wins = losses = opens = 0
                
            closed_trades = wins + losses
            win_rate = round((wins / closed_trades) * 100, 1) if closed_trades > 0 else 0.0
            loss_rate = round((losses / closed_trades) * 100, 1) if closed_trades > 0 else 0.0
            
            st.markdown(f"### 📊 نتائج **{active_sym}** — {period_display}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("✅ أ. ناجحة", wins, delta=f"{win_rate}%")
            m2.metric("❌ ب. خاسرة", losses, delta=f"{loss_rate}%", delta_color="inverse")
            m3.metric("⏳ ج. مفتوحة", opens)
            m4.metric("📉 إجمالي النقاط", f"{trades_df['Pips'].dropna().sum():+.1f}")
            
            st.download_button("📥 تنزيل صفقات الأصل (CSV)", trades_df.to_csv(index=False).encode('utf-8-sig'), f"backtest_{active_sym}.csv", "text/csv", use_container_width=True)
            
            if active_sym in dfs_dict and not dfs_dict[active_sym].empty:
                df_res = dfs_dict[active_sym].copy()
                df_res['EMA50'] = df_res['Close'].ewm(span=50, adjust=False).mean()
                df_res['EMA200'] = df_res['Close'].ewm(span=200, adjust=False).mean()
                
                si = st.session_state.get(f"signal_index_{active_sym}", len(trades_df)-1)
                n1, n2, n3 = st.columns([1, 2, 1])
                with n1:
                    if st.button("⬅️ السابق", use_container_width=True, key="bt_prev_top"): st.session_state[f"signal_index_{active_sym}"] = max(0, si - 1); st.rerun()
                with n2: st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>إشارة {si+1} من {len(trades_df)}</div>", unsafe_allow_html=True)
                with n3:
                    if st.button("التالي ➡️", use_container_width=True, key="bt_next_top"): st.session_state[f"signal_index_{active_sym}"] = min(len(trades_df)-1, si + 1); st.rerun()
                
                cur_trade = trades_df.iloc[si]
                fig = go.Figure(data=[go.Candlestick(x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"], name="السعر")])
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA50'], line=dict(color='orange', width=1.2), name="EMA 50"))
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA200'], line=dict(color='blue', width=1.2), name="EMA 200"))
                
                if "nodes" in cur_trade and isinstance(cur_trade['nodes'], list):
                    sn = sorted(cur_trade['nodes'], key=lambda x: pd.to_datetime(x[0]))
                    fig.add_trace(go.Scatter(x=[n[0] for n in sn], y=[n[1] for n in sn], mode="lines+markers", name=f"النمط #{si+1}", line=dict(color="#9C27B0", width=2)))
                for val, col, txt in [(cur_trade.get('Entry Price'), "#2196F3", "دخول"), (cur_trade.get('Stop Loss'), "#F44336", "وقف"), (cur_trade.get('Take Profit'), "#4CAF50", "هدف")]:
                    if val: fig.add_hline(y=val, line_dash="dash", line_color=col, annotation_text=txt)
                    
                fig.update_layout(template="plotly_white", height=500, autosize=True, margin=dict(l=10, r=10, t=30, b=30), xaxis_rangeslider_visible=False, yaxis=dict(side="right", automargin=True), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': False})
                
                st.markdown("<br>", unsafe_allow_html=True)
                n4, n5, n6 = st.columns([1, 2, 1])
                with n4:
                    if st.button("⬅️ السابق", use_container_width=True, key="bt_prev_bottom"): st.session_state[f"signal_index_{active_sym}"] = max(0, si - 1); st.rerun()
                with n6:
                    if st.button("التالي ➡️", use_container_width=True, key="bt_next_bottom"): st.session_state[f"signal_index_{active_sym}"] = min(len(trades_df)-1, si + 1); st.rerun()
                
                st.dataframe(cur_trade.to_frame().T, use_container_width=True)

            with st.expander("🔬 التقرير التشخيصي الذكي (تطوير ذاتي)", expanded=True):
                if diagnose_filters is None: st.error("⚠️ `diagnose_filters` غير موجودة في engine.py")
                else:
                    df_for_diag = dfs_dict.get(active_sym)
                    if df_for_diag is not None and not df_for_diag.empty:
                        with st.spinner("جاري تحليل أسباب الخسارة والربح..."):
                            diag = diagnose_filters(df_for_diag, interval=selected_interval, symbol=active_sym)
                            smart = diag.get("smart_diagnosis", {})
                            if smart.get("verdict"): st.markdown(f"### 🎯 الحكم: {smart['verdict']}")
                            
                            stats = smart.get("stats", {})
                            if stats:
                                dc1, dc2, dc3 = st.columns(3)
                                dc1.metric("إجمالي الصفقات المغلقة", stats.get("closed_trades", 0))
                                dc2.metric("الصفقات الرابحة", stats.get("wins", 0), stats.get("win_rate", "0%"))
                                dc3.metric("الصفقات الخاسرة", stats.get("losses", 0), stats.get("loss_rate", "0%"), delta_color="inverse")
                            
                            if smart.get("action_plan"):
                                st.markdown("#### 💡 خطة التطوير الذاتي (توصيات المحرك)")
                                for item in smart["action_plan"]:
                                    if item.startswith("⚠️") or item.startswith("📉"): st.warning(item)
                                    else: st.success(item)
    else:
        st.info("ℹ️ لم يتم العثور على نتائج بعد. اضبط الإعدادات واضغط 'بدء المحاكاة'.")

# ================= LIVE SCAN MODE =================
else:
    scan_mode = st.radio("طريقة الفحص:", ["سهم فردي", "مسح كلي لشيت الأصول"], horizontal=True, key="live_scan_mode")
    
    if scan_mode == "سهم فردي":
        symbols = [st.text_input("رمز الأصل", value="NZDCAD=X", key="live_single_symbol")]
    else:
        all_sheet_symbols = get_available_symbols()
        c_sel1, c_sel2 = st.columns(2)
        if c_sel1.button("✅ تحديد كل عملات الشيت", use_container_width=True, key="live_sel_all"):
            st.session_state["live_selected_symbols"] = all_sheet_symbols; st.rerun()
        if c_sel2.button("❌ إلغاء التحديد", use_container_width=True, key="live_clr_all"):
            st.session_state["live_selected_symbols"] = []; st.rerun()
        if "live_selected_symbols" not in st.session_state: st.session_state["live_selected_symbols"] = ["NZDCAD=X"]
        symbols = st.multiselect("اختر الأصول للفحص:", all_sheet_symbols, key="live_selected_symbols")

    c1, c2 = st.columns(2)
    selected_interval = c1.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=9, key="live_interval")
    selected_period = c2.selectbox("📅 نطاق البيانات:", ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"], index=3, key="live_period")
    
    if st.button("🚀 بدء المسح والتحليل الفوري", use_container_width=True) and symbols:
        valid = []; p_bar = st.progress(0); s_txt = st.empty(); error_log = []
        
        for idx, sym in enumerate(symbols):
            s_txt.text(f"فحص ({idx+1}/{len(symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(symbols))
            try:
                # ⬇️⬇️ استخدام fetch_data من data_provider ⬇️⬇️
                df = fetch_data(sym, interval=selected_interval, period=selected_period) if fetch_data else yf.download(fix_symbol(sym), period=selected_period, interval=selected_interval, progress=False, auto_adjust=False)
                
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    if len(df) >= 20:
                        res = run_full_analysis(df, interval=selected_interval, symbol=sym)
                        if res["signal"] in ["STRONG BUY", "STRONG SELL"] or scan_mode == "سهم فردي": 
                            valid.append({"symbol": sym, "result": res})
                else: error_log.append(f"⚠️ {sym}: لا توجد بيانات")
            except Exception as e: error_log.append(f"❌ {sym}: {type(e).__name__}: {e}")
        s_txt.empty(); p_bar.empty()
        st.session_state.scanned_signals = valid
        
        if error_log:
            with st.expander(f"⚠️ تحذيرات ({len(error_log)})"):
                for msg in error_log: st.text(msg)

    if st.session_state.scanned_signals:
        sigs = st.session_state.scanned_signals
        if scan_mode == "مسح كلي لشيت الأصول":
            opts = [f"{i['symbol']} | {i['result']['signal']}" for i in sigs]
            active_idx = opts.index(st.selectbox("👇 اختر الأصل:", opts))
        else: active_idx = 0
            
        si = st.session_state.get("live_si", active_idx)
        n1, n2, n3 = st.columns([1, 2, 1])
        with n1:
            if st.button("⬅️ السابق", use_container_width=True, key="live_prev_top"): st.session_state["live_si"] = max(0, si - 1); st.rerun()
        with n2: st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>إشارة {si+1} من {len(sigs)}</div>", unsafe_allow_html=True)
        with n3:
            if st.button("التالي ➡️", use_container_width=True, key="live_next_top"): st.session_state["live_si"] = min(len(sigs)-1, si + 1); st.rerun()

        active_res = sigs[si]['result']
        active_sym = active_res.get("symbol", "N/A")
        st.session_state.current_symbol = active_sym
        
        st.session_state.update({
            "active_signal_symbol": active_sym, "active_signal_entry": active_res.get("entry"),
            "active_signal_sl": active_res.get("sl"), "active_signal_tp": active_res.get("tp"),
            "active_signal_bias": active_res.get("bias")
        })
        
        e1, e2, e3 = st.columns(3)
        e1.metric("🎯 سعر الدخول", f"{active_res.get('entry', 0)}")
        e2.metric("🛑 وقف الخسارة", f"{active_res.get('sl', 0)}")
        e3.metric("🎯 الهدف", f"{active_res.get('tp', 0)}")
        
        df_res = active_res.get("df")
        if df_res is not None and not df_res.empty:
            df_res = df_res.copy()
            df_res['EMA50'] = df_res['Close'].ewm(span=50, adjust=False).mean()
            df_res['EMA200'] = df_res['Close'].ewm(span=200, adjust=False).mean()
            fig = go.Figure(data=[go.Candlestick(x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"], name="السعر")])
            fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA50'], line=dict(color='orange', width=1.2), name="EMA 50"))
            fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA200'], line=dict(color='blue', width=1.2), name="EMA 200"))
            
            live_nodes = active_res.get("nodes") or active_res.get("pattern_nodes")
            if isinstance(live_nodes, list) and live_nodes:
                sn = sorted(live_nodes, key=lambda x: pd.to_datetime(x[0]))
                fig.add_trace(go.Scatter(x=[n[0] for n in sn], y=[n[1] for n in sn], mode="lines+markers", name="النمط المكتشف", line=dict(color="#9C27B0", width=2)))
                
            for val, col, txt in [(active_res.get('entry'), "#2196F3", "دخول"), (active_res.get('sl'), "#F44336", "وقف"), (active_res.get('tp'), "#4CAF50", "هدف")]:
                if val: fig.add_hline(y=val, line_dash="dash", line_color=col, annotation_text=txt)
                
            fig.update_layout(template="plotly_white", height=500, autosize=True, margin=dict(l=10, r=10, t=30, b=30), xaxis_rangeslider_visible=False, yaxis=dict(side="right", automargin=True), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': False})

            st.markdown("<br>", unsafe_allow_html=True)
            n4, n5, n6 = st.columns([1, 2, 1])
            with n4:
                if st.button("⬅️ السابق", use_container_width=True, key="live_prev_bottom"): st.session_state["live_si"] = max(0, si - 1); st.rerun()
            with n6:
                if st.button("التالي ➡️", use_container_width=True, key="live_next_bottom"): st.session_state["live_si"] = min(len(sigs)-1, si + 1); st.rerun()
