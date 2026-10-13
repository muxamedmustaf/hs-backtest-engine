# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st, yfinance as yf, plotly.graph_objects as go, pandas as pd
from data_provider import fetch_data, get_provider_info, PROVIDER
from engine import run_full_analysis, backtest_strategy
try:
    from engine import diagnose_filters
except ImportError:
    diagnose_filters = None

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    def get_symbols_from_sheet(*args, **kwargs):
        return [["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "NZDUSD=X",
                 "USDCAD=X", "USDCHF=X", "EURJPY=X", "GBPJPY=X", "AUDJPY=X",
                 "NZDCAD=X", "GBPAUD=X", "EURGBP=X", "USDTRY=X", "USDTHB=X",
                 "GBPNOK=X", "CADJPY=X", "AUDNZD=X"]]

st.set_page_config(page_title="Smart Market Analyzer", page_icon="📈",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    .main .block-container { max-width: 100% !important; padding: 0.1rem !important; }
    div[data-testid='stPlotlyChart'] { width: 100% !important; }
    iframe { width: 100% !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    label, .stRadio label, .stTextInput label, .stSelectbox label {
        direction: rtl; text-align: right;
    }
    div[data-testid="stMetricLabel"] { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    .stButton > button { direction: rtl; text-align: center; }
    .stAlert, .stInfo, .stSuccess, .stWarning, .stError {
        direction: rtl; text-align: right;
    }
    .stDataFrame { direction: ltr; }
    * { transition: none !important; animation: none !important; }
    section.main > div { contain: layout style !important; }
    .stDataFrame, .stPlotlyChart { contain: content !important; }
    .stExpander, .stMetric, .stDataFrame { box-shadow: none !important; }
    details { padding: 0.2rem !important; }
    div[data-testid="stMetric"] { padding: 4px !important; }
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

ALL_GLOBAL_INTERVALS = [
    "1m", "2m", "3m", "4m", "5m", "10m", "15m", "30m", "45m",
    "1h", "2h", "3h", "4h", "6h", "8h", "12h",
    "1d", "2d", "3d", "1wk", "1mo", "3mo", "6mo", "1y"
]

INTERVAL_LIMITS = {
    "1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60,
    "60m": 730, "90m": 60, "1h": 730,
}

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
    "EURGBP=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "EURCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURAUD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "GBPCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPAUD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "AUDCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "NZDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "NZDCHF=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "NZDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "CADJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "CHFJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "USDTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
    "USDNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Scandinavian"},
    "USDTHB=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
    "GBPNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Scandinavian"},
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
    if any(c in s for c in ["HUF","TRY","SEK","NOK","CZK","MXN","ZAR","PLN","INR","THB","DKK","HKD","SGD","PHP","IDR"]):
        return 0.01
    return 0.0001

def get_default_lot_for_symbol(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["min_lot"]
    return 0.01


def compute_pips(trades_df):
    if trades_df is None or trades_df.empty: return trades_df
    df = trades_df.copy()
    def to_float(v):
        try: return float(v)
        except (TypeError, ValueError): return None
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
        pips = (entry - exit_) / pip if is_sell else (exit_ - entry) / pip if entry and exit_ else None
        risk = abs((sl - entry) / pip if is_sell else (entry - sl) / pip) if entry and sl else None
        reward = abs((entry - tp) / pip if is_sell else (tp - entry) / pip) if entry and tp else None
        rr = round(reward / risk, 2) if (risk and reward and risk > 0) else None
        pips_l.append(round(pips, 1) if pips is not None else None)
        risk_l.append(round(risk, 1) if risk is not None else None)
        reward_l.append(round(reward, 1) if reward is not None else None)
        rr_l.append(rr)
    df["Pips"] = pips_l; df["Risk_Pips"] = risk_l
    df["Reward_Pips"] = reward_l; df["RR_Ratio"] = rr_l
    return df


def get_available_symbols():
    symbols_set = set(IC_MARKETS_SPECS.keys())
    try:
        for s in get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]:
            symbols_set.add(str(s).strip())
    except Exception: pass
    return sorted(list(symbols_set))


def _week_to_bars_label(interval):
    mapping = {"1m": "7 أيام", "5m": "7 أيام", "15m": "7 أيام", "30m": "7 أيام",
               "1h": "7 أيام", "4h": "7 أيام", "1d": "7 أيام"}
    return mapping.get(interval, "7 أيام")


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 draw_rectangle_pattern — مستطيل مثالي بحواف مستقيمة
# ══════════════════════════════════════════════════════════════════════════════
def draw_rectangle_pattern(fig, source):
    if source is None: return
    box = source.get("consolidation_box") if isinstance(source, dict) else source.get("consolidation_box")
    if box is None: return

    x_start  = int(box["x_start"]); x_end = int(box["x_end"])
    box_high = float(box["high"]);   box_low = float(box["low"])

    # تعبئة
    fig.add_shape(type="rect", x0=x_start, y0=box_low, x1=x_end, y1=box_high,
                  line=dict(width=0), fillcolor="rgba(156, 39, 176, 0.07)", layer="below")
    # حدود أفقية
    fig.add_shape(type="line", x0=x_start, y0=box_high, x1=x_end, y1=box_high,
                  line=dict(color="#2962FF", width=4), layer="above")
    fig.add_shape(type="line", x0=x_start, y0=box_low, x1=x_end, y1=box_low,
                  line=dict(color="#FF5252", width=4), layer="above")
    # حدود عمودية
    fig.add_shape(type="line", x0=x_start, y0=box_low, x1=x_start, y1=box_high,
                  line=dict(color="#9C27B0", width=2, dash="dot"), layer="above")
    fig.add_shape(type="line", x0=x_end, y0=box_low, x1=x_end, y1=box_high,
                  line=dict(color="#9C27B0", width=2, dash="dot"), layer="above")

    # علامات القمم
    top_nodes = source.get("top_nodes") or []
    bot_nodes = source.get("bot_nodes") or []
    if top_nodes:
        fig.add_trace(go.Scatter(
            x=[n[0] for n in top_nodes], y=[n[1] for n in top_nodes],
            mode="markers", name="قمم",
            marker=dict(size=13, color="#2962FF", symbol="circle",
                        line=dict(color="white", width=2.5)), showlegend=True))
    if bot_nodes:
        fig.add_trace(go.Scatter(
            x=[n[0] for n in bot_nodes], y=[n[1] for n in bot_nodes],
            mode="markers", name="قيعان",
            marker=dict(size=13, color="#FF5252", symbol="circle",
                        line=dict(color="white", width=2.5)), showlegend=True))

    # نجمة الدخول
    entry_nodes = source.get("nodes") or []
    if entry_nodes:
        fig.add_trace(go.Scatter(
            x=[n[0] for n in entry_nodes], y=[n[1] for n in entry_nodes],
            mode="markers", name="الدخول",
            marker=dict(size=22, color="#FFC107", symbol="star",
                        line=dict(color="black", width=2)), showlegend=True))

    # سهم
    arrow = source.get("arrow")
    if isinstance(arrow, dict):
        col = "#00C853" if arrow.get("direction") == "BUY" else "#D50000"
        fig.add_annotation(x=arrow["x1"], y=arrow["y1"], ax=arrow["x0"], ay=arrow["y0"],
                           xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=2.5, arrowwidth=4,
                           arrowcolor=col, opacity=0.95, text="TP",
                           font=dict(color=col, size=13))


# ══════════════════════════════════════════════════════════════════════════════
# Session State
# ══════════════════════════════════════════════════════════════════════════════
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
    ("live_picked_symbols", []),
    ("bt_picked_symbols", []),
    ("signal_index", 0),   # 🆕 تنقل الإشارات
]:
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;direction:rtl;">
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:16px;padding:8px 14px;font-weight:700;color:#0B57D0;">📈 {st.session_state.current_symbol}</div>
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:30px;padding:8px 14px;font-weight:700;color:#0B57D0;">{st.session_state.status_summary}</div>
</div>''', unsafe_allow_html=True)

app_mode = st.radio("وضع التطبيق:",
    ["🚀 الماسح الحي للأسواق", "🧪 مختبر الاختبار الرجعي (Backtest)"],
    horizontal=True)
st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ================= BACKTEST MODE =================
# ══════════════════════════════════════════════════════════════════════════════
if app_mode == "🧪 مختبر الاختبار الرجعي (Backtest)":

    st.markdown("### 🧪 مختبر تحليل الأداء التاريخي")

    bt_scan_mode = st.radio("طريقة فحص الاختبار الرجعي:",
        ["سهم فردي", "🎯 مجموعة مخصصة"],
        horizontal=True, key="bt_scan_mode")

    if bt_scan_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="EURUSD=X", key="bt_single_symbol")]
    else:
        all_available = get_available_symbols()
        default_picks = st.session_state.get("bt_picked_symbols", [])
        default_picks = [s for s in default_picks if s in all_available]
        picked = st.multiselect("🔽 اختر العملات:", options=all_available,
            default=default_picks, key="bt_multi_symbols")
        st.session_state["bt_picked_symbols"] = picked
        bt_symbols = picked if picked else []
        if not bt_symbols: st.warning("⚠️ اختر عملة")

    now = datetime.datetime.now()
    available_years = [now.year, now.year - 1, now.year - 2]
    months_dict = {1:"يناير",2:"فبراير",3:"مارس",4:"إبريل",5:"مايو",6:"يونيو",
                   7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

    st.markdown("#### 📅 الفترة")
    period_mode = st.radio("نمط الفترة:",
        ["📆 شهر واحد", "📅 نطاق مخصص", "🗓️ سنة كاملة"],
        horizontal=True, key="bt_period_mode")

    start_date = None; end_date = None; period_label = ""

    if period_mode == "📆 شهر واحد":
        c_yr, c_mo = st.columns(2)
        selected_year = c_yr.selectbox("📅 السنة:", available_years, index=0, key="bt_single_year")
        selected_month = c_mo.selectbox("🗓️ الشهر:", list(months_dict.keys()),
            format_func=lambda x: months_dict[x], index=now.month - 1, key="bt_single_month")
        _, last_day = calendar.monthrange(selected_year, selected_month)
        start_date = f"{selected_year}-{selected_month:02d}-01"
        end_date   = f"{selected_year}-{selected_month:02d}-{last_day:02d}"
        period_label = f"{months_dict[selected_month]} {selected_year}"
    elif period_mode == "📅 نطاق مخصص":
        c1, c2 = st.columns(2)
        start_pick = c1.date_input("📅 من:", value=datetime.date(now.year, max(1, now.month-1), 1),
            min_value=datetime.date(now.year - 5, 1, 1), max_value=datetime.date.today(), key="bt_custom_start")
        end_pick = c2.date_input("📅 إلى:", value=datetime.date.today(),
            min_value=datetime.date(now.year - 5, 1, 1), max_value=datetime.date.today(), key="bt_custom_end")
        if start_pick < end_pick:
            start_date = start_pick.strftime("%Y-%m-%d")
            end_date = end_pick.strftime("%Y-%m-%d")
            period_label = f"{start_date} → {end_date}"
    else:
        year_pick = st.columns(1)[0].selectbox("📅 السنة:", available_years, index=0, key="bt_full_year")
        start_date = f"{year_pick}-01-01"; end_date = f"{year_pick}-12-31"
        period_label = f"السنة {year_pick}"

    st.markdown("---")
    selected_interval = st.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=9, key="bt_interval")
    st.info(f"⏱️ **عمر المستطيل الأدنى:** {_week_to_bars_label(selected_interval)} — أقل من ذلك يُرفض")

    lot_size = st.number_input("حجم اللوت:", min_value=0.01, max_value=100.0,
        value=0.01, step=0.01, format="%.2f", key="bt_lot_size")

    if st.button("📊 بدء المحاكاة", use_container_width=True) and bt_symbols and start_date and end_date:
        results, dfs = [], {}
        p_bar = st.progress(0); s_txt = st.empty(); error_log = []

        for idx, sym in enumerate(bt_symbols):
            s_txt.text(f"({idx+1}/{len(bt_symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(bt_symbols))
            try:
                df = fetch_data(fix_symbol(sym), interval=selected_interval,
                                start_date=start_date, end_date=end_date, cache_hours=1)
                if df is None or df.empty:
                    error_log.append(f"⚠️ {sym}: لا توجد بيانات"); continue
                trades = backtest_strategy(df, interval=selected_interval, symbol=sym)
                if trades:
                    tdf = pd.DataFrame(trades)
                    if "symbol" not in tdf.columns: tdf["symbol"] = sym
                    results.append({"symbol": sym, "trades_df": tdf, "total_signals": len(tdf)})
                    dfs[sym] = df
            except Exception as e:
                error_log.append(f"❌ {sym}: {e}")

        s_txt.empty(); p_bar.empty()
        st.session_state.backtest_scanned_signals = results
        st.session_state.backtest_dfs = dfs
        st.session_state.backtest_period = period_label
        st.session_state.backtest_start = start_date
        st.session_state.backtest_end = end_date
        st.session_state.signal_index = 0  # reset
        if error_log:
            with st.expander(f"⚠️ تحذيرات ({len(error_log)})"):
                for m in error_log: st.text(m)

    if st.session_state.backtest_scanned_signals:
        res_list = st.session_state.backtest_scanned_signals
        dfs_dict = st.session_state.backtest_dfs
        period_display = st.session_state.get("backtest_period", "غير محدد")

        all_dfs = [i["trades_df"] for i in res_list if "trades_df" in i and not i["trades_df"].empty]

        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            combined_df = compute_pips(combined_df)

            g_res_col = None
            for col in ["Result", "Head Result"]:
                if col in combined_df.columns: g_res_col = col; break

            if g_res_col:
                g_series = combined_df[g_res_col].astype(str).str.upper()
                g_wins = len(combined_df[g_series.str.contains("WIN")])
                g_losses = len(combined_df[g_series.str.contains("LOSS")])
                g_opens = len(combined_df[g_series.str.contains("OPEN")])
            else:
                g_wins = g_losses = g_opens = 0

            g_closed = g_wins + g_losses
            g_win_rate = round((g_wins / g_closed) * 100, 1) if g_closed > 0 else 0.0
            g_total = len(combined_df)

            st.markdown(f"#### 🌍 الملخص الإجمالي — **{period_display}**")
            gm1, gm2, gm3, gm4 = st.columns(4)
            gm1.metric("📊 إجمالي الصفقات", g_total)
            gm2.metric("✅ ناجحة", g_wins, delta=f"{g_win_rate}%")
            gm3.metric("❌ خاسرة", g_losses)
            gm4.metric("⏳ مفتوحة", g_opens)
            st.markdown("---")

        if bt_scan_mode == "🎯 مجموعة مخصصة" and len(res_list) > 1:
            opts = [f"{i['symbol']} | إشارات: {i['total_signals']}" for i in res_list]
            active_item = res_list[opts.index(st.selectbox("👇 اختر الأصل:", opts))]
        else:
            active_item = res_list[0]

        active_sym = active_item["symbol"]
        trades_df = active_item["trades_df"]
        trades_df = compute_pips(trades_df)
        st.session_state.current_symbol = active_sym

        if len(trades_df) == 0:
            st.warning(f"⚠️ **{active_sym}** — لا توجد مستطيلات أفقية مطابقة (تحقق من الشروط الصارمة).")
        else:
            # ═══════════════════════════════════════════════════════════════
            # 🔽🔼 تنقل بين الإشارات
            # ═══════════════════════════════════════════════════════════════
            st.markdown(f"### 📊 {active_sym} — {len(trades_df)} إشارة")

            # reset index إذا تغير الرمز
            if st.session_state.get("_last_bt_sym") != active_sym:
                st.session_state.signal_index = len(trades_df) - 1
                st.session_state["_last_bt_sym"] = active_sym

            sig_idx = st.session_state.signal_index
            sig_idx = max(0, min(sig_idx, len(trades_df) - 1))

            nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 3, 1, 1])
            with nav1:
                if st.button("⏮️ الأولى", use_container_width=True):
                    st.session_state.signal_index = 0; st.rerun()
            with nav2:
                if st.button("◀ السابقة", use_container_width=True):
                    st.session_state.signal_index = max(0, sig_idx - 1); st.rerun()
            with nav3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>"
                            f"إشارة {sig_idx + 1} من {len(trades_df)}</div>",
                            unsafe_allow_html=True)
            with nav4:
                if st.button("التالية ▶", use_container_width=True):
                    st.session_state.signal_index = min(len(trades_df) - 1, sig_idx + 1); st.rerun()
            with nav5:
                if st.button("الأخيرة ⏭️", use_container_width=True):
                    st.session_state.signal_index = len(trades_df) - 1; st.rerun()

            current_sig = trades_df.iloc[sig_idx]

            # metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🎯 الدخول", f"{current_sig.get('Entry Price', '—')}")
            m2.metric("🛑 SL", f"{current_sig.get('Stop Loss', '—')}")
            m3.metric("🏆 TP", f"{current_sig.get('Take Profit', '—')}")
            m4.metric("📊 النتيجة", f"{current_sig.get('Result', '—')}")

            # الرسم
            if active_sym in dfs_dict and not dfs_dict[active_sym].empty:
                _orig = dfs_dict[active_sym].copy()
                _dates = _orig.index.tolist()
                df_res = _orig.reset_index(drop=True)
                df_res['EMA50'] = df_res['Close'].ewm(span=50, adjust=False).mean()
                df_res['EMA200'] = df_res['Close'].ewm(span=200, adjust=False).mean()
                _x = list(range(len(df_res)))

                fig = go.Figure(data=[go.Candlestick(
                    x=_x, open=df_res["Open"], high=df_res["High"],
                    low=df_res["Low"], close=df_res["Close"], name="السعر")])
                fig.add_trace(go.Scatter(x=_x, y=df_res['EMA50'],
                    line=dict(color='orange', width=1.2), name="EMA 50"))
                fig.add_trace(go.Scatter(x=_x, y=df_res['EMA200'],
                    line=dict(color='blue', width=1.2), name="EMA 200"))

                draw_rectangle_pattern(fig, current_sig)

                _step = max(1, len(df_res) // 8)
                _tick_vals = list(range(0, len(df_res), _step))
                _tick_text = [str(_dates[i])[:10] if i < len(_dates) else "" for i in _tick_vals]

                fig.update_layout(template="plotly_white", height=650, autosize=True,
                    margin=dict(l=80, r=20, t=40, b=60), xaxis_rangeslider_visible=False,
                    yaxis=dict(side="left", automargin=True, tickfont=dict(size=12, color="#333"),
                               showgrid=True, gridcolor="#E5E5E5"),
                    xaxis=dict(automargin=True, tickfont=dict(size=10),
                               tickmode="array", tickvals=_tick_vals, ticktext=_tick_text),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True, config={'responsive': True})

            # تفاصيل
            with st.expander("📋 تفاصيل الإشارة الحالية", expanded=False):
                for col in ["Entry Date", "Exit Date", "Bias", "Result", "Entry Price", "Stop Loss",
                            "Take Profit", "Pips", "RR_Ratio", "top_touches", "bot_touches",
                            "impulse_pct", "slope_pct", "cv_pct", "drift_pct", "flat_bars_pct"]:
                    if col in current_sig:
                        st.text(f"{col}: {current_sig[col]}")


# ══════════════════════════════════════════════════════════════════════════════
# ================= LIVE SCAN MODE =================
# ══════════════════════════════════════════════════════════════════════════════
else:

    scan_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة مخصصة"],
        horizontal=True, key="live_scan_mode")

    if scan_mode == "سهم فردي":
        symbols = [st.text_input("رمز الأصل", value="EURUSD=X", key="live_single_symbol")]
    else:
        all_available = get_available_symbols()
        default_picks = st.session_state.get("live_picked_symbols", [])
        default_picks = [s for s in default_picks if s in all_available]
        picked = st.multiselect("🔽 اختر العملات:", options=all_available,
            default=default_picks, key="live_multi_symbols")
        st.session_state["live_picked_symbols"] = picked
        symbols = picked if picked else []
        if not symbols: st.warning("⚠️ اختر عملة")

    c1, c2 = st.columns(2)
    selected_interval = c1.selectbox("⏱️ الإطار:", ALL_GLOBAL_INTERVALS, index=9, key="live_interval")
    selected_period = c2.selectbox("📅 النطاق:",
        ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
        index=4, key="live_period")

    st.info(f"⏱️ عمر المستطيل الأدنى: {_week_to_bars_label(selected_interval)}")

    if st.button("🚀 بدء المسح", use_container_width=True) and symbols:
        valid = []; p_bar = st.progress(0); s_txt = st.empty(); error_log = []

        for idx, sym in enumerate(symbols):
            s_txt.text(f"({idx+1}/{len(symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(symbols))
            try:
                df = fetch_data(fix_symbol(sym), interval=selected_interval,
                                period=selected_period, cache_hours=1)
                if df is None or df.empty:
                    error_log.append(f"⚠️ {sym}: لا توجد بيانات"); continue
                if len(df) >= 20:
                    res = run_full_analysis(df, interval=selected_interval, symbol=sym)
                    if res["signal"] in ["STRONG BUY", "STRONG SELL"]:
                        valid.append({"symbol": sym, "result": res})
                    elif scan_mode == "سهم فردي":
                        st.info(f"ℹ️ {sym}: لا يوجد مستطيل أفقي مطابق")
            except Exception as e:
                error_log.append(f"❌ {sym}: {e}")

        s_txt.empty(); p_bar.empty()
        st.session_state.scanned_signals = valid
        st.session_state.signal_index = 0
        if error_log:
            with st.expander(f"⚠️ تحذيرات ({len(error_log)})"):
                for m in error_log: st.text(m)

    if st.session_state.scanned_signals:
        sigs = st.session_state.scanned_signals
        st.success(f"✅ تم العثور على **{len(sigs)}** إشارة")

        _show = st.toggle("🔽 عرض النتائج", value=False, key="live_show_results")

        if _show:
            # تنقل
            sig_idx = st.session_state.signal_index
            sig_idx = max(0, min(sig_idx, len(sigs) - 1))

            nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 3, 1, 1])
            with nav1:
                if st.button("⏮️ الأولى", use_container_width=True, key="live_nav_first"):
                    st.session_state.signal_index = 0; st.rerun()
            with nav2:
                if st.button("◀ السابقة", use_container_width=True, key="live_nav_prev"):
                    st.session_state.signal_index = max(0, sig_idx - 1); st.rerun()
            with nav3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>"
                            f"إشارة {sig_idx + 1} من {len(sigs)}</div>",
                            unsafe_allow_html=True)
            with nav4:
                if st.button("التالية ▶", use_container_width=True, key="live_nav_next"):
                    st.session_state.signal_index = min(len(sigs) - 1, sig_idx + 1); st.rerun()
            with nav5:
                if st.button("الأخيرة ⏭️", use_container_width=True, key="live_nav_last"):
                    st.session_state.signal_index = len(sigs) - 1; st.rerun()

            active_res = sigs[sig_idx]['result']
            active_sym = active_res.get("symbol", "N/A")

            e1, e2, e3 = st.columns(3)
            e1.metric("🎯 الدخول", f"{active_res.get('entry', 0)}")
            e2.metric("🛑 SL", f"{active_res.get('sl', 0)}")
            e3.metric("🏆 TP", f"{active_res.get('tp', 0)}")

            df_res_orig = active_res.get("df")
            if df_res_orig is not None and not df_res_orig.empty:
                _dates_live = df_res_orig.index.tolist()
                df_res = df_res_orig.reset_index(drop=True)
                df_res['EMA50'] = df_res['Close'].ewm(span=50, adjust=False).mean()
                df_res['EMA200'] = df_res['Close'].ewm(span=200, adjust=False).mean()
                _x = list(range(len(df_res)))

                fig = go.Figure(data=[go.Candlestick(
                    x=_x, open=df_res["Open"], high=df_res["High"],
                    low=df_res["Low"], close=df_res["Close"], name="السعر")])
                fig.add_trace(go.Scatter(x=_x, y=df_res['EMA50'],
                    line=dict(color='orange', width=1.2), name="EMA 50"))
                fig.add_trace(go.Scatter(x=_x, y=df_res['EMA200'],
                    line=dict(color='blue', width=1.2), name="EMA 200"))

                draw_rectangle_pattern(fig, active_res)

                _step = max(1, len(df_res) // 8)
                _tick_vals = list(range(0, len(df_res), _step))
                _tick_text = [str(_dates_live[i])[:10] if i < len(_dates_live) else "" for i in _tick_vals]

                fig.update_layout(template="plotly_white", height=650, autosize=True,
                    margin=dict(l=80, r=20, t=40, b=60), xaxis_rangeslider_visible=False,
                    yaxis=dict(side="left", automargin=True, tickfont=dict(size=12, color="#333"),
                               showgrid=True, gridcolor="#E5E5E5"),
                    xaxis=dict(automargin=True, tickfont=dict(size=10),
                               tickmode="array", tickvals=_tick_vals, ticktext=_tick_text),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True, config={'responsive': True})


# ══════════════════════════════════════════════════════════════════════════════
# Footer
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("🎯 Strict Horizontal Rectangle · Min Age 1 Week · Navigate with ◀ ▶")
