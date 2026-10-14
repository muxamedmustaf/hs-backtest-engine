# -*- coding: utf-8 -*-
"""
backtest.py — Smart Market Analyzer (v48)
==========================================
⚡ تحسينات الأداء:
  • @st.cache_data على fetch_data
  • كاش على تحليل الإشارات
  • PLOTLY_CONFIG موحّد (بدون pin)
  • scrollZoom + pan (تحريك محترف)
  • ارتفاع 750 / هوامش أقل
"""
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from data_provider import fetch_data

try:
    from engine import run_full_analysis, backtest_strategy, diagnose_filters
except ImportError:
    from engine import run_full_analysis, backtest_strategy
    diagnose_filters = None

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    def get_symbols_from_sheet(*args, **kwargs):
        return [["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "NZDUSD=X",
                 "USDCAD=X", "USDCHF=X", "EURJPY=X", "GBPJPY=X", "AUDJPY=X"]]


# ══════════════════════════════════════════════════════════════════════════════
# Page setup
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Smart Market Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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


# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════
SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

ALL_GLOBAL_INTERVALS = [
    "1m", "2m", "3m", "4m", "5m", "10m", "15m", "30m", "45m",
    "1h", "2h", "3h", "4h", "6h", "8h", "12h",
    "1d", "2d", "3d", "1wk", "1mo", "3mo", "6mo", "1y"
]

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


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 PLOTLY_CONFIG — موحّد لكل الرسوم (بدون pin)
# ══════════════════════════════════════════════════════════════════════════════
PLOTLY_CONFIG = {
    'responsive': True,
    'scrollZoom': True,
    'displaylogo': False,
    'displayModeBar': True,
    'modeBarButtonsToRemove': [
        'toImage', 'sendDataToCloud', 'lasso2d', 'select2d',
        'autoScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian',
        'toggleSpikelines',
    ],
    'doubleClick': 'reset+autosize',
    'showTips': False,
    'watermark': False,
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ("XAUUSD", "XAUUSD=X", "GOLD"): return "GC=F"
    if sym in ("XAGUSD", "XAGUSD=X", "SILVER"): return "SI=F"
    if sym == "GBPADY=X": return "GBPNZD=X"
    if len(sym) == 6 and sym.isalpha(): return f"{sym}=X"
    return sym

def pip_size_for(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["pip"]
    if "XAU" in s or "GOLD" in s: return 0.1
    if "XAG" in s or "SILVER" in s: return 0.01
    if any(x in s for x in ("BTC", "ETH")): return 1.0
    if any(x in s for x in ("US30", "NAS", "SPX", "US100", "US500")): return 1.0
    if "JPY" in s: return 0.01
    if any(c in s for c in ("HUF","TRY","SEK","NOK","CZK","MXN","ZAR","PLN","INR","THB","DKK","HKD","SGD","PHP","IDR")):
        return 0.01
    return 0.0001

def get_default_lot_for_symbol(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["min_lot"]
    return 0.01


# ══════════════════════════════════════════════════════════════════════════════
# ⚡ Cached data fetching
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch(symbol, interval, start_date=None, end_date=None, period=None):
    try:
        if start_date and end_date:
            return fetch_data(symbol, interval=interval,
                              start_date=start_date, end_date=end_date, cache_hours=1)
        return fetch_data(symbol, interval=interval, period=period, cache_hours=1)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_backtest(symbol, interval, start_date, end_date):
    df = _cached_fetch(symbol, interval, start_date, end_date, None)
    if df is None or df.empty: return None, None
    try:
        trades = backtest_strategy(df, interval=interval, symbol=symbol)
    except Exception:
        return df, None
    return df, trades


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_live(symbol, interval, period):
    df = _cached_fetch(symbol, interval, None, None, period)
    if df is None or df.empty: return None, None
    try:
        res = run_full_analysis(df, interval=interval, symbol=symbol)
    except Exception:
        return df, None
    return df, res


# ══════════════════════════════════════════════════════════════════════════════
# compute helpers
# ══════════════════════════════════════════════════════════════════════════════
def compute_pips(df):
    if df is None or df.empty: return df
    df = df.copy()
    def _f(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    def _pick(row, names):
        for n in names:
            if n in row and pd.notna(row[n]):
                v = _f(row[n])
                if v is not None: return v
        return None
    pips_l, risk_l, rew_l, rr_l = [], [], [], []
    for _, row in df.iterrows():
        pip = pip_size_for(row.get("symbol") or row.get("Symbol") or "")
        e = _pick(row, ["Entry Price", "Entry", "entry"])
        x = _pick(row, ["Exit Price", "Exit", "exit", "Close Price"])
        sl = _pick(row, ["Stop Loss", "SL", "sl"])
        tp = _pick(row, ["Take Profit", "TP", "tp"])
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias

        p = (e - x) / pip if (e is not None and x is not None and is_sell) else \
            (x - e) / pip if (e is not None and x is not None) else None
        r = abs((sl - e) / pip if is_sell else (e - sl) / pip) if (e is not None and sl is not None) else None
        w = abs((e - tp) / pip if is_sell else (tp - e) / pip) if (e is not None and tp is not None) else None
        rr = round(w / r, 2) if (r and w and r > 0) else None

        pips_l.append(round(p, 1) if p is not None else None)
        risk_l.append(round(r, 1) if r is not None else None)
        rew_l.append(round(w, 1) if w is not None else None)
        rr_l.append(rr)
    df["Pips"] = pips_l; df["Risk_Pips"] = risk_l
    df["Reward_Pips"] = rew_l; df["RR_Ratio"] = rr_l
    return df


def compute_dollar_pnl(df, lot=0.01):
    if df is None or df.empty: return df
    df = df.copy()
    usd, pct = [], []
    for _, row in df.iterrows():
        sym = str(row.get("symbol") or row.get("Symbol") or "").upper()
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias
        try:
            e = float(row.get("Entry Price") or row.get("Entry"))
            x = float(row.get("Exit Price") or row.get("Exit"))
        except (TypeError, ValueError):
            usd.append(None); pct.append(None); continue
        move = (x - e) if not is_sell else (e - x)
        if any(k in sym for k in ("BTC", "ETH", "US30", "NAS", "SPX", "US100", "US500")):
            pnl = move * lot
        elif "XAU" in sym or "GC=F" in sym:
            pnl = move * lot * 100
        elif "XAG" in sym or "SI=F" in sym:
            pnl = move * lot * 5000
        elif sym.endswith("USD"):
            pnl = move * lot * 100000
        else:
            pnl = move * lot * 100000 / x if x else None
        usd.append(round(pnl, 2) if pnl is not None else None)
        pct.append(round(move / e * 100, 2) if e else None)
    df["PnL_USD"] = usd; df["PnL_Pct"] = pct
    return df


def check_risk_limit(entry, sl, lot, symbol, capital, risk_pct):
    try:
        e = float(entry); s = float(sl); l = float(lot)
    except (TypeError, ValueError):
        return {"allowed": False, "risk_usd": None, "max_risk_usd": None,
                "risk_pct_actual": None, "message": "⚠️ بيانات ناقصة"}
    if e == 0:
        return {"allowed": False, "risk_usd": None, "max_risk_usd": None,
                "risk_pct_actual": None, "message": "⚠️ سعر دخول غير صالح"}
    pm = abs(e - s)
    su = str(symbol).upper()
    if any(x in su for x in ("BTC", "ETH", "US30", "NAS", "SPX")):
        r = pm * l
    elif "XAU" in su or "GC=F" in su: r = pm * l * 100
    elif "XAG" in su or "SI=F" in su: r = pm * l * 5000
    elif su.endswith("USD"): r = pm * l * 100000
    else: r = pm * l * 100000 / e
    mx = capital * (risk_pct / 100)
    pct_a = (r / capital * 100) if capital > 0 else 0
    ok = r <= mx
    msg = (f"✅ مقبولة — المخاطرة {r:.2f}$ ({pct_a:.2f}%) ≤ الحد {mx:.2f}$" if ok
           else f"❌ مرفوضة — المخاطرة {r:.2f}$ ({pct_a:.2f}%) > الحد {mx:.2f}$")
    return {"allowed": ok, "risk_usd": round(r, 2), "max_risk_usd": round(mx, 2),
            "risk_pct_actual": round(pct_a, 2), "message": msg}


def get_available_symbols():
    s = set(IC_MARKETS_SPECS.keys())
    try:
        for x in get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]:
            s.add(str(x).strip())
    except Exception: pass
    return sorted(s)


def get_last_known_price(symbol):
    dfs = st.session_state.get("backtest_dfs", {})
    df = dfs.get(symbol)
    if df is not None and not df.empty:
        try: return float(df["Close"].iloc[-1])
        except Exception: pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 draw_rectangle_pattern
# ══════════════════════════════════════════════════════════════════════════════
def draw_rectangle_pattern(fig, source):
    if source is None: return
    try: box = source.get("consolidation_box")
    except Exception: return
    if box is None: return
    x0 = int(box["x_start"]); x1 = int(box["x_end"])
    bh = float(box["high"]);  bl = float(box["low"])

    fig.add_shape(type="rect", x0=x0, y0=bl, x1=x1, y1=bh,
                  line=dict(width=0), fillcolor="rgba(156,39,176,0.07)", layer="below")
    fig.add_shape(type="line", x0=x0, y0=bh, x1=x1, y1=bh,
                  line=dict(color="#2962FF", width=3.5), layer="above")
    fig.add_shape(type="line", x0=x0, y0=bl, x1=x1, y1=bl,
                  line=dict(color="#FF5252", width=3.5), layer="above")
    fig.add_shape(type="line", x0=x0, y0=bl, x1=x0, y1=bh,
                  line=dict(color="#9C27B0", width=1.5, dash="dot"), layer="above")
    fig.add_shape(type="line", x0=x1, y0=bl, x1=x1, y1=bh,
                  line=dict(color="#9C27B0", width=1.5, dash="dot"), layer="above")

    tn = source.get("top_nodes") or []
    bn = source.get("bot_nodes") or []
    if tn:
        fig.add_trace(go.Scatter(x=[n[0] for n in tn], y=[n[1] for n in tn],
            mode="markers", name="قمم",
            marker=dict(size=11, color="#2962FF", symbol="circle",
                        line=dict(color="white", width=2)), showlegend=True))
    if bn:
        fig.add_trace(go.Scatter(x=[n[0] for n in bn], y=[n[1] for n in bn],
            mode="markers", name="قيعان",
            marker=dict(size=11, color="#FF5252", symbol="circle",
                        line=dict(color="white", width=2)), showlegend=True))

    en = source.get("nodes") or []
    if en:
        fig.add_trace(go.Scatter(x=[n[0] for n in en], y=[n[1] for n in en],
            mode="markers", name="الدخول",
            marker=dict(size=20, color="#FFC107", symbol="star",
                        line=dict(color="black", width=2)), showlegend=True))

    arrow = source.get("arrow")
    if isinstance(arrow, dict):
        col = "#00C853" if arrow.get("direction") == "BUY" else "#D50000"
        fig.add_annotation(x=arrow["x1"], y=arrow["y1"], ax=arrow["x0"], ay=arrow["y0"],
                           xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=2.5, arrowwidth=4,
                           arrowcolor=col, opacity=0.95, text="TP",
                           font=dict(color=col, size=12))


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Realtime Actions
# ══════════════════════════════════════════════════════════════════════════════
def render_realtime_actions(trades_df, is_live=False):
    st.markdown("### 🎯 التصرفات المطلوبة الآن")
    if trades_df is None or trades_df.empty:
        st.info("ℹ️ لا توجد صفقات للتحليل"); return

    actions = []
    relevant = trades_df.index.tolist() if is_live else trades_df.tail(5).index.tolist()

    for idx in relevant:
        row = trades_df.loc[idx]
        result = str(row.get("Result", "")).upper()
        if not is_live and result in ("WIN", "LOSS", "TIMEOUT", "BREAKEVEN"): continue
        try:
            e = float(row.get("Entry Price") or row.get("Entry") or 0)
            s = float(row.get("Stop Loss") or row.get("SL") or 0)
            t = float(row.get("Take Profit") or row.get("TP") or 0)
        except (TypeError, ValueError): continue
        if e == 0 or s == 0 or t == 0: continue

        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_bear = "BEAR" in bias or "SELL" in bias
        prog = row.get("Max Reach %", 0) or 0
        if prog < 15: continue

        tot = abs(t - e)
        if prog >= 80:
            pr, act, gg = "🔴 عاجل", "إغلاق 50% + Trailing 60%", "60%"
            nsl = e + (0.6 * tot * (-1 if is_bear else 1))
        elif prog >= 50:
            pr, act, gg = "🟠 عالي", "تفعيل Trailing 30%", "30%"
            nsl = e + (0.3 * tot * (-1 if is_bear else 1))
        elif prog >= 25:
            pr, act, gg = "🟡 متوسط", "نقل SL للتعادل", "0%"
            nsl = e
        else: continue

        actions.append({"الأولوية": pr, "الزوج": row.get("symbol") or "?",
                        "الوصول": f"{prog:.1f}%", "الإجراء": act,
                        "SL الجديد": f"{nsl:.5f}", "الربح المضمون": gg,
                        "_p": {"🔴 عاجل": 0, "🟠 عالي": 1, "🟡 متوسط": 2}[pr]})

    if not actions:
        st.success("✅ لا توجد صفقات تحتاج تصرفًا الآن"); return

    actions.sort(key=lambda x: x["_p"])
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 عاجل", sum(1 for a in actions if a["الأولوية"] == "🔴 عاجل"))
    c2.metric("🟠 عالي", sum(1 for a in actions if a["الأولوية"] == "🟠 عالي"))
    c3.metric("🟡 متوسط", sum(1 for a in actions if a["الأولوية"] == "🟡 متوسط"))
    for a in actions:
        msg = f"**{a['الأولوية']} | {a['الزوج']}** — {a['الإجراء']} — الوصول: {a['الوصول']} — SL: `{a['SL الجديد']}`"
        st.error(msg) if a["الأولوية"].startswith("🔴") else \
        st.warning(msg) if a["الأولوية"].startswith("🟠") else st.info(msg)


# ══════════════════════════════════════════════════════════════════════════════
# 💰 Risk Calculator
# ══════════════════════════════════════════════════════════════════════════════
def render_advanced_risk_calculator(unique_id="main"):
    st.markdown("### 💰 حاسبة المخاطرة المتقدمة")
    c1, c2, c3 = st.columns(3)
    with c1:
        capital = st.number_input("💵 رأس المال ($):", min_value=10.0, max_value=10_000_000.0,
            value=1000.0, step=100.0, format="%.2f", key=f"{unique_id}_cap")
    with c2:
        risk_pct = st.selectbox("📊 المخاطرة (%):", [1,2,3,4,5,6,7,8,9,10],
            index=4, key=f"{unique_id}_rp")
    mx = capital * (risk_pct / 100)
    with c3:
        st.metric("🛑 الحد الأقصى", f"${mx:,.2f}")

    avail = get_available_symbols()
    search = st.text_input("🔍 ابحث:", placeholder="EUR, GBP, BTC...", key=f"{unique_id}_s")
    if search:
        avail = [s for s in avail if search.upper() in s.upper()]
    if not avail:
        st.warning("⚠️ لا توجد عملات مطابقة"); return

    act = st.session_state.get("active_signal_symbol")
    di = avail.index(act) if act and act in avail else 0

    c_s, c_l = st.columns([2, 1])
    with c_s:
        sel = st.selectbox("🔽 العملة:", avail, index=di, key=f"{unique_id}_sym")
    with c_l:
        lot = st.number_input("💰 اللوت:", min_value=0.0001, max_value=100.0,
            value=get_default_lot_for_symbol(sel), step=0.01, format="%.2f",
            key=f"{unique_id}_lot_{sel}")

    if act == sel and st.session_state.get("active_signal_entry"):
        de = float(st.session_state["active_signal_entry"])
        ds = float(st.session_state.get("active_signal_sl") or de * 1.01)
        dt = float(st.session_state.get("active_signal_tp") or de * 0.98)
        st.info("🔗 مُحمّل من الإشارة النشطة")
    else:
        lp = get_last_known_price(sel)
        de = float(lp) if lp else 1.0
        ds = de * 1.01; dt = de * 0.98

    ce, cs, ct = st.columns(3)
    with ce: entry = st.number_input("📈 الدخول:", value=float(de), format="%.5f", key=f"{unique_id}_e_{sel}")
    with cs: sl_p  = st.number_input("🛑 SL:", value=float(ds), format="%.5f", key=f"{unique_id}_sl_{sel}")
    with ct: tp_p  = st.number_input("🏆 TP:", value=float(dt), format="%.5f", key=f"{unique_id}_tp_{sel}")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("⚡ 1:2", key=f"{unique_id}_b2_{sel}", use_container_width=True):
            n = entry - 2*(sl_p-entry) if sl_p > entry else entry + 2*(entry-sl_p)
            st.session_state[f"{unique_id}_tp_{sel}"] = round(n, 5); st.rerun()
    with b2:
        if st.button("⚡ 1:3", key=f"{unique_id}_b3_{sel}", use_container_width=True):
            n = entry - 3*(sl_p-entry) if sl_p > entry else entry + 3*(entry-sl_p)
            st.session_state[f"{unique_id}_tp_{sel}"] = round(n, 5); st.rerun()
    with b3:
        if st.button("⚡ 1:1", key=f"{unique_id}_b1_{sel}", use_container_width=True):
            n = entry - (sl_p-entry) if sl_p > entry else entry + (entry-sl_p)
            st.session_state[f"{unique_id}_tp_{sel}"] = round(n, 5); st.rerun()

    chk = check_risk_limit(entry, sl_p, lot, sel, capital, risk_pct)
    try:
        rd = abs(float(entry) - float(sl_p)); rw = abs(float(tp_p) - float(entry))
        rr = round(rw / rd, 2) if rd > 0 else "—"
    except Exception: rr = "—"

    if chk["allowed"]: st.success("### ✅ مقبولة — ضمن حد المخاطرة")
    else: st.error("### ❌ مرفوضة — تجاوزت حد المخاطرة")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💸 المخاطرة", f"${chk['risk_usd']:,.2f}" if chk['risk_usd'] else "—")
    m2.metric("📊 النسبة", f"{chk['risk_pct_actual']}%" if chk['risk_pct_actual'] else "—")
    m3.metric("⚖️ R:R", f"1:{rr}" if rr != "—" else "—")
    st.info(f"**التفاصيل:** {chk['message']}")


# ══════════════════════════════════════════════════════════════════════════════
# 📊 Financial Report
# ══════════════════════════════════════════════════════════════════════════════
def render_financial_report(df, lot_size=0.01, symbol="—", period="—"):
    st.markdown("### 📊 التقرير المالي الكامل")
    if df is None or df.empty:
        st.info("ℹ️ لا توجد صفقات"); return

    df = compute_pips(df); df = compute_dollar_pnl(df, lot=lot_size)

    rc = next((c for c in ["Result", "Head Result"] if c in df.columns), None)
    if rc is None: st.warning("⚠️ لا عمود نتيجة"); return

    s = df[rc].astype(str).str.upper()
    w_df = df[s.str.contains("WIN")]; l_df = df[s.str.contains("LOSS")]
    o_df = df[s.str.contains("OPEN")]; t_df = df[s.str.contains("TIMEOUT")]

    w, l, o, t = len(w_df), len(l_df), len(o_df), len(t_df)
    total = len(df); closed = w + l
    wr = round(w / closed * 100, 1) if closed else 0
    lr = round(l / closed * 100, 1) if closed else 0

    wp = w_df["Pips"].dropna().sum() if not w_df.empty else 0
    lp = l_df["Pips"].dropna().sum() if not l_df.empty else 0
    wu = w_df["PnL_USD"].dropna().sum() if not w_df.empty else 0
    lu = l_df["PnL_USD"].dropna().sum() if not l_df.empty else 0
    net_p = wp + lp; net_u = wu + lu
    pf = round(abs(wu / lu), 2) if lu != 0 else float("inf")
    exp_p = net_p / closed if closed else 0
    exp_u = net_u / closed if closed else 0

    aw = wu / w if w else 0; al = abs(lu / l) if l else 0

    mws = mls = cw = cl = 0
    for r in s.tolist():
        if "WIN" in r: cw += 1; cl = 0; mws = max(mws, cw)
        elif "LOSS" in r: cl += 1; cw = 0; mls = max(mls, cl)
        else: cw = cl = 0

    if not df["PnL_USD"].dropna().empty:
        c = df["PnL_USD"].dropna().cumsum()
        dd = (c - c.cummax()).min()
        mdd = abs(dd) if pd.notna(dd) else 0
    else: mdd = 0

    st.markdown(f"#### 📍 {symbol} · {period}")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 الصفقات", total)
    k2.metric("✅ ناجحة", w, delta=f"{wr}%")
    k3.metric("❌ خاسرة", l, delta=f"{lr}%", delta_color="inverse")
    k4.metric("⏳ مفتوحة", o)

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("📏 النقاط", f"{net_p:+.1f}")
    k6.metric("💰 صافي الربح", f"${net_u:+.2f}")
    k7.metric("⚖️ Profit Factor", f"{pf:.2f}" if pf != float("inf") else "∞")
    k8.metric("📉 Max DD", f"${mdd:.2f}")

    adv1, adv2, adv3, adv4 = st.columns(4)
    adv1.metric("📈 Expectancy (نقاط)", f"{exp_p:+.1f}")
    adv2.metric("💵 Expectancy ($)", f"${exp_u:+.2f}")
    adv3.metric("🔥 أطول ربح", mws)
    adv4.metric("❄️ أطول خسارة", mls)

    ratio = aw / al if al > 0 else 0
    st.info(f"📊 متوسط الربح/الخسارة: ${aw:.2f} / ${al:.2f} = **{ratio:.2f}x**")

    if wr >= 60 and pf >= 1.5: st.success("🌟 استراتيجية ممتازة")
    elif wr >= 50 and pf >= 1.2: st.success("✅ استراتيجية جيدة")
    elif wr >= 40 and pf >= 1.0: st.warning("🟡 استراتيجية مقبولة")
    else: st.error("🔴 استراتيجية ضعيفة")


# ══════════════════════════════════════════════════════════════════════════════
# Session state
# ══════════════════════════════════════════════════════════════════════════════
for k, v in [
    ("current_symbol", "NZDCAD=X"),
    ("status_summary", "⚡ Live Scan & Backtest Lab"),
    ("scanned_signals", []),
    ("backtest_scanned_signals", []),
    ("backtest_dfs", {}),
    ("backtest_period", ""),
    ("active_signal_symbol", None),
    ("active_signal_entry", None),
    ("active_signal_sl", None),
    ("active_signal_tp", None),
    ("live_picked_symbols", []),
    ("bt_picked_symbols", []),
    ("signal_index", 0),
]:
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;direction:rtl;">
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:16px;padding:8px 14px;font-weight:700;color:#0B57D0;">📈 {st.session_state.current_symbol}</div>
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:30px;padding:8px 14px;font-weight:700;color:#0B57D0;">{st.session_state.status_summary}</div>
</div>''', unsafe_allow_html=True)

app_mode = st.radio("وضع التطبيق:",
    ["🚀 الماسح الحي", "🧪 مختبر الاختبار الرجعي"],
    horizontal=True)
st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ================= BACKTEST MODE =================
# ══════════════════════════════════════════════════════════════════════════════
if app_mode == "🧪 مختبر الاختبار الرجعي":

    st.markdown("### 🧪 مختبر تحليل الأداء التاريخي")

    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"],
        horizontal=True, key="bt_scan_mode")

    if bt_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="EURUSD=X", key="bt_sym")]
    else:
        av = get_available_symbols()
        dp = [s for s in st.session_state.get("bt_picked_symbols", []) if s in av]
        picked = st.multiselect("🔽 اختر العملات:", av, default=dp, key="bt_multi")
        st.session_state["bt_picked_symbols"] = picked
        bt_symbols = picked
        if not bt_symbols: st.warning("⚠️ اختر عملة")

    now = datetime.datetime.now()
    years = [now.year, now.year - 1, now.year - 2]
    months = {1:"يناير",2:"فبراير",3:"مارس",4:"إبريل",5:"مايو",6:"يونيو",
              7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

    st.markdown("#### 📅 الفترة")
    pm = st.radio("نمط:", ["📆 شهر", "📅 نطاق", "🗓️ سنة"],
        horizontal=True, key="bt_pmode")

    sd = ed = pl = None
    if pm == "📆 شهر":
        c1, c2 = st.columns(2)
        yy = c1.selectbox("السنة:", years, index=0, key="bt_y1")
        mm = c2.selectbox("الشهر:", list(months.keys()),
            format_func=lambda x: months[x], index=now.month - 1, key="bt_m1")
        _, ld = calendar.monthrange(yy, mm)
        sd = f"{yy}-{mm:02d}-01"; ed = f"{yy}-{mm:02d}-{ld:02d}"
        pl = f"{months[mm]} {yy}"
    elif pm == "📅 نطاق":
        c1, c2 = st.columns(2)
        p1 = c1.date_input("من:", value=datetime.date(now.year, max(1, now.month-1), 1),
            min_value=datetime.date(now.year-5, 1, 1), max_value=datetime.date.today(), key="bt_p1")
        p2 = c2.date_input("إلى:", value=datetime.date.today(),
            min_value=datetime.date(now.year-5, 1, 1), max_value=datetime.date.today(), key="bt_p2")
        if p1 < p2:
            sd = p1.strftime("%Y-%m-%d"); ed = p2.strftime("%Y-%m-%d")
            pl = f"{sd} → {ed}"
    else:
        yy = st.selectbox("السنة:", years, index=0, key="bt_y2")
        sd = f"{yy}-01-01"; ed = f"{yy}-12-31"; pl = f"السنة {yy}"

    st.markdown("---")
    interval = st.selectbox("⏱️ الإطار:", ALL_GLOBAL_INTERVALS, index=9, key="bt_int")
    st.info("⏱️ عمر المستطيل الأدنى: أسبوع واحد (7 أيام)")

    lot = st.number_input("حجم اللوت:", 0.01, 100.0, 0.01, 0.01, "%.2f", key="bt_lot")

    if st.button("📊 بدء المحاكاة", use_container_width=True) and bt_symbols and sd and ed:
        results, dfs = [], {}
        bar = st.progress(0); txt = st.empty(); errs = []
        for i, sym in enumerate(bt_symbols):
            txt.text(f"({i+1}/{len(bt_symbols)}): {sym}...")
            bar.progress((i + 1) / len(bt_symbols))
            try:
                df, trades = _cached_backtest(fix_symbol(sym), interval, sd, ed)
                if df is None or df.empty:
                    errs.append(f"⚠️ {sym}: لا توجد بيانات"); continue
                if trades:
                    tdf = pd.DataFrame(trades)
                    if "symbol" not in tdf.columns: tdf["symbol"] = sym
                    results.append({"symbol": sym, "trades_df": tdf, "total_signals": len(tdf)})
                    dfs[sym] = df
            except Exception as e:
                errs.append(f"❌ {sym}: {e}")
        txt.empty(); bar.empty()
        st.session_state.backtest_scanned_signals = results
        st.session_state.backtest_dfs = dfs
        st.session_state.backtest_period = pl
        st.session_state.signal_index = 0
        if errs:
            with st.expander(f"⚠️ تحذيرات ({len(errs)})"):
                for m in errs: st.text(m)

    if st.session_state.backtest_scanned_signals:
        rl = st.session_state.backtest_scanned_signals
        dfs_dict = st.session_state.backtest_dfs
        pd_disp = st.session_state.get("backtest_period", "غير محدد")

        all_dfs = [i["trades_df"] for i in rl if "trades_df" in i and not i["trades_df"].empty]
        if all_dfs:
            comb = pd.concat(all_dfs, ignore_index=True)
            with st.expander("📊 التقرير المالي الشامل", expanded=False):
                render_financial_report(comb, lot_size=lot,
                                       symbol="كل الأصول", period=pd_disp)

        if bt_mode == "🎯 مجموعة" and len(rl) > 1:
            opts = [f"{i['symbol']} | {i['total_signals']}" for i in rl]
            ai = rl[opts.index(st.selectbox("👇 اختر:", opts))]
        else:
            ai = rl[0]

        sym = ai["symbol"]
        tdf = compute_pips(ai["trades_df"])
        tdf = compute_dollar_pnl(tdf, lot=lot)
        st.session_state.current_symbol = sym

        if len(tdf) == 0:
            st.warning(f"⚠️ **{sym}** — لا توجد مستطيلات")
        else:
            st.markdown(f"### 📊 {sym} — {len(tdf)} إشارة")

            last = tdf.iloc[-1]
            st.session_state["active_signal_symbol"] = sym
            st.session_state["active_signal_entry"] = last.get("Entry Price") or last.get("Entry")
            st.session_state["active_signal_sl"] = last.get("Stop Loss") or last.get("SL")
            st.session_state["active_signal_tp"] = last.get("Take Profit") or last.get("TP")

            with st.expander(f"📊 تقرير مالي — {sym}", expanded=False):
                render_financial_report(tdf, lot_size=lot, symbol=sym, period=pd_disp)

            with st.expander("🎯 التصرفات", expanded=False):
                render_realtime_actions(tdf, is_live=False)

            if st.session_state.get("_last_sym") != sym:
                st.session_state.signal_index = len(tdf) - 1
                st.session_state["_last_sym"] = sym

            si = max(0, min(st.session_state.signal_index, len(tdf) - 1))
            n1, n2, n3, n4, n5 = st.columns([1, 1, 3, 1, 1])
            with n1:
                if st.button("⏮️", use_container_width=True): st.session_state.signal_index = 0; st.rerun()
            with n2:
                if st.button("◀", use_container_width=True): st.session_state.signal_index = max(0, si - 1); st.rerun()
            with n3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>إشارة {si+1} من {len(tdf)}</div>", unsafe_allow_html=True)
            with n4:
                if st.button("▶", use_container_width=True): st.session_state.signal_index = min(len(tdf)-1, si+1); st.rerun()
            with n5:
                if st.button("⏭️", use_container_width=True): st.session_state.signal_index = len(tdf)-1; st.rerun()

            cur = tdf.iloc[si]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🎯 الدخول", f"{cur.get('Entry Price', '—')}")
            m2.metric("🛑 SL", f"{cur.get('Stop Loss', '—')}")
            m3.metric("🏆 TP", f"{cur.get('Take Profit', '—')}")
            m4.metric("📊 النتيجة", f"{cur.get('Result', '—')}")

            if sym in dfs_dict and not dfs_dict[sym].empty:
                _o = dfs_dict[sym].copy()
                _d = _o.index.tolist()
                df_res = _o.reset_index(drop=True)
                df_res["EMA50"] = df_res["Close"].ewm(span=50, adjust=False).mean()
                df_res["EMA200"] = df_res["Close"].ewm(span=200, adjust=False).mean()
                x = list(range(len(df_res)))

                fig = go.Figure(data=[go.Candlestick(x=x, open=df_res["Open"], high=df_res["High"],
                    low=df_res["Low"], close=df_res["Close"], name="السعر")])
                fig.add_trace(go.Scatter(x=x, y=df_res["EMA50"],
                    line=dict(color="orange", width=1.2), name="EMA 50"))
                fig.add_trace(go.Scatter(x=x, y=df_res["EMA200"],
                    line=dict(color="blue", width=1.2), name="EMA 200"))

                draw_rectangle_pattern(fig, cur)

                step = max(1, len(df_res) // 8)
                tv = list(range(0, len(df_res), step))
                tt = [str(_d[i])[:10] if i < len(_d) else "" for i in tv]

                fig.update_layout(
                    template="plotly_white",
                    height=750, autosize=True,
                    margin=dict(l=45, r=10, t=35, b=45),
                    xaxis_rangeslider_visible=False,
                    dragmode="pan",
                    hovermode="x unified",
                    yaxis=dict(side="left", automargin=True,
                               tickfont=dict(size=11, color="#333"),
                               showgrid=True, gridcolor="#EEEEEE", zeroline=False),
                    xaxis=dict(automargin=True, tickfont=dict(size=10),
                               tickmode="array", tickvals=tv, ticktext=tt,
                               showgrid=False, rangeslider=dict(visible=False),
                               fixedrange=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="center", x=0.5,
                                bgcolor="rgba(255,255,255,0.9)",
                                bordercolor="#DDDDDD", borderwidth=1),
                )
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


# ══════════════════════════════════════════════════════════════════════════════
# ================= LIVE SCAN MODE =================
# ══════════════════════════════════════════════════════════════════════════════
else:

    mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"],
        horizontal=True, key="live_mode")

    if mode == "سهم فردي":
        symbols = [st.text_input("رمز:", value="EURUSD=X", key="live_sym")]
    else:
        av = get_available_symbols()
        dp = [s for s in st.session_state.get("live_picked_symbols", []) if s in av]
        picked = st.multiselect("🔽 اختر العملات:", av, default=dp, key="live_multi")
        st.session_state["live_picked_symbols"] = picked
        symbols = picked
        if not symbols: st.warning("⚠️ اختر عملة")

    c1, c2 = st.columns(2)
    interval = c1.selectbox("⏱️ الإطار:", ALL_GLOBAL_INTERVALS, index=9, key="live_int")
    period = c2.selectbox("📅 النطاق:",
        ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"],
        index=4, key="live_period")

    st.info("⏱️ عمر المستطيل الأدنى: أسبوع واحد")

    if st.button("🚀 بدء المسح", use_container_width=True) and symbols:
        valid = []; bar = st.progress(0); txt = st.empty(); errs = []
        for i, sym in enumerate(symbols):
            txt.text(f"({i+1}/{len(symbols)}): {sym}...")
            bar.progress((i + 1) / len(symbols))
            try:
                df, res = _cached_live(fix_symbol(sym), interval, period)
                if df is None or df.empty:
                    errs.append(f"⚠️ {sym}: لا توجد بيانات"); continue
                if res and res.get("signal") in ("STRONG BUY", "STRONG SELL"):
                    valid.append({"symbol": sym, "result": res})
            except Exception as e:
                errs.append(f"❌ {sym}: {e}")
        txt.empty(); bar.empty()
        st.session_state.scanned_signals = valid
        st.session_state.signal_index = 0
        if errs:
            with st.expander(f"⚠️ تحذيرات ({len(errs)})"):
                for m in errs: st.text(m)

    if st.session_state.scanned_signals:
        sigs = st.session_state.scanned_signals
        st.success(f"✅ تم العثور على **{len(sigs)}** إشارة")

        if st.toggle("🔽 عرض النتائج", value=False, key="live_show"):
            si = max(0, min(st.session_state.signal_index, len(sigs) - 1))
            n1, n2, n3, n4, n5 = st.columns([1, 1, 3, 1, 1])
            with n1:
                if st.button("⏮️", use_container_width=True, key="ln1"): st.session_state.signal_index = 0; st.rerun()
            with n2:
                if st.button("◀", use_container_width=True, key="ln2"): st.session_state.signal_index = max(0, si - 1); st.rerun()
            with n3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>إشارة {si+1} من {len(sigs)}</div>", unsafe_allow_html=True)
            with n4:
                if st.button("▶", use_container_width=True, key="ln4"): st.session_state.signal_index = min(len(sigs)-1, si+1); st.rerun()
            with n5:
                if st.button("⏭️", use_container_width=True, key="ln5"): st.session_state.signal_index = len(sigs)-1; st.rerun()

            ar = sigs[si]["result"]
            asy = ar.get("symbol", "N/A")

            e1, e2, e3 = st.columns(3)
            e1.metric("🎯 الدخول", f"{ar.get('entry', 0)}")
            e2.metric("🛑 SL", f"{ar.get('sl', 0)}")
            e3.metric("🏆 TP", f"{ar.get('tp', 0)}")

            st.session_state["active_signal_symbol"] = asy
            st.session_state["active_signal_entry"] = ar.get("entry")
            st.session_state["active_signal_sl"] = ar.get("sl")
            st.session_state["active_signal_tp"] = ar.get("tp")

            dfo = ar.get("df")
            if dfo is not None and not dfo.empty:
                _d = dfo.index.tolist()
                dfr = dfo.reset_index(drop=True)
                dfr["EMA50"] = dfr["Close"].ewm(span=50, adjust=False).mean()
                dfr["EMA200"] = dfr["Close"].ewm(span=200, adjust=False).mean()
                x = list(range(len(dfr)))

                fig = go.Figure(data=[go.Candlestick(x=x, open=dfr["Open"], high=dfr["High"],
                    low=dfr["Low"], close=dfr["Close"], name="السعر")])
                fig.add_trace(go.Scatter(x=x, y=dfr["EMA50"],
                    line=dict(color="orange", width=1.2), name="EMA 50"))
                fig.add_trace(go.Scatter(x=x, y=dfr["EMA200"],
                    line=dict(color="blue", width=1.2), name="EMA 200"))

                draw_rectangle_pattern(fig, ar)

                step = max(1, len(dfr) // 8)
                tv = list(range(0, len(dfr), step))
                tt = [str(_d[i])[:10] if i < len(_d) else "" for i in tv]

                fig.update_layout(
                    template="plotly_white",
                    height=750, autosize=True,
                    margin=dict(l=45, r=10, t=35, b=45),
                    xaxis_rangeslider_visible=False,
                    dragmode="pan",
                    hovermode="x unified",
                    yaxis=dict(side="left", automargin=True,
                               tickfont=dict(size=11, color="#333"),
                               showgrid=True, gridcolor="#EEEEEE", zeroline=False),
                    xaxis=dict(automargin=True, tickfont=dict(size=10),
                               tickmode="array", tickvals=tv, ticktext=tt,
                               showgrid=False, rangeslider=dict(visible=False),
                               fixedrange=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="center", x=0.5,
                                bgcolor="rgba(255,255,255,0.9)",
                                bordercolor="#DDDDDD", borderwidth=1),
                )
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


# ══════════════════════════════════════════════════════════════════════════════
# Footer
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("💰 حاسبة المخاطرة المتقدمة", expanded=False):
    render_advanced_risk_calculator(unique_id="end")

with st.expander("📖 دليل الاستخدام", expanded=False):
    st.markdown("""
    ## 🎯 Horizontal Rectangle Reversal

    ### الشروط:
    - ✅ انطلاقة قوية (≥ 0.8%)
    - ✅ مستطيل أفقي ≥ أسبوع
    - ✅ ≥ 3 لمسات على كل حد
    - ✅ كسر بإغلاق شمعة
    - ✅ SL على الجهة المقابلة
    - ✅ TP = حجم الانطلاقة

    ### 🎮 التحكم بالشارت:
    - **سحب بإصبع** → تحريك (Pan)
    - **ضغط بإصبعين + سحب** → تكبير/تصغير
    - **نقرة مزدوجة** → Reset
    - **عجلة الماوس** → تكبير
    """)
