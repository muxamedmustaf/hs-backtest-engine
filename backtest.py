# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from data_provider import fetch_data

try:
    from engine import run_full_analysis, backtest_strategy, REASON_MAP, diagnose_no_signals, diagnose_filters
except ImportError as e:
    st.error(f"❌ فشل الاستيراد من engine: {e}"); st.stop()

# محاولة استيراد دالة الشيت
try:
    from ffff import get_symbols_from_sheet
    HAS_SHEET = True
except ImportError:
    HAS_SHEET = False
    def get_symbols_from_sheet(*args, **kwargs): return [["EURUSD=X", "BTC-USD"]]

st.set_page_config(page_title="Box Hunter Pro", page_icon="📦", layout="wide")

st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    .main .block-container { max-width: 100% !important; padding: 0.5rem 1rem !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 15px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    label, .stRadio label, .stTextInput label, .stSelectbox label { direction: rtl; text-align: right; }
    .js-plotly-plot .plotly, .js-plotly-plot .plotly .main-svg { touch-action: none !important; } 
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
ALL_GLOBAL_INTERVALS = ["15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1wk"]

IC_MARKETS_SPECS = {
    "BTC-USD":  {"contract": 1, "min_lot": 0.01, "step": 0.01, "pip": 1.0, "cat": "🪙 Crypto"},
    "EURUSD":   {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
    "GBPUSD":   {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "💵 Major"},
}

PLOTLY_CONFIG = {
    'responsive': True, 'scrollZoom': True, 'displaylogo': False, 'displayModeBar': True, 
    'dragmode': 'pan', 'doubleClick': 'reset+autosize'
}

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

# 🎯 الدالة الاحترافية الجديدة لجلب الرموز (تكشف الأخطاء ولا تخفيها)
def get_available_symbols():
    s = set(IC_MARKETS_SPECS.keys())
    
    if not HAS_SHEET:
        st.warning("⚠️ **تنبيه:** لم يتم العثور على ملف `ffff.py`، يتم عرض الرموز الافتراضية فقط.")
        return sorted(s)

    try:
        # استدعاء الدالة
        raw_data = get_symbols_from_sheet(SHEET_ID, "GOLD", "TOKENS")
        
        fetched_symbols = []
        
        # 1. إذا كانت النتيجة Pandas DataFrame
        if isinstance(raw_data, pd.DataFrame):
            if not raw_data.empty:
                # نفترض أن العمود الأول يحتوي على الرموز
                fetched_symbols = raw_data.iloc[:, 0].dropna().astype(str).tolist()
                
        # 2. إذا كانت النتيجة List of Lists (القوائم المتداخلة)
        elif isinstance(raw_data, (list, tuple)) and len(raw_data) > 0:
            first_item = raw_data[0]
            if isinstance(first_item, (list, tuple)):
                fetched_symbols = [str(x) for x in first_item if pd.notna(x)]
            elif isinstance(first_item, str):
                # إذا كانت قائمة مسطحة
                fetched_symbols = [str(x) for x in raw_data if pd.notna(x)]

        # إضافة الرموز التي تم جلبها
        for sym in fetched_symbols:
            sym_clean = sym.strip().upper()
            if sym_clean: 
                s.add(sym_clean)

        if len(fetched_symbols) > 0:
            st.sidebar.success(f"✅ تم جلب {len(fetched_symbols)} رمز من الشيت.")
        else:
            st.sidebar.warning("⚠️ تم الاتصال بالشيت ولكنه رجع فارغاً أو بصيغة غير معروفة.")

    except Exception as e:
        # هنا نطبع الخطأ للمستخدم بدلاً من تجاهله
        st.error(f"🚨 **خطأ أثناء قراءة الشيت:** {str(e)}")
        st.info("يتم استخدام القائمة الافتراضية كاحتياطي.")
        
    return sorted(s)

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch(symbol, interval, start_date=None, end_date=None, period=None):
    try:
        if start_date and end_date: return fetch_data(symbol, interval=interval, start_date=start_date, end_date=end_date, cache_hours=1)
        return fetch_data(symbol, interval=interval, period=period, cache_hours=1)
    except Exception: return None

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_backtest(symbol, interval, start_date, end_date):
    df = _cached_fetch(symbol, interval, start_date, end_date, None)
    if df is None or df.empty: return None, None
    try: trades = backtest_strategy(df, interval=interval, symbol=symbol)
    except Exception: return df, None
    return df, trades

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_live(symbol, interval, period):
    df = _cached_fetch(symbol, interval, None, None, period)
    if df is None or df.empty: return None, None
    try: res = run_full_analysis(df, interval=interval, symbol=symbol)
    except Exception: return df, None
    return df, res

@st.cache_data(ttl=3600, show_spinner=False)
def _prepare_chart_data(symbol, interval, start_date, end_date):
    df = _cached_fetch(symbol, interval, start_date, end_date, None)
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

def check_risk_limit(entry, sl, lot, symbol, capital, risk_pct):
    try: e = float(entry); s = float(sl); l = float(lot)
    except (TypeError, ValueError): return {"allowed": False, "risk_usd": None, "max_risk_usd": None, "risk_pct_actual": None, "message": "⚠️ بيانات ناقصة"}
    if e == 0: return {"allowed": False, "risk_usd": None, "max_risk_usd": None, "risk_pct_actual": None, "message": "⚠️ سعر غير صالح"}
    pm = abs(e - s)
    su = str(symbol).upper()
    if any(x in su for x in ("BTC", "ETH", "US30", "NAS", "SPX")): r = pm * l
    elif "XAU" in su or "GC=F" in su: r = pm * l * 100
    elif "XAG" in su or "SI=F" in su: r = pm * l * 5000
    elif su.endswith("USD"): r = pm * l * 100000
    else: r = pm * l * 100000 / e
    mx = capital * (risk_pct / 100)
    pct_a = (r / capital * 100) if capital > 0 else 0
    ok = r <= mx
    msg = (f"✅ مقبولة — المخاطرة {r:.2f}$ ({pct_a:.2f}%) ≤ الحد {mx:.2f}$" if ok else f"❌ مرفوضة — المخاطرة {r:.2f}$ ({pct_a:.2f}%) > الحد {mx:.2f}$")
    return {"allowed": ok, "risk_usd": round(r, 2), "max_risk_usd": round(mx, 2), "risk_pct_actual": round(pct_a, 2), "message": msg}

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

    entry, sl, tp, entry_x = source.get("entry"), source.get("sl"), source.get("tp"), nodes[2][0]
    if entry and sl: fig.add_annotation(x=entry_x, y=sl, text="SL", showarrow=True, arrowhead=1, ax=20, ay=20, font=dict(color="red"), row=1, col=1)
    if entry and tp: fig.add_annotation(x=entry_x, y=tp, text="TP", showarrow=True, arrowhead=1, ax=20, ay=-20, font=dict(color="green"), row=1, col=1)

def render_chart_fast(sym, cur, df_chart_full):
    if df_chart_full is None or df_chart_full.empty: return
    nodes = cur.get("nodes", [])
    if not nodes: return
    pattern_start, pattern_end = nodes[0][0], nodes[-1][0]
    span = pattern_end - pattern_start
    
    x_min, x_max = pattern_start - span * 2.5, pattern_end + span * 2.5
    
    try:
        idx_min = max(0, df_chart_full.index.searchsorted(x_min))
        idx_max = min(len(df_chart_full), df_chart_full.index.searchsorted(x_max))
        df_window = df_chart_full.iloc[idx_min:idx_max]
    except: df_window = df_chart_full
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
    
    fig.add_trace(go.Candlestick(x=df_window.index, open=df_window["Open"], high=df_window["High"], low=df_window["Low"], close=df_window["Close"], name="Price"), row=1, col=1)
    
    if "EMA50" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA50"], line=dict(color="orange", width=1), name="EMA 50"), row=1, col=1)
    if "EMA200" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA200"], line=dict(color="blue", width=1), name="EMA 200"), row=1, col=1)
    
    draw_box_pattern(fig, cur)
    
    if "Volume" in df_window.columns:
        fig.add_trace(go.Bar(x=df_window.index, y=df_window["Volume"], name="Volume", marker_color='rgba(158, 158, 158, 0.5)'), row=2, col=1)
    
    fig.update_layout(
        template="plotly_white", height=750, autosize=True, xaxis_rangeslider_visible=False, 
        dragmode="pan", hovermode="x unified", margin=dict(l=10, r=60, t=30, b=30), 
        yaxis=dict(side="right", showgrid=True, gridcolor="#EEEEEE", fixedrange=False, automargin=True),
        yaxis2=dict(side="right", showgrid=False, fixedrange=False, automargin=True),
        xaxis=dict(showgrid=True, gridcolor="#F5F5F5", range=[x_min, x_max], fixedrange=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

def render_financial_report(df, lot_size, symbol, period, raw_df=None, interval="1h"):
    st.markdown("### 📊 التقرير المالي الكامل")
    if df is None or df.empty: st.info("ℹ️ لا توجد صفقات"); return

    df = compute_pips(df); df = compute_dollar_pnl(df, lot=lot_size)
    rc = next((c for c in ["Result", "Head Result"] if c in df.columns), None)
    if rc is None: st.warning("⚠️ لا عمود نتيجة"); return

    s = df[rc].astype(str).str.upper()
    w_df, l_df = df[s.str.contains("WIN")], df[s.str.contains("LOSS")]
    o_df, b_df = df[s.str.contains("OPEN")], df[s.str.contains("BREAKEVEN")]

    w, l, o, b = len(w_df), len(l_df), len(o_df), len(b_df)
    total = len(df); closed = w + l
    wr = round(w / closed * 100, 1) if closed else 0

    wp = w_df["Pips"].dropna().sum() if not w_df.empty else 0
    lp = l_df["Pips"].dropna().sum() if not l_df.empty else 0
    wu = w_df["PnL_USD"].dropna().sum() if not w_df.empty else 0
    lu = l_df["PnL_USD"].dropna().sum() if not l_df.empty else 0
    net_p = wp + lp; net_u = wu + lu
    pf = round(abs(wu / lu), 2) if lu != 0 else float("inf")

    st.markdown(f"#### 📍 {symbol} · {period}")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 الصفقات", total); k2.metric("✅ ناجحة", w, delta=f"{wr}%")
    k3.metric("❌ خاسرة", l); k4.metric("⏳ مفتوحة", o)

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("📏 النقاط", f"{net_p:+.1f}"); k6.metric("💰 صافي الربح", f"${net_u:+.2f}")
    k7.metric("⚖️ Profit Factor", f"{pf:.2f}" if pf != float("inf") else "∞"); k8.metric("⚖️ تعادل", b)

    if wr >= 60 and pf >= 1.5: st.success("🌟 استراتيجية ممتازة")
    elif wr >= 50 and pf >= 1.2: st.success("✅ استراتيجية جيدة")
    elif wr >= 40 and pf >= 1.0: st.warning("🟡 استراتيجية مقبولة")
    else: st.error("🔴 استراتيجية ضعيفة")

    if l > 0:
        st.markdown("---")
        st.markdown("### 🔍 تحليل الخسائر (القاسم المشترك)")
        c1, c2, c3 = st.columns(3)
        if "Loss Category" in l_df.columns and not l_df["Loss Category"].dropna().empty:
            common_cat = l_df["Loss Category"].mode().iloc[0]
            reason_text = REASON_MAP.get(common_cat, {}).get("reason", common_cat) if REASON_MAP else common_cat
            c1.metric("🚩 السبب الأكثر شيوعاً", reason_text)
        else: c1.metric("🚩 السبب الأكثر شيوعاً", "غير محدد")
        c2.metric("📉 متوسط الوصول للهدف", f"{l_df['Max Reach %'].mean():.1f}%")
        c3.metric("📏 متوسط النقاط الخاسرة", f"{l_df['Pips'].mean():.1f}")

    st.markdown("---")
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 تنزيل بيانات الدورة (CSV)", csv, f"backtest_{symbol}_{period}.csv", "text/csv", use_container_width=True, type="primary")

def render_advanced_risk_calculator(unique_id="main"):
    st.markdown("### 💰 حاسبة المخاطرة المتقدمة")
    c1, c2, c3 = st.columns(3)
    with c1: capital = st.number_input("💵 رأس المال ($):", 10.0, 10000000.0, 1000.0, 100.0, "%.2f", key=f"{unique_id}_cap")
    with c2: risk_pct = st.selectbox("📊 المخاطرة (%):", [1,2,3,4,5,6,7,8,9,10], index=4, key=f"{unique_id}_rp")
    mx = capital * (risk_pct / 100)
    with c3: st.metric("🛑 الحد الأقصى", f"${mx:,.2f}")

    avail = get_available_symbols()
    search = st.text_input("🔍 ابحث:", placeholder="EUR, GBP, BTC...", key=f"{unique_id}_s")
    if search: avail = [s for s in avail if search.upper() in s.upper()]
    if not avail: st.warning("⚠️ لا توجد عملات"); return

    act = st.session_state.get("active_signal_symbol")
    di = avail.index(act) if act and act in avail else 0
    c_s, c_l = st.columns([2, 1])
    with c_s: sel = st.selectbox("🔽 العملة:", avail, index=di, key=f"{unique_id}_sym")
    with c_l: lot = st.number_input("💰 اللوت:", 0.0001, 100.0, 0.01, 0.01, "%.2f", key=f"{unique_id}_lot_{sel}")

    if act == sel and st.session_state.get("active_signal_entry"):
        de = float(st.session_state["active_signal_entry"])
        ds = float(st.session_state.get("active_signal_sl") or de * 1.01)
        dt = float(st.session_state.get("active_signal_tp") or de * 0.98)
        st.info("🔗 مُحمّل من الإشارة النشطة")
    else: de, ds, dt = 1.0, 1.01, 0.98

    ce, cs, ct = st.columns(3)
    with ce: entry = st.number_input("📈 الدخول:", value=float(de), format="%.5f", key=f"{unique_id}_e_{sel}")
    with cs: sl_p  = st.number_input("🛑 SL:", value=float(ds), format="%.5f", key=f"{unique_id}_sl_{sel}")
    with ct: tp_p  = st.number_input("🏆 TP:", value=float(dt), format="%.5f", key=f"{unique_id}_tp_{sel}")

    try:
        pip = pip_size_for(sel)
        net_points = abs(float(tp_p) - float(entry)) / pip
        st.metric("🎯 النقاط الصافية للهدف (TP)", f"{net_points:.1f} نقطة")
    except: pass

    chk = check_risk_limit(entry, sl_p, lot, sel, capital, risk_pct)
    try: rd = abs(float(entry) - float(sl_p)); rw = abs(float(tp_p) - float(entry)); rr = round(rw / rd, 2) if rd > 0 else "—"
    except: rr = "—"

    if chk["allowed"]: st.success("### ✅ مقبولة")
    else: st.error("### ❌ مرفوضة")

    m1, m2, m3 = st.columns(3)
    m1.metric("💸 المخاطرة", f"${chk['risk_usd']:,.2f}" if chk['risk_usd'] else "—")
    m2.metric("📊 النسبة", f"{chk['risk_pct_actual']}%" if chk['risk_pct_actual'] else "—")
    m3.metric("⚖️ R:R", f"1:{rr}" if rr != "—" else "—")
    st.info(f"**التفاصيل:** {chk['message']}")

    st.markdown("---")
    st.markdown("### 🧮 حاسبة حسابية")
    calc_key = f"{unique_id}_calc_result"
    if calc_key not in st.session_state: st.session_state[calc_key] = 0.0

    c_a, c_b = st.columns(2)
    with c_a: num_a = st.number_input("🔢 الرقم الأول:", value=float(st.session_state.get(f"{unique_id}_calc_a", 0.0)), step=1.0, format="%.4f", key=f"{unique_id}_calc_a")
    with c_b: num_b = st.number_input("🔢 الرقم الثاني:", value=float(st.session_state.get(f"{unique_id}_calc_b", 0.0)), step=1.0, format="%.4f", key=f"{unique_id}_calc_b")

    op1, op2, op3, op4 = st.columns(4)
    result_val = None; op_symbol = ""
    with op1:
        if st.button("➕ جمع", use_container_width=True, key=f"{unique_id}_calc_add"): result_val = num_a + num_b; op_symbol = "+"
    with op2:
        if st.button("➖ طرح", use_container_width=True, key=f"{unique_id}_calc_sub"): result_val = num_a - num_b; op_symbol = "−"
    with op3:
        if st.button("✖️ ضرب", use_container_width=True, key=f"{unique_id}_calc_mul"): result_val = num_a * num_b; op_symbol = "×"
    with op4:
        if st.button("➗ قسمة", use_container_width=True, key=f"{unique_id}_calc_div"):
            if num_b != 0: result_val = num_a / num_b; op_symbol = "÷"
            else: st.error("⚠️ لا يمكن القسمة على صفر")

    if result_val is not None:
        st.session_state[calc_key] = result_val; st.session_state[f"{unique_id}_calc_last_op"] = op_symbol
        st.session_state[f"{unique_id}_calc_last_a"] = num_a; st.session_state[f"{unique_id}_calc_last_b"] = num_b

    last_op = st.session_state.get(f"{unique_id}_calc_last_op", ""); last_a = st.session_state.get(f"{unique_id}_calc_last_a", 0); last_b = st.session_state.get(f"{unique_id}_calc_last_b", 0); current_result = st.session_state.get(calc_key, 0.0)

    if last_op: st.success(f"### = `{current_result:.4f}`  ({last_a:.4f} {last_op} {last_b:.4f})")
    else: st.info(f"### النتيجة: `{current_result:.4f}`")

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي", "🧪 مختبر الاختبار الرجعي"], horizontal=True)
st.markdown("---")

if app_mode == "🧪 مختبر الاختبار الرجعي":
    st.markdown("### 🧪 مختبر الصناديق")
    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True)
    
    if bt_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="BTC-USD")]
    else:
        av = get_available_symbols()
        dp = [s for s in st.session_state.get("bt_picked_symbols", []) if s in av]
        picked = st.multiselect("اختر الرموز (من الشيت):", av, default=dp, key="bt_multi")
        st.session_state["bt_picked_symbols"] = picked
        bt_symbols = picked
        if not bt_symbols: st.warning("⚠️ اختر عملة")

    now = datetime.datetime.now()
    c1, c2, c3 = st.columns(3)
    sd = c1.date_input("من:", value=datetime.date(now.year-1, 1, 1)).strftime("%Y-%m-%d")
    ed = c2.date_input("إلى:", value=datetime.date.today()).strftime("%Y-%m-%d")
    interval = c3.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    lot = st.number_input("حجم اللوت:", 0.01, 100.0, 0.01, 0.01, "%.2f", key="bt_lot")
    
    if st.button("📊 بدء المحاكاة", use_container_width=True) and bt_symbols:
        results, dfs = [], {}
        bar = st.progress(0)
        for i, sym in enumerate(bt_symbols):
            bar.progress((i+1)/len(bt_symbols))
            df, trades = _cached_backtest(fix_symbol(sym), interval, sd, ed)
            if df is not None:
                dfs[sym] = df
                if trades:
                    tdf = pd.DataFrame(trades)
                    results.append({"symbol": sym, "trades_df": tdf, "total": len(tdf)})
                else:
                    results.append({"symbol": sym, "trades_df": pd.DataFrame(), "total": 0})
        st.session_state["bt_results"] = results
        st.session_state["bt_dfs"] = dfs
        st.session_state["bt_sd"], st.session_state["bt_ed"], st.session_state["bt_int"] = sd, ed, interval

    if "bt_results" in st.session_state and st.session_state["bt_results"]:
        rl = st.session_state["bt_results"]
        all_dfs = [r["trades_df"] for r in rl if not r["trades_df"].empty]
        
        if all_dfs:
            comb = pd.concat(all_dfs, ignore_index=True)
            tab1, tab2, tab3 = st.tabs(["📊 التقرير المالي", "📉 الرسوم البيانية والصفقات", "🧠 التشخيص"])
            
            with tab1: render_financial_report(comb, lot, "الكل", "مخصص")
            with tab2:
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                ai = rl[opts.index(st.selectbox("اختر الأصل:", opts))]
                sym, tdf = ai["symbol"], ai["trades_df"]
                if not tdf.empty:
                    if len(tdf) > 1: si = st.slider("الصفقة:", 0, len(tdf)-1, len(tdf)-1)
                    else: si = 0
                    cur = tdf.iloc[si]
                    st.write(cur.get("Trade Recommendation", ""))
                    df_chart = _prepare_chart_data(fix_symbol(sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"])
                    render_chart_fast(sym, cur, df_chart)
                    
                    with st.expander("📋 التفاصيل", expanded=False):
                        for col in ["Entry Date", "Exit Date", "Bias", "Result", "Entry Price", "Stop Loss", "Take Profit", "Max Reach %", "SL Safety %", "Loss Category"]:
                            if col in cur: st.text(f"{col}: {cur[col]}")
            with tab3:
                st.info("التشخيص قيد التطوير لهذا المحرك.")

else:
    st.markdown("### 🚀 الماسح الحي")
    av = get_available_symbols()
    dp = [s for s in st.session_state.get("live_picked_symbols", []) if s in av]
    picked = st.multiselect("اختر العملات (من الشيت):", av, default=dp, key="live_multi")
    st.session_state["live_picked_symbols"] = picked
    symbols = picked
    if not symbols: st.warning("⚠️ اختر عملة")

    interval = st.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    period = st.selectbox("النطاق:", ["1mo", "3mo", "6mo", "1y"], index=2)
    
    if st.button("🚀 بدء المسح", use_container_width=True):
        valid = []
        for sym in symbols:
            df, res = _cached_live(fix_symbol(sym), interval, period)
            if res and res.get("signal") in ("STRONG BUY", "STRONG SELL"):
                valid.append({"symbol": sym, "result": res})
        if valid:
            st.success(f"تم العثور على {len(valid)} إشارة")
            if len(valid) > 1: si = st.slider("الإشارة:", 0, len(valid)-1, 0)
            else: si = 0
            ar, sym = valid[si]["result"], valid[si]["symbol"]
            st.write(f"**{sym}** - {ar['signal']}")
            
            st.session_state["active_signal_symbol"] = sym
            st.session_state["active_signal_entry"] = ar.get("entry")
            st.session_state["active_signal_sl"] = ar.get("sl")
            st.session_state["active_signal_tp"] = ar.get("tp")
            
            df_chart = _prepare_chart_data(fix_symbol(sym), interval, None, None)
            if df_chart is not None: render_chart_fast(sym, ar, df_chart)

st.markdown("---")
with st.expander("💰 حاسبة المخاطرة المتقدمة + 🧮 حاسبة حسابية", expanded=False):
    render_advanced_risk_calculator(unique_id="end")
