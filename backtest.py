# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st, yfinance as yf, plotly.graph_objects as go, pandas as pd
import numpy as np
from plotly.subplots import make_subplots
from data_provider import fetch_data, get_github_repo

# ⬇️ استيراد آمن يمنع الانهيار ⬇️
try:
    from engine import run_full_analysis, backtest_strategy
except Exception as e:
    st.error(f"تأكد من وجود ملف engine.py وخلوه من الأخطاء: {e}")
    st.stop()

try:
    from engine import REASON_MAP
except ImportError:
    REASON_MAP = {}

try:
    from ffff import get_symbols_from_sheet
    SHEET_ENABLED = True
except ImportError:
    SHEET_ENABLED = False
    def get_symbols_from_sheet(*args, **kwargs): return [], "ملف ffff.py غير موجود."

st.set_page_config(page_title="H&S Hunter Pro", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    .main .block-container { max-width: 98% !important; padding: 1.5rem 2.5rem !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 16px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; margin-bottom: 1rem; }
    label, .stRadio label, .stTextInput label, .stSelectbox label, .stMultiSelect label { direction: rtl; text-align: right; margin-bottom: 0.5rem; }
    .stButton > button { direction: rtl; text-align: center; padding: 0.6rem 1rem; font-size: 1rem; }
    .stAlert, .stInfo, .stSuccess, .stWarning, .stError { direction: rtl; text-align: right; padding: 1rem; font-size: 16px; font-weight: bold;}
    .stDataFrame { direction: ltr; }
    div[data-testid="stHorizontalBlock"] { gap: 1.5rem; }
    div[data-testid="stVerticalBlock"] { gap: 1rem; }
    
    .float-top {
        position: fixed; bottom: 80px; right: 20px; z-index: 99999;
        background-color: #E91E63; color: white !important; border-radius: 50%;
        width: 55px; height: 55px; display: flex; align-items: center; justify-content: center;
        font-size: 28px; text-decoration: none; box-shadow: 0 4px 10px rgba(0,0,0,0.4);
        cursor: pointer; border: none;
    }
    .float-top:hover { background-color: #C2185B; color: white; }
    .js-plotly-plot .plotly, .js-plotly-plot .main-svg { touch-action: none !important; }
</style>
<div id="top"></div>
<a href="javascript:void(0);" class="float-top" onclick="
    var main = document.querySelector('.main');
    var appView = document.querySelector('div[data-testid=\'stAppViewContainer\']');
    var scrollable = document.querySelector('section.main');
    if(main) main.scrollTo({top: 0, behavior: 'smooth'});
    if(appView) appView.scrollTo({top: 0, behavior: 'smooth'});
    if(scrollable) scrollable.scrollTo({top: 0, behavior: 'smooth'});
    window.scrollTo({top: 0, behavior: 'smooth'});
" title="العودة للأعلى">⬆️</a>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

ALL_GLOBAL_INTERVALS = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "4h", "1d", "5d", "1wk", "1mo", "3mo"]
ALL_PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]

IC_MARKETS_SPECS = {
    "BTC-USD":  {"contract": 1,      "min_lot": 0.01, "step": 0.01, "pip": 1.0,    "cat": "🪙 Crypto"},
    "ETH-USD":  {"contract": 1,      "min_lot": 0.01, "step": 0.01, "pip": 1.0,    "cat": "🪙 Crypto"},
    "EURUSD":   {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "GBPUSD":   {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "USDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 JPY"},
    "USDCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "USDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "AUDUSD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "NZDUSD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
}

PLOTLY_CONFIG = {'responsive': True, 'scrollZoom': True, 'displaylogo': False, 'displayModeBar': True, 'dragmode': 'pan', 'doubleClick': 'reset+autosize'}

def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ("XAUUSD", "GOLD"): return "GC=F"
    if len(sym) == 6 and sym.isalpha(): return f"{sym}=X"
    return sym

def pip_size_for(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["pip"]
    if "XAU" in s or "GOLD" in s: return 0.1
    if "XAG" in s or "SILVER" in s: return 0.01
    if any(x in s for x in ["BTC", "ETH"]): return 1.0
    if "JPY" in s: return 0.01
    return 0.0001

@st.cache_data(ttl=3600, show_spinner="جاري جلب العملات من الشيت...")
def get_available_symbols():
    s = set(IC_MARKETS_SPECS.keys())
    sheet_count = 0
    error_msg = None
    
    if SHEET_ENABLED:
        try:
            result = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
            if isinstance(result, tuple) and len(result) == 2:
                sheet_symbols, err = result
                if err: error_msg = err
                elif sheet_symbols and isinstance(sheet_symbols, list):
                    for x in sheet_symbols: 
                        if x and str(x).lower() != 'nan':
                            s.add(str(x).strip().upper())
                    sheet_count = len(sheet_symbols)
            elif isinstance(result, list):
                for x in result: s.add(str(x).strip().upper())
                sheet_count = len(result)
        except Exception as e: 
            error_msg = str(e)
            
    return sorted(s), sheet_count, error_msg

all_symbols, sheet_count, sheet_error = get_available_symbols()

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_smart_fetch(symbol, interval, source_choice, start_date=None, end_date=None, period=None):
    df = None
    force_dl = True if "الإنترنت" in source_choice else False
    
    if "GitHub" in source_choice or "الإنترنت" in source_choice:
        try:
            if start_date and end_date: 
                df = fetch_data(symbol, interval=interval, start_date=start_date, end_date=end_date, force_download=force_dl)
            else: 
                df = fetch_data(symbol, interval=interval, period=period, force_download=force_dl)
        except Exception:
            df = None

    if df is None or "Yahoo" in source_choice:
        try:
            if start_date and end_date:
                df = yf.download(fix_symbol(symbol), start=start_date, end=end_date, interval=interval, progress=False, auto_adjust=False)
            else:
                df = yf.download(fix_symbol(symbol), period=period, interval=interval, progress=False, auto_adjust=False)
        except Exception:
            df = None

    if df is not None and isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_backtest(symbol, interval, start_date, end_date, period, source_choice):
    df = _cached_smart_fetch(symbol, interval, source_choice, start_date=start_date, end_date=end_date, period=period)
    if df is None or df.empty: 
        return None, None, "فشل جلب البيانات أو لا توجد بيانات في هذه الفترة.", {}
    try: 
        trades = backtest_strategy(df)
    except Exception as e: 
        return df, None, f"خطأ داخل محرك البحث (engine.py): {str(e)}", {}
    return df, trades, None, {}

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_live(symbol, interval, period, source_choice):
    df = _cached_smart_fetch(symbol, interval, source_choice, period=period)
    if df is None or df.empty: return None, None
    try: res = run_full_analysis(df)
    except Exception: return df, None
    return df, res

@st.cache_data(ttl=3600, show_spinner=False)
def _prepare_chart_data(symbol, interval, start_date, end_date, period, source_choice):
    df = _cached_smart_fetch(symbol, interval, source_choice, start_date=start_date, end_date=end_date, period=period)
    if df is None or df.empty: return None
    df = df.copy()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df

def compute_pips(df):
    if df is None or df.empty: return df
    df = df.copy()
    def _f(v): return float(v) if pd.notna(v) else None
    pips_l = []
    for _, row in df.iterrows():
        pip = pip_size_for(row.get("symbol") or row.get("Symbol") or "")
        e = _f(row.get("Entry"))
        x = _f(row.get("Exit Price"))
        bias = str(row.get("Bias") or "").upper()
        is_sell = "BEAR" in bias
        p = (e - x) / pip if (e and x and is_sell) else (x - e) / pip if (e and x) else None
        pips_l.append(round(p, 1) if p is not None else None)
    df["Pips"] = pips_l
    return df

def compute_dollar_pnl(df, capital=1000.0, risk_pct=2.0):
    if df is None or df.empty: return df
    df = df.copy()
    usd_list = []
    
    for _, row in df.iterrows():
        sym = str(row.get("symbol") or "").upper()
        try: 
            e = float(row.get("Entry"))
            x = float(row.get("Exit Price"))
            sl = float(row.get("SL"))
        except: 
            usd_list.append(None); continue
            
        is_sell = "BEAR" in str(row.get("Bias")).upper()
        risk_distance = abs(e - sl)
        if risk_distance == 0: risk_distance = 1e-5
        
        max_risk_usd = capital * (risk_pct / 100)
        
        if "BTC" in sym or "ETH" in sym: 
            lot_size = max_risk_usd / risk_distance
            pnl = ((x - e) if not is_sell else (e - x)) * lot_size
        elif "XAU" in sym or "GC=F" in sym: 
            lot_size = max_risk_usd / (risk_distance * 100)
            pnl = ((x - e) if not is_sell else (e - x)) * lot_size * 100
        else:
            if sym.endswith("USD"):
                lot_size = max_risk_usd / (risk_distance * 100000)
                pnl = ((x - e) if not is_sell else (e - x)) * lot_size * 100000
            else:
                lot_size = max_risk_usd / (risk_distance * 100000)
                pnl = ((x - e) if not is_sell else (e - x)) * lot_size * 100000 / x if x else None
                
        usd_list.append(round(pnl, 2) if pnl is not None else None)
        
    df["PnL_USD"] = usd_list
    return df

def draw_pattern(fig, source):
    if source is None: return
    nodes = source.get("nodes", [])
    neckline_nodes = source.get("neckline_nodes", [])
    
    if len(nodes) > 0:
        nx = [n[0] for n in nodes]
        ny = [n[1] for n in nodes]
        fig.add_trace(go.Scatter(x=nx, y=ny, mode="lines+markers", name="Pattern", line=dict(color="#FF9800", width=2, dash="dot")), row=1, col=1)
        
    if len(neckline_nodes) == 2:
        nl_x = [neckline_nodes[0][0], neckline_nodes[1][0]]
        nl_y = [neckline_nodes[0][1], neckline_nodes[1][1]]
        fig.add_trace(go.Scatter(x=nl_x, y=nl_y, mode="lines", name="Neckline", line=dict(color="#2196F3", width=2)), row=1, col=1)

def render_chart_fast(sym, cur, df_chart_full, chart_mode):
    if df_chart_full is None or df_chart_full.empty: return
    nodes = cur.get("nodes", [])
    if not nodes: return
    
    pattern_start, pattern_end = nodes[0][0], nodes[-1][0]
    span = pattern_end - pattern_start
    
    if chart_mode == "adaptive":
        x_min = pattern_start - span * 1.5
        x_max = pattern_end + span * 1.5
        try:
            idx_min = max(0, df_chart_full.index.searchsorted(x_min))
            idx_max = min(len(df_chart_full), df_chart_full.index.searchsorted(x_max))
            df_window = df_chart_full.iloc[idx_min:idx_max].copy()
            if len(df_window) > 250:
                mid = len(df_window) // 2
                df_window = df_window.iloc[max(0, mid-125):min(len(df_window), mid+125)]
        except: df_window = df_chart_full.tail(150).copy()
    else:
        df_window = df_chart_full.copy()
        x_min = df_window.index[0] if not df_window.empty else pattern_start
        x_max = df_window.index[-1] if not df_window.empty else pattern_end

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
    fig.add_trace(go.Candlestick(x=df_window.index, open=df_window["Open"], high=df_window["High"], low=df_window["Low"], close=df_window["Close"], name="Price"), row=1, col=1)
    
    if "EMA50" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA50"], line=dict(color="orange", width=1), name="EMA 50"), row=1, col=1)
    if "EMA200" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA200"], line=dict(color="blue", width=1), name="EMA 200"), row=1, col=1)
    
    draw_pattern(fig, cur)
    
    try:
        e_val = float(cur.get("entry", 0))
        s_val = float(cur.get("sl", 0))
        t_val = float(cur.get("tp", 0))
        
        if e_val > 0: fig.add_hline(y=e_val, line_dash="dash", line_color="#2196F3", annotation_text=f"الدخول: {e_val}", annotation_position="top left", row=1, col=1)
        if s_val > 0: fig.add_hline(y=s_val, line_dash="dash", line_color="#F44336", annotation_text=f"وقف الخسارة: {s_val}", annotation_position="bottom left", row=1, col=1)
        if t_val > 0: fig.add_hline(y=t_val, line_dash="dash", line_color="#4CAF50", annotation_text=f"الهدف: {t_val}", annotation_position="top left", row=1, col=1)
    except Exception:
        pass
    
    if "Volume" in df_window.columns:
        fig.add_trace(go.Bar(x=df_window.index, y=df_window["Volume"], name="Volume", marker_color='rgba(158, 158, 158, 0.5)'), row=2, col=1)
    
    fig.update_layout(
        template="plotly_white", height=650, autosize=True, xaxis_rangeslider_visible=False, 
        dragmode="pan", hovermode="x unified", margin=dict(l=10, r=60, t=40, b=40), 
        yaxis=dict(side="right", showgrid=True, gridcolor="#EEEEEE", fixedrange=False, automargin=True),
        yaxis2=dict(side="right", showgrid=False, fixedrange=False, automargin=True),
        xaxis=dict(showgrid=True, gridcolor="#F5F5F5", range=[x_min, x_max], fixedrange=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

with st.expander("⚙️ إدارة البيانات (GitHub) - اضغط للفتح", expanded=False):
    repo = get_github_repo()
    if repo:
        st.success(f"✅ متصل بـ: {repo.full_name}")
        
        if sheet_count > 0: st.success(f"📊 تم جلب **{sheet_count}** عملة من الشيت بنجاح + العملات الافتراضية. الإجمالي: **{len(all_symbols)}** عملة.")
        else: st.error(f"⚠️ فشل جلب العملات من الشيت! السبب: {sheet_error if sheet_error else 'قد يكون اسم الشيت أو العمود غير صحيح.'}")
        
        dl_mode = st.radio("طريقة التنزيل:", ["الكل (شيت)", "مجموعة محددة", "عملة واحدة"], horizontal=True, key="dl_mode")
        intvs_to_dl = st.multiselect("اختر الأطُر الزمنية للتنزيل:", ALL_GLOBAL_INTERVALS, default=["1h", "4h"], key="dl_intvs")
        
        if dl_mode == "الكل (شيت)":
            st.info(f"سيتم تنزيل **جميع** العملات ({len(all_symbols)} عملة).")
            if st.button("📥 تنزيل وحفظ الكل", use_container_width=True):
                with st.status("جاري تحديث البيانات وحفظها...", expanded=True) as status:
                    for i, sym in enumerate(all_symbols):
                        st.write(f"[{i+1}/{len(all_symbols)}] تحديث {sym}...")
                        for intv in intvs_to_dl:
                            _cached_smart_fetch(fix_symbol(sym), intv, "الإنترنت", period="max")
                    st.cache_data.clear()
                    status.update(label="✅ تم التحديث والحفظ!", state="complete", expanded=False)
                    
        elif dl_mode == "مجموعة محددة":
            selected_syms = st.multiselect("اختر العملات المراد تنزيلها:", all_symbols, default=all_symbols[:5], key="dl_selected_syms")
            if st.button("📥 تنزيل وحفظ المحدد", use_container_width=True) and selected_syms:
                with st.status(f"جاري تحديث {len(selected_syms)} عملات...", expanded=True) as status:
                    for i, sym in enumerate(selected_syms):
                        st.write(f"[{i+1}/{len(selected_syms)}] تحديث {sym}...")
                        for intv in intvs_to_dl:
                            _cached_smart_fetch(fix_symbol(sym), intv, "الإنترنت", period="max")
                    st.cache_data.clear()
                    status.update(label="✅ تم التحديث والحفظ!", state="complete", expanded=False)
                    
        elif dl_mode == "عملة واحدة":
            single_sym = st.text_input("أدخل رمز العملة (مثال: XAUUSD أو EURUSD):", value="BTC-USD", key="single_dl_sym")
            if st.button("📥 تنزيل وحفظ العملة", use_container_width=True) and single_sym:
                with st.status(f"جاري تحديث {single_sym}...", expanded=True) as status:
                    for intv in intvs_to_dl:
                        st.write(f"تحديث {single_sym} للإطار {intv}...")
                        _cached_smart_fetch(fix_symbol(single_sym), intv, "الإنترنت", period="max")
                    st.cache_data.clear()
                    status.update(label=f"✅ تم تحديث {single_sym}!", state="complete", expanded=False)
    else:
        st.warning("⚠️ لم يتم ربط GitHub. يرجى إضافة التوكن في الإعدادات.")

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي", "🧪 مختبر الاختبار الرجعي"], horizontal=True)

# ================= BACKTEST MODE =================
if app_mode == "🧪 مختبر الاختبار الرجعي":
    st.markdown("### 🧪 مختبر الكتف والكتفين (H&S)")
    
    bt_data_source = st.radio(
        "📁 مصدر البيانات للمحاكاة:",
        ["📁 البيانات المحفوظة (GitHub - سريع جداً)", "🌐 جلب مباشر من الإنترنت (API - قد يكون بطيئاً)", "🌐 Yahoo Finance (بديل)"],
        horizontal=True
    )

    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True)
    if bt_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="BTC-USD")]
    else:
        c1, c2 = st.columns(2)
        if c1.button("✅ تحديد كل العملات (من الشيت والافتراضية)", use_container_width=True):
            st.session_state["bt_selected_symbols"] = all_symbols; st.rerun()
        if c2.button("❌ إلغاء التحديد", use_container_width=True):
            st.session_state["bt_selected_symbols"] = []; st.rerun()
        if "bt_selected_symbols" not in st.session_state: st.session_state["bt_selected_symbols"] = ["BTC-USD"]
        bt_symbols = st.multiselect("اختر:", all_symbols, key="bt_selected_symbols")

    now = datetime.datetime.now()
    st.markdown("#### 📅 اختيار الفترة الزمنية")
    date_mode = st.radio("طريقة تحديد الفترة:", ["📅 تواريخ مخصصة", "⏳ فترة سريعة"], horizontal=True, key="bt_date_mode")
    
    sd, ed, period = None, None, None
    if date_mode == "📅 تواريخ مخصصة":
        c1, c2, c3 = st.columns(3)
        sd = c1.date_input("من:", value=datetime.date(now.year-1, 1, 1)).strftime("%Y-%m-%d")
        ed = c2.date_input("إلى:", value=datetime.date.today()).strftime("%Y-%m-%d")
        interval = c3.selectbox("الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=ALL_GLOBAL_INTERVALS.index("1h"))
    else:
        c1, c2 = st.columns(2)
        period = c1.selectbox("اختر الفترة السريعة:", ALL_PERIODS, index=ALL_PERIODS.index("1y"))
        interval = c2.selectbox("الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=ALL_GLOBAL_INTERVALS.index("1h"))

    if st.button("📊 بدء المحاكاة", use_container_width=True) and bt_symbols:
        results, dfs, all_stats = [], {}, []
        
        with st.status(f"جاري محاكاة {len(bt_symbols)} رموز...", expanded=True) as status:
            for i, sym in enumerate(bt_symbols):
                st.write(f"⏳ **جاري معالجة {sym}** (خطوة {i+1}/{len(bt_symbols)})...")
                df, trades, error_msg, stats = _cached_backtest(fix_symbol(sym), interval, sd, ed, period, bt_data_source)
                
                if error_msg:
                    st.error(f"❌ **{sym}:** {error_msg}")
                    continue 
                    
                if df is not None:
                    dfs[sym] = df
                    if stats: stats["symbol"] = sym; all_stats.append(stats)
                    
                    if trades:
                        tdf = pd.DataFrame(trades)
                        results.append({"symbol": sym, "trades_df": tdf, "total": len(tdf)})
                        st.success(f"✅ تم العثور على {len(tdf)} نموذج لـ {sym}.")
                    else:
                        st.warning(f"⚠️ **{sym}:** لم يتم العثور على أي نماذج H&S في هذه الفترة.")
            
            if results:
                status.update(label=f"✅ اكتملت المحاكاة. تم العثور على نماذج في {len(results)} أصول.", state="complete", expanded=False)
            else:
                status.update(label="⚠️ اكتملت المحاكاة. لم يتم العثور على أي نماذج.", state="error", expanded=True)

        st.session_state["bt_results"] = results
        st.session_state["bt_dfs"] = dfs
        st.session_state["bt_stats"] = all_stats
        st.session_state["bt_sd"], st.session_state["bt_ed"], st.session_state["bt_period"], st.session_state["bt_int"] = sd, ed, period, interval

    if "bt_results" in st.session_state and st.session_state["bt_results"]:
        rl = st.session_state["bt_results"]
        all_stats = st.session_state.get("bt_stats", [])
        all_dfs = [r["trades_df"] for r in rl if not r["trades_df"].empty]
        
        if all_dfs:
            tab1, tab2, tab3, tab4 = st.tabs(["📉 الرسوم البيانية", "📋 جدول كل الإشارات", "🧠 التشخيص الذكي", "🧮 الحاسبات التفاعلية"])
            
            with tab4:
                st.subheader("🧮 الحاسبات التفاعلية وإدارة المخاطر")
                
                st.markdown("#### 1️⃣ الإعدادات العامة للحساب")
                c1, c2 = st.columns(2)
                capital = c1.number_input("رأس المال الكلي ($):", min_value=10.0, value=1000.0, step=100.0, key="calc_capital")
                risk_per_trade_pct = c2.slider("نسبة المخاطرة لكل صفقة (%):", min_value=1, max_value=10, value=2, key="calc_risk_pct")
                
                max_risk_usd = capital * (risk_per_trade_pct / 100)
                st.info(f"💰 أقصى خسارة مسموحة لكل صفقة: **${max_risk_usd:.2f}**")
                
                st.markdown("---")
                st.markdown("#### 2️⃣ حاسبة الإشارة الحالية والنتائج الكلية")
                
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                sel_idx_calc = st.selectbox("اختر الأصل للتحليل:", opts, key="calc_sel_sym")
                ai_calc = rl[opts.index(sel_idx_calc)]
                sym_calc, tdf_calc = ai_calc["symbol"], ai_calc["trades_df"]
                
                if not tdf_calc.empty:
                    tdf_calc = compute_dollar_pnl(compute_pips(tdf_calc), capital=capital, risk_pct=risk_per_trade_pct)
                    
                    sig_options = [f"إشارة {i+1} | اتجاه: {'بيع 🔴' if 'Bear' in str(tdf_calc.iloc[i].get('Bias', '')) else 'شراء 🟢'}" for i in range(len(tdf_calc))]
                    selected_sig_str = st.selectbox("اختر الإشارة لعرض تفاصيلها:", sig_options, index=len(tdf_calc)-1, key="calc_sig_idx")
                    sig_idx = sig_options.index(selected_sig_str)
                    
                    cur_calc = tdf_calc.iloc[sig_idx]
                    e_val = float(cur_calc.get("Entry", 0))
                    s_val = float(cur_calc.get("SL", 0))
                    t_val = float(cur_calc.get("TP", 0))
                    is_bear = "Bear" in str(cur_calc.get("Bias", ""))
                    
                    if e_val > 0:
                        risk_pts = abs(e_val - s_val)
                        reward_pts = abs(t_val - e_val)
                        risk_pct = (risk_pts / e_val) * 100
                        reward_pct = (reward_pts / e_val) * 100
                        rr = reward_pct / risk_pct if risk_pct > 0 else 0
                        
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("سعر الدخول", f"{e_val:.5f}", "بيع" if is_bear else "شراء", delta_color="inverse" if is_bear else "normal")
                        col2.metric("وقف الخسارة (SL)", f"{s_val:.5f}", f"-{risk_pct:.2f}%", delta_color="inverse")
                        col3.metric("الهدف (TP)", f"{t_val:.5f}", f"+{reward_pct:.2f}%", delta_color="normal")
                        col4.metric("نسبة المخاطرة/الربح", f"1 : {rr:.2f}")
                        
                        st.markdown("##### 📊 ملخص جميع إشارات هذا الأصل بالدولار:")
                        wins = tdf_calc[tdf_calc["trade_result"] == "WIN"]
                        losses = tdf_calc[tdf_calc["trade_result"] == "LOSS"]
                        
                        total_profit_usd = wins["PnL_USD"].sum() if "PnL_USD" in wins else 0
                        total_loss_usd = losses["PnL_USD"].sum() if "PnL_USD" in losses else 0
                        net_pnl = total_profit_usd + total_loss_usd
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("إجمالي الأرباح", f"+${total_profit_usd:.2f}", f"{len(wins)} صفقة", delta_color="normal")
                        c2.metric("إجمالي الخسائر", f"${total_loss_usd:.2f}", f"{len(losses)} صفقة", delta_color="inverse")
                        c3.metric("صافي الربح/الخسارة", f"${net_pnl:.2f}", delta_color="normal" if net_pnl > 0 else "inverse")
                        c4.metric("نسبة النجاح", f"{(len(wins)/len(tdf_calc)*100):.1f}%" if len(tdf_calc)>0 else "0%")

            with tab2:
                st.subheader("📋 قائمة بجميع الإشارات التي تم العثور عليها")
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                sel_idx = st.selectbox("اختر الأصل لعرض إشاراته:", opts, key="table_sel")
                ai = rl[opts.index(sel_idx)]
                sym, tdf = ai["symbol"], ai["trades_df"]
                
                if not tdf.empty:
                    tdf_pips = compute_pips(tdf)
                    tdf_pips = compute_dollar_pnl(tdf_pips, capital=1000.0, risk_pct=2.0)
                    display_cols = ["Pattern", "Bias", "Entry", "SL", "TP", "Exit Index", "Exit Price", "trade_result", "Pips", "PnL_USD"]
                    available_cols = [c for c in display_cols if c in tdf_pips.columns]
                    st.dataframe(tdf_pips[available_cols], use_container_width=True, height=600)

            with tab3:
                st.subheader("📊 تحليل النتائج وخطة التطوير الذاتي")
                combined_df = pd.concat(all_dfs, ignore_index=True)
                combined_df = compute_dollar_pnl(compute_pips(combined_df), capital=1000.0, risk_pct=2.0) 
                
                closed = combined_df[combined_df["trade_result"].isin(["WIN", "LOSS"])]
                wins = len(closed[closed["trade_result"] == "WIN"])
                losses = len(closed[closed["trade_result"] == "LOSS"])
                wr = round((wins / len(closed) * 100), 1) if len(closed) > 0 else 0
                
                total_profit_all = closed[closed["trade_result"] == "WIN"]["PnL_USD"].sum()
                total_loss_all = closed[closed["trade_result"] == "LOSS"]["PnL_USD"].sum()
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("إجمالي المغلقة", len(closed))
                c2.metric("الرابحة", wins, f"{wr}%")
                c3.metric("إجمالي الأرباح الكلية", f"+${total_profit_all:.2f}", delta_color="normal")
                c4.metric("إجمالي الخسائر الكلية", f"${total_loss_all:.2f}", delta_color="inverse")

            with tab1:
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                ai = rl[opts.index(st.selectbox("اختر الأصل:", opts, key="chart_sel"))]
                sym, tdf = ai["symbol"], ai["trades_df"]
                
                if not tdf.empty:
                    chart_mode_label = st.radio("نطاق الرسم:", ["📉 الرسم المتكيف (سريع جداً)", "🗺️ كامل الفترة (قد يكون بطيئاً)"], horizontal=True)
                    chart_mode = "adaptive" if "المتكيف" in chart_mode_label else "full"
                    
                    si = st.session_state.get(f"signal_index_{sym}", len(tdf)-1)
                    if si >= len(tdf) or si < 0:
                        si = len(tdf) - 1
                        st.session_state[f"signal_index_{sym}"] = si

                    n1, n2, n3 = st.columns([1, 2, 1])
                    with n1:
                        if st.button("⬅️ السابق", use_container_width=True, key="bt_prev_top"): st.session_state[f"signal_index_{sym}"] = max(0, si - 1); st.rerun()
                    with n2:
                        st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>إشارة {si+1} من {len(tdf)}</div>", unsafe_allow_html=True)
                    with n3:
                        if st.button("التالي ➡️", use_container_width=True, key="bt_next_top"): st.session_state[f"signal_index_{sym}"] = min(len(tdf)-1, si + 1); st.rerun()
                            
                    cur = tdf.iloc[si]
                    
                    df_chart = _prepare_chart_data(fix_symbol(sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"], st.session_state["bt_period"], bt_data_source)
                    render_chart_fast(sym, cur, df_chart, chart_mode)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    n4, n5, n6 = st.columns([1, 2, 1])
                    with n4:
                        if st.button("⬅️ السابق", key="bt_prev_bottom", use_container_width=True): st.session_state[f"signal_index_{sym}"] = max(0, si - 1); st.rerun()
                    with n6:
                        if st.button("التالي ➡️", key="bt_next_bottom", use_container_width=True): st.session_state[f"signal_index_{sym}"] = min(len(tdf)-1, si + 1); st.rerun()

# ================= LIVE SCAN MODE =================
else:
    st.markdown("### 🚀 الماسح الحي")
    
    live_data_source = st.radio(
        "📡 مصدر البيانات:",
        ["📁 البيانات المحفوظة (GitHub - سريع جداً)", "🌐 جلب مباشر من الإنترنت (API - قد يكون بطيئاً)", "🌐 Yahoo Finance (بديل)"],
        horizontal=True
    )

    live_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True, key="live_mode_radio")
    if live_mode == "سهم فردي":
        symbols = [st.text_input("رمز:", value="BTC-USD", key="live_sym_input")]
    else:
        c1, c2 = st.columns(2)
        if c1.button("✅ تحديد كل العملات (من الشيت والافتراضية)", use_container_width=True, key="live_sel_all"):
            st.session_state["live_selected_symbols"] = all_symbols; st.rerun()
        if c2.button("❌ إلغاء التحديد", use_container_width=True, key="live_clr_all"):
            st.session_state["live_selected_symbols"] = []; st.rerun()
        if "live_selected_symbols" not in st.session_state: st.session_state["live_selected_symbols"] = ["BTC-USD"]
        symbols = st.multiselect("اختر العملات:", all_symbols, key="live_selected_symbols")

    interval = st.selectbox("الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=ALL_GLOBAL_INTERVALS.index("1h"))
    period = st.selectbox("الفترة:", ALL_PERIODS, index=ALL_PERIODS.index("3mo"))
    
    if st.button("🚀 بدء المسح", use_container_width=True) and symbols:
        valid = []
        for sym in symbols:
            df, res = _cached_live(fix_symbol(sym), interval, period, live_data_source)
            if res and res.get("signal") in ("STRONG BUY", "STRONG SELL"):
                valid.append({"symbol": sym, "result": res})
        if valid:
            st.success(f"تم العثور على {len(valid)} إشارة")
            
            si = st.session_state.get("live_signal_index", 0)
            if si >= len(valid) or si < 0:
                si = 0
                st.session_state["live_signal_index"] = si
                
            n1, n2, n3 = st.columns([1, 2, 1])
            with n1:
                if st.button("⬅️ السابق", use_container_width=True, key="live_prev_top"): st.session_state["live_signal_index"] = max(0, si - 1); st.rerun()
            with n2:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>إشارة {si+1} من {len(valid)}</div>", unsafe_allow_html=True)
            with n3:
                if st.button("التالي ➡️", use_container_width=True, key="live_next_top"): st.session_state["live_signal_index"] = min(len(valid)-1, si + 1); st.rerun()

            ar, sym = valid[si]["result"], valid[si]["symbol"]
            st.write(f"**{sym}** - {ar['signal']}")
            df_chart = _prepare_chart_data(fix_symbol(sym), interval, None, None, period, live_data_source)
            if df_chart is not None: render_chart_fast(sym, ar, df_chart, "adaptive")
            
            st.markdown("<br>", unsafe_allow_html=True)
            n4, n5, n6 = st.columns([1, 2, 1])
            with n4:
                if st.button("⬅️ السابق", key="live_prev_bottom", use_container_width=True): st.session_state["live_signal_index"] = max(0, si - 1); st.rerun()
            with n6:
                if st.button("التالي ➡️", key="live_next_bottom", use_container_width=True): st.session_state["live_signal_index"] = min(len(valid)-1, si + 1); st.rerun()
