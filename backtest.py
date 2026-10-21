# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import yfinance as yf
from data_provider import fetch_data, get_github_repo

# ⬇️ استيراد المحرك ⬇️
try:
    from engine import run_full_analysis, backtest_strategy, REASON_MAP, diagnose_no_signals, diagnose_filters
except ImportError:
    st.error("تأكد من وجود ملف engine.py")
    st.stop()

# ⬇️ استيراد دالة جلب العملات من الشيت ⬇️
try:
    from ffff import get_symbols_from_sheet
    SHEET_ENABLED = True
except ImportError:
    SHEET_ENABLED = False
    def get_symbols_from_sheet(*args, **kwargs): return []

st.set_page_config(page_title="Box Hunter Pro - Smart", page_icon="📦", layout="wide")

# ⬇️⬇️ تحديثات CSS للتوسيع والتباعد (واجهة أوسع وأطول) ⬇️⬇️
st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    
    .main .block-container { 
        max-width: 98% !important; 
        padding: 1.5rem 2.5rem !important; 
    }
    
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 16px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; margin-bottom: 1rem; }
    label, .stRadio label, .stTextInput label, .stSelectbox label, .stMultiSelect label { direction: rtl; text-align: right; margin-bottom: 0.5rem; }
    
    .stButton > button { 
        direction: rtl; 
        text-align: center; 
        padding: 0.6rem 1rem;
        font-size: 1rem;
    }
    
    .stAlert, .stInfo, .stSuccess, .stWarning, .stError { direction: rtl; text-align: right; padding: 1rem; }
    .stDataFrame { direction: ltr; }
    
    div[data-testid="stHorizontalBlock"] { gap: 1.5rem; }
    div[data-testid="stVerticalBlock"] { gap: 1rem; }
    
    .js-plotly-plot .plotly, .js-plotly-plot .main-svg { touch-action: none !important; }
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
ALL_GLOBAL_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALL_PERIODS = ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]

IC_MARKETS_SPECS = {"BTC-USD": {"pip": 1.0}, "EURUSD": {"pip": 0.0001}, "GBPUSD": {"pip": 0.0001}}
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
    return 0.0001

def get_available_symbols():
    s = set(IC_MARKETS_SPECS.keys())
    sheet_count = 0
    if SHEET_ENABLED:
        try:
            sheet_symbols = get_symbols_from_sheet(SHEET_ID, "GOLD", "TOKENS")
            if sheet_symbols and isinstance(sheet_symbols, list) and len(sheet_symbols) > 0:
                for x in sheet_symbols[0]: s.add(str(x).strip().upper())
                sheet_count = len(sheet_symbols[0])
        except Exception: pass
    return sorted(s), sheet_count

# ⬇️⬇️ دالة الجلب الذكية (التي تسمح بالاختيار بين المصادر) ⬇️⬇️
@st.cache_data(ttl=3600, show_spinner=False)
def _cached_smart_fetch(symbol, interval, source_choice, start_date=None, end_date=None, period=None):
    df = None
    force_dl = True if "الإنترنت" in source_choice else False
    
    # الخيار 1: GitHub أو الإنترنت (Twelve Data)
    if "GitHub" in source_choice or "الإنترنت" in source_choice:
        try:
            if start_date and end_date: 
                df = fetch_data(symbol, interval=interval, start_date=start_date, end_date=end_date, force_download=force_dl)
            else: 
                df = fetch_data(symbol, interval=interval, period=period, force_download=force_dl)
        except Exception:
            df = None

    # الخيار 2: Yahoo Finance (إما بطلب من المستخدم أو كبديل تلقائي)
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
def _cached_backtest(symbol, interval, start_date, end_date, source_choice):
    df = _cached_smart_fetch(symbol, interval, source_choice, start_date=start_date, end_date=end_date)
    if df is None or df.empty: 
        return None, None, "فشل جلب البيانات أو لا توجد بيانات في هذه الفترة.", {}
    try: 
        trades, stats = backtest_strategy(df, interval=interval, symbol=symbol)
    except Exception as e: 
        return df, None, f"خطأ داخل محرك البحث (engine.py): {str(e)}", {}
    return df, trades, None, stats

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_live(symbol, interval, period, source_choice):
    df = _cached_smart_fetch(symbol, interval, source_choice, period=period)
    if df is None or df.empty: return None, None
    try: res = run_full_analysis(df, interval=interval, symbol=symbol)
    except Exception: return df, None
    return df, res

@st.cache_data(ttl=3600, show_spinner=False)
def _prepare_chart_data(symbol, interval, start_date, end_date, source_choice):
    df = _cached_smart_fetch(symbol, interval, source_choice, start_date=start_date, end_date=end_date)
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
        e, x = _f(row.get("Entry Price")), _f(row.get("Exit Price"))
        bias = str(row.get("bias") or "").upper()
        is_sell = "BEAR" in bias
        p = (e - x) / pip if (e and x and is_sell) else (x - e) / pip if (e and x) else None
        pips_l.append(round(p, 1) if p is not None else None)
    df["Pips"] = pips_l
    return df

def compute_dollar_pnl(df, lot=0.01):
    if df is None or df.empty: return df
    df = df.copy()
    usd = []
    for _, row in df.iterrows():
        sym = str(row.get("symbol") or "").upper()
        try: e, x = float(row.get("Entry Price")), float(row.get("Exit Price"))
        except: usd.append(None); continue
        move = (x - e) if "BEAR" not in str(row.get("bias")).upper() else (e - x)
        if "BTC" in sym: pnl = move * lot
        elif "XAU" in sym: pnl = move * lot * 100
        elif sym.endswith("USD"): pnl = move * lot * 100000
        else: pnl = move * lot * 100000 / x if x else None
        usd.append(round(pnl, 2) if pnl is not None else None)
    df["PnL_USD"] = usd
    return df

def draw_box_pattern(fig, source):
    if source is None: return
    nodes = source.get("nodes", [])
    box_nodes = source.get("neckline_nodes", [])
    if len(nodes) < 3 or len(box_nodes) < 4: return

    fig.add_trace(go.Scatter(x=[nodes[0][0], nodes[1][0]], y=[nodes[0][1], nodes[1][1]], mode="lines", name="Trend", line=dict(color="#FF9800", width=2, dash="dot")), row=1, col=1)
    top_x, top_y = [box_nodes[0][0], box_nodes[1][0]], [box_nodes[0][1], box_nodes[1][1]]
    bot_x, bot_y = [box_nodes[2][0], box_nodes[3][0]], [box_nodes[2][1], box_nodes[3][1]]
    
    fig.add_trace(go.Scatter(x=top_x, y=top_y, mode="lines", name="Resistance", line=dict(color="#2196F3", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=bot_x, y=bot_y, mode="lines", name="Support", line=dict(color="#2196F3", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=[top_x[0], bot_x[0]], y=[top_y[0], bot_y[0]], mode="lines", line=dict(color="#B0BEC5", width=1), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[top_x[1], bot_x[1]], y=[top_y[1], bot_y[1]], mode="lines", line=dict(color="#B0BEC5", width=1), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[nodes[2][0]], y=[nodes[2][1]], mode="markers+text", name="Breakout", marker=dict(size=14, color="#E91E63", symbol="star"), text=["كسر"], textposition="top center"), row=1, col=1)

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
    
    draw_box_pattern(fig, cur)
    
    if "Volume" in df_window.columns:
        fig.add_trace(go.Bar(x=df_window.index, y=df_window["Volume"], name="Volume", marker_color='rgba(158, 158, 158, 0.5)'), row=2, col=1)
    
    fig.update_layout(
        template="plotly_white", height=750, autosize=True, xaxis_rangeslider_visible=False, 
        dragmode="pan", hovermode="x unified", margin=dict(l=10, r=60, t=40, b=40), 
        yaxis=dict(side="right", showgrid=True, gridcolor="#EEEEEE", fixedrange=False, automargin=True),
        yaxis2=dict(side="right", showgrid=False, fixedrange=False, automargin=True),
        xaxis=dict(showgrid=True, gridcolor="#F5F5F5", range=[x_min, x_max], fixedrange=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

all_symbols, sheet_count = get_available_symbols()

# ⬇️⬇️ قسم إدارة البيانات (GitHub) ⬇️⬇️
with st.expander("⚙️ إدارة البيانات (GitHub) - اضغط للفتح", expanded=False):
    repo = get_github_repo()
    if repo:
        st.success(f"✅ متصل بـ: {repo.full_name}")
        
        if sheet_count > 0:
            st.info(f"📊 تم جلب **{sheet_count}** عملة من الشيت + العملات الافتراضية. الإجمالي: **{len(all_symbols)}** عملة.")
        else:
            st.warning("⚠️ تعذر جلب العملات من الشيت (قد يكون ملف `ffff.py` مفقوداً).")
        
        dl_mode = st.radio("طريقة التنزيل:", ["الكل (شيت)", "مجموعة محددة", "عملة واحدة"], horizontal=True, key="dl_mode")
        intvs_to_dl = st.multiselect("اختر الأطُر الزمنية للتنزيل:", ["1h", "4h", "1d"], default=["1h", "4h"], key="dl_intvs")
        
        if dl_mode == "الكل (شيت)":
            st.info(f"سيتم تنزيل **جميع** العملات ({len(all_symbols)} عملة).")
            if st.button("📥 تنزيل وحفظ الكل", use_container_width=True):
                with st.status("جاري تحديث البيانات وحفظها...", expanded=True) as status:
                    for i, sym in enumerate(all_symbols):
                        st.write(f"[{i+1}/{len(all_symbols)}] تحديث {sym}...")
                        for intv in intvs_to_dl:
                            _cached_smart_fetch(fix_symbol(sym), intv, "الإنترنت", start_date="2020-01-01", end_date=datetime.datetime.now().strftime("%Y-%m-%d"))
                    st.cache_data.clear()
                    status.update(label="✅ تم التحديث والحفظ!", state="complete", expanded=False)
                    
        elif dl_mode == "مجموعة محددة":
            selected_syms = st.multiselect("اختر العملات المراد تنزيلها:", all_symbols, default=all_symbols[:5], key="dl_selected_syms")
            if st.button("📥 تنزيل وحفظ المحدد", use_container_width=True) and selected_syms:
                with st.status(f"جاري تحديث {len(selected_syms)} عملات...", expanded=True) as status:
                    for i, sym in enumerate(selected_syms):
                        st.write(f"[{i+1}/{len(selected_syms)}] تحديث {sym}...")
                        for intv in intvs_to_dl:
                            _cached_smart_fetch(fix_symbol(sym), intv, "الإنترنت", start_date="2020-01-01", end_date=datetime.datetime.now().strftime("%Y-%m-%d"))
                    st.cache_data.clear()
                    status.update(label="✅ تم التحديث والحفظ!", state="complete", expanded=False)
                    
        elif dl_mode == "عملة واحدة":
            single_sym = st.text_input("أدخل رمز العملة (مثال: XAUUSD أو EURUSD):", value="BTC-USD", key="single_dl_sym")
            if st.button("📥 تنزيل وحفظ العملة", use_container_width=True) and single_sym:
                with st.status(f"جاري تحديث {single_sym}...", expanded=True) as status:
                    for intv in intvs_to_dl:
                        st.write(f"تحديث {single_sym} للإطار {intv}...")
                        _cached_smart_fetch(fix_symbol(single_sym), intv, "الإنترنت", start_date="2020-01-01", end_date=datetime.datetime.now().strftime("%Y-%m-%d"))
                    st.cache_data.clear()
                    status.update(label=f"✅ تم تحديث {single_sym}!", state="complete", expanded=False)
    else:
        st.warning("⚠️ لم يتم ربط GitHub. يرجى إضافة التوكن في الإعدادات.")

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي", "🧪 مختبر الاختبار الرجعي"], horizontal=True)

# ================= BACKTEST MODE =================
if app_mode == "🧪 مختبر الاختبار الرجعي":
    st.markdown("### 🧪 مختبر الصناديق")
    
    # ⬇️ إعادة خيارات مصدر البيانات ⬇️
    bt_data_source = st.radio(
        "📁 مصدر البيانات للمحاكاة:",
        ["📁 البيانات المحفوظة (GitHub - سريع جداً)", "🌐 جلب مباشر من الإنترنت (API - قد يكون بطيئاً)", "🌐 Yahoo Finance (بديل)"],
        horizontal=True,
        help="اختر 'البيانات المحفوظة' لاستخدام الملفات التي قمت بتحميلها مسبقاً دون استهلاك الـ API."
    )

    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True)
    if bt_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="BTC-USD")]
    else:
        c1, c2 = st.columns(2)
        if c1.button("✅ تحديد كل العملات", use_container_width=True):
            st.session_state["bt_selected_symbols"] = all_symbols; st.rerun()
        if c2.button("❌ إلغاء التحديد", use_container_width=True):
            st.session_state["bt_selected_symbols"] = []; st.rerun()
        if "bt_selected_symbols" not in st.session_state: st.session_state["bt_selected_symbols"] = ["BTC-USD"]
        bt_symbols = st.multiselect("اختر:", all_symbols, key="bt_selected_symbols")

    now = datetime.datetime.now()
    c1, c2, c3 = st.columns(3)
    sd = c1.date_input("من:", value=datetime.date(now.year-1, 1, 1)).strftime("%Y-%m-%d")
    ed = c2.date_input("إلى:", value=datetime.date.today()).strftime("%Y-%m-%d")
    interval = c3.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)

    if st.button("📊 بدء المحاكاة", use_container_width=True) and bt_symbols:
        results, dfs, all_stats = [], {}, []
        
        with st.status(f"جاري محاكاة {len(bt_symbols)} رموز...", expanded=True) as status:
            for i, sym in enumerate(bt_symbols):
                st.write(f"⏳ **جاري معالجة {sym}** (خطوة {i+1}/{len(bt_symbols)})...")
                df, trades, error_msg, stats = _cached_backtest(fix_symbol(sym), interval, sd, ed, bt_data_source)
                
                if error_msg:
                    st.error(f"❌ **{sym}:** {error_msg}")
                    continue 
                    
                if df is not None:
                    dfs[sym] = df
                    if stats: stats["symbol"] = sym; all_stats.append(stats)
                    
                    if trades:
                        tdf = pd.DataFrame(trades)
                        results.append({"symbol": sym, "trades_df": tdf, "total": len(tdf)})
                        st.success(f"✅ تم العثور على {len(tdf)} صفقة لـ {sym}.")
                    else:
                        st.warning(f"⚠️ **{sym}:** لم يتم العثور على أي نماذج تتطابق مع شروط 'الصناديق' في هذه الفترة.")
            
            if results:
                status.update(label=f"✅ اكتملت المحاكاة. تم العثور على صفقات في {len(results)} أصول.", state="complete", expanded=False)
            else:
                status.update(label="⚠️ اكتملت المحاكاة. لم يتم العثور على أي صفقات.", state="error", expanded=True)

        st.session_state["bt_results"] = results
        st.session_state["bt_dfs"] = dfs
        st.session_state["bt_stats"] = all_stats
        st.session_state["bt_sd"], st.session_state["bt_ed"], st.session_state["bt_int"] = sd, ed, interval

    if "bt_results" in st.session_state and st.session_state["bt_results"]:
        rl = st.session_state["bt_results"]
        all_stats = st.session_state.get("bt_stats", [])
        all_dfs = [r["trades_df"] for r in rl if not r["trades_df"].empty]
        
        if all_dfs:
            tab1, tab2, tab3, tab4 = st.tabs(["📉 الرسوم البيانية", "📋 جدول كل الإشارات", "🧠 التشخيص الذكي", "🛡️ تقرير الفلاتر"])
            
            with tab2:
                st.subheader("📋 قائمة بجميع الإشارات التي تم العثور عليها")
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                sel_idx = st.selectbox("اختر الأصل لعرض إشاراته:", opts, key="table_sel")
                ai = rl[opts.index(sel_idx)]
                sym, tdf = ai["symbol"], ai["trades_df"]
                
                if not tdf.empty:
                    tdf_pips = compute_pips(tdf)
                    tdf_pips = compute_dollar_pnl(tdf_pips, lot=0.01)
                    display_cols = ["Entry Date", "Exit Date", "bias", "Entry Price", "Stop Loss", "Take Profit", "Result", "Pips", "PnL_USD"]
                    available_cols = [c for c in display_cols if c in tdf_pips.columns]
                    st.dataframe(tdf_pips[available_cols], use_container_width=True, height=600)

            with tab3:
                st.subheader("📊 تحليل النتائج وخطة التطوير الذاتي")
                combined_df = pd.concat(all_dfs, ignore_index=True)
                closed = combined_df[combined_df["Result"].isin(["WIN", "LOSS"])]
                wins = len(closed[closed["Result"] == "WIN"])
                losses = len(closed[closed["Result"] == "LOSS"])
                wr = round((wins / len(closed) * 100), 1) if len(closed) > 0 else 0
                
                c1, c2, c3 = st.columns(3)
                c1.metric("إجمالي المغلقة", len(closed))
                c2.metric("الرابحة", wins, f"{wr}%")
                c3.metric("الخاسرة", losses, f"{100-wr}%", delta_color="inverse")
                
                if losses > 0:
                    st.markdown("### 🔍 تحليل الخسائر وخطة التطوير")
                    loss_counts = closed[closed["Result"] == "LOSS"]["Loss Category"].value_counts()
                    for cat, count in loss_counts.items():
                        cat_ar = REASON_MAP.get(cat, {}).get("reason", cat)
                        st.write(f"- **{cat_ar}**: {count} صفقة ({round(count/losses*100, 1)}%)")
            
            with tab4:
                st.subheader("🛡️ تقرير الفلاتر (Filter Diagnostics)")
                st.markdown("هذا التقرير يوضح لك عدد النماذج التي تم اكتشافها وعدد التي تم رفضها بسبب الفلاتر.")
                
                if all_stats:
                    for st_item in all_stats:
                        sym = st_item["symbol"]
                        raw = st_item.get("raw_breakouts", 0)
                        rej_retest = st_item.get("rejected_retest", 0)
                        rej_sr = st_item.get("rejected_sr", 0)
                        rej_rsi = st_item.get("rejected_rsi", 0)
                        accepted = raw - rej_retest - rej_sr - rej_rsi
                        
                        st.markdown(f"#### {sym}")
                        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                        sc1.metric("كسرات خام (Raw)", raw)
                        sc2.metric("مرفوضة (RSI)", rej_rsi)
                        sc3.metric("مرفوضة (إعادة اختبار)", rej_retest)
                        sc4.metric("مرفوضة (دعوم/مقاومات)", rej_sr)
                        sc5.metric("مقبولة (ناجحة)", accepted)
                        st.markdown("---")

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
                    st.write(cur.get("Trade Recommendation", ""))
                    df_chart = _prepare_chart_data(fix_symbol(sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"], bt_data_source)
                    render_chart_fast(sym, cur, df_chart, chart_mode)
                    
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    n4, n5, n6 = st.columns([1, 2, 1])
                    with n4:
                        if st.button("⬅️ السابق", key="bt_prev_bottom", use_container_width=True): st.session_state[f"signal_index_{sym}"] = max(0, si - 1); st.rerun()
                    with n6:
                        if st.button("التالي ➡️", key="bt_next_bottom", use_container_width=True): st.session_state[f"signal_index_{sym}"] = min(len(tdf)-1, si + 1); st.rerun()

# ================= LIVE SCAN MODE =================
else:
    st.markdown("### 🚀 الماسح الحي")
    
    # ⬇️ إعادة خيارات مصدر البيانات ⬇️
    live_data_source = st.radio(
        "📡 مصدر البيانات:",
        ["📁 البيانات المحفوظة (GitHub - سريع جداً)", "🌐 جلب مباشر من الإنترنت (API - قد يكون بطيئاً)", "🌐 Yahoo Finance (بديل)"],
        horizontal=True,
        help="اختر 'البيانات المحفوظة' لاستخدام الملفات التي قمت بتحميلها مسبقاً دون استهلاك الـ API."
    )

    live_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True, key="live_mode_radio")
    if live_mode == "سهم فردي":
        symbols = [st.text_input("رمز:", value="BTC-USD", key="live_sym_input")]
    else:
        c1, c2 = st.columns(2)
        if c1.button("✅ تحديد كل العملات", use_container_width=True, key="live_sel_all"):
            st.session_state["live_selected_symbols"] = all_symbols; st.rerun()
        if c2.button("❌ إلغاء التحديد", use_container_width=True, key="live_clr_all"):
            st.session_state["live_selected_symbols"] = []; st.rerun()
        if "live_selected_symbols" not in st.session_state: st.session_state["live_selected_symbols"] = ["BTC-USD"]
        symbols = st.multiselect("اختر العملات:", all_symbols, key="live_selected_symbols")

    interval = st.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    period = st.selectbox("النطاق:", ALL_PERIODS, index=2)
    
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
            df_chart = _prepare_chart_data(fix_symbol(sym), interval, None, None, live_data_source)
            if df_chart is not None: render_chart_fast(sym, ar, df_chart, "adaptive")
            
            st.markdown("<br><br>", unsafe_allow_html=True)
            n4, n5, n6 = st.columns([1, 2, 1])
            with n4:
                if st.button("⬅️ السابق", key="live_prev_bottom", use_container_width=True): st.session_state["live_signal_index"] = max(0, si - 1); st.rerun()
            with n6:
                if st.button("التالي ➡️", key="live_next_bottom", use_container_width=True): st.session_state["live_signal_index"] = min(len(valid)-1, si + 1); st.rerun()
