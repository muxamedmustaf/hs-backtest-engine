# -*- coding: utf-8 -*-
"""
backtest.py — H&S Analyzer (Robust Imports + Enhancements)
"""
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from data_provider import fetch_data

# ══════════════════════════════════════════════════════════════════════════════
# ⚡ استيراد محصّن من engine
# ══════════════════════════════════════════════════════════════════════════════
try:
    from engine import run_full_analysis, backtest_strategy, REASON_MAP, diagnose_no_signals
except ImportError as e:
    st.error(f"❌ فشل استيراد الأساسيات من engine: {e}")
    st.info("تأكد أن engine.py يحتوي على: run_full_analysis، backtest_strategy")
    st.stop()

try:
    from engine import diagnose_filters
except ImportError:
    diagnose_filters = None

try:
    from engine import CONFIG as ENGINE_CONFIG
except ImportError:
    ENGINE_CONFIG = {}

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    def get_symbols_from_sheet(*args, **kwargs):
        return [["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "NZDUSD=X",
                 "USDCAD=X", "USDCHF=X", "EURJPY=X", "GBPJPY=X", "AUDJPY=X"]]


st.set_page_config(page_title="H&S Analyzer", page_icon="📈",
                   layout="wide", initial_sidebar_state="collapsed")

# زيادة العرض وتحسين القراءة والتنقل
st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    .main .block-container { max-width: 100% !important; padding: 0.5rem 1rem !important; }
    div[data-testid='stPlotlyChart'] { width: 100% !important; }
    iframe { width: 100% !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 15px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    label, .stRadio label, .stTextInput label, .stSelectbox label {
        direction: rtl; text-align: right; font-weight: 500;
    }
    div[data-testid="stMetricLabel"] { direction: rtl; text-align: right; font-size: 14px; }
    div[data-testid="stMetricValue"] { direction: ltr; text-align: right; font-size: 20px; }
    .stButton > button { direction: rtl; text-align: center; border-radius: 8px; }
    .stAlert, .stInfo, .stSuccess, .stWarning, .stError {
        direction: rtl; text-align: right; border-radius: 8px;
    }
    .stDataFrame { direction: ltr; }
    * { transition: none !important; animation: none !important; }
    section.main > div { contain: layout style !important; }
    .stDataFrame, .stPlotlyChart { contain: content !important; }
    .stExpander, .stMetric, .stDataFrame { box-shadow: none !important; }
    details { padding: 0.3rem !important; }
    div[data-testid="stMetric"] { padding: 8px !important; background: #f8f9fa; border-radius: 10px; border: 1px solid #e9ecef; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding: 8px 16px; }
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
    "GBPJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "AUDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "NZDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "CADJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "CHFJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "NZDCAD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDNZD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "USDTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
    "USDNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Scandinavian"},
}

PLOTLY_CONFIG = {
    'responsive': True,
    'scrollZoom': True,
    'displaylogo': False,
    'displayModeBar': True,
    'modeBarButtonsToRemove': [
        'sendDataToCloud', 'lasso2d', 'select2d',
        'autoScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian',
        'toggleSpikelines',
    ],
    'toImageButtonOptions': {
        'format': 'png', 'filename': 'hs_chart',
        'height': 900, 'width': 1600, 'scale': 2,
    },
    'doubleClick': 'reset+autosize',
    'showTips': False,
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
    if any(x in s for x in ("US30", "NAS", "SPX")): return 1.0
    if "JPY" in s: return 0.01
    if any(c in s for c in ("TRY","NOK","SEK","DKK","HKD","SGD","THB")):
        return 0.01
    return 0.0001


def get_default_lot_for_symbol(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["min_lot"]
    return 0.01


def get_available_symbols():
    s = set(IC_MARKETS_SPECS.keys())
    try:
        for x in get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]:
            s.add(str(x).strip())
    except Exception:
        pass
    return sorted(s)


def get_last_known_price(symbol):
    dfs = st.session_state.get("backtest_dfs", {})
    df = dfs.get(symbol)
    if df is not None and not df.empty:
        try: return float(df["Close"].iloc[-1])
        except Exception: pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# ⚡ Cached fetch
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
# Compute helpers
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
        if any(k in sym for k in ("BTC", "ETH", "US30", "NAS", "SPX")):
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
                "risk_pct_actual": None, "message": "⚠️ سعر غير صالح"}
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


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 draw_hs_pattern
# ══════════════════════════════════════════════════════════════════════════════
def draw_hs_pattern(fig, source, df):
    if source is None: return
    nodes = source.get("nodes", [])
    if not nodes or len(nodes) < 6: return

    xs = [n[0] for n in nodes]
    ys = [n[1] for n in nodes]

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        name="H&S Pattern",
        line=dict(color="#9C27B0", width=3),
        marker=dict(size=11, color="#9C27B0",
                    line=dict(color="white", width=2)),
        showlegend=True, hoverinfo="skip",
    ))

    nn = source.get("neckline_nodes", [])
    if len(nn) >= 2:
        x0, y0 = nn[0]; x1, y1 = nn[1]
        try:
            if hasattr(x0, 'timestamp'):
                span = (x1 - x0).total_seconds()
                x1_ext = x1 + pd.Timedelta(seconds=span * 0.3)
                x0_ext = x0 - pd.Timedelta(seconds=span * 0.05)
            else:
                span = x1 - x0
                x1_ext = x1 + span * 0.3
                x0_ext = x0 - span * 0.05
        except Exception:
            x0_ext, x1_ext = x0, x1
        fig.add_trace(go.Scatter(
            x=[x0_ext, x1_ext], y=[y0, y1],
            mode="lines", name="Neckline",
            line=dict(color="#2962FF", width=3, dash="dash"),
            showlegend=True, hoverinfo="skip",
        ))

    pivot_x = [n[0] for n in nodes[:5]]
    pivot_y = [n[1] for n in nodes[:5]]
    fig.add_trace(go.Scatter(
        x=pivot_x, y=pivot_y,
        mode="markers", name="Pivots",
        marker=dict(size=15, color="#FF6F00", symbol="circle",
                    line=dict(color="white", width=2.5)),
        showlegend=True, hoverinfo="skip",
    ))

    start_x = nodes[0][0]
    end_x = nodes[-1][0]
    fig.add_shape(type="line", x0=start_x, x1=start_x, y0=0, y1=1, yref="paper",
                  line=dict(color="#607D8B", width=1.5, dash="dot"), layer="below")
    fig.add_shape(type="line", x0=end_x, x1=end_x, y0=0, y1=1, yref="paper",
                  line=dict(color="#607D8B", width=1.5, dash="dot"), layer="below")

    entry = source.get("entry")
    if entry is not None:
        entry_x = nodes[-1][0]
        fig.add_trace(go.Scatter(
            x=[entry_x], y=[float(entry)],
            mode="markers", name="Entry",
            marker=dict(size=22, color="#FFC107", symbol="star",
                        line=dict(color="black", width=2)),
            showlegend=True, hoverinfo="skip",
        ))

    if entry is not None:
        tp = source.get("tp")
        is_bull = "Bull" in source.get("bias", "")
        col = "#00C853" if is_bull else "#D50000"
        entry_x = nodes[-1][0]
        try:
            if hasattr(nodes[0][0], 'timestamp'):
                total_span = (nodes[-1][0] - nodes[0][0]).total_seconds()
                step = total_span / 5
                x1_pos = nodes[-1][0] + pd.Timedelta(seconds=step * 3)
            else:
                total_span = nodes[-1][0] - nodes[0][0]
                x1_pos = nodes[-1][0] + (total_span / 5) * 3
        except Exception:
            x1_pos = nodes[-1][0]
        fig.add_annotation(
            x=x1_pos, y=float(tp),
            ax=entry_x, ay=float(entry),
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=3, arrowsize=2.5, arrowwidth=4,
            arrowcolor=col, opacity=0.95,
            text=f"TP ({float(tp):.5f})",
            font=dict(color=col, size=12),
        )

    sl = source.get("sl")
    if sl is not None:
        sl_y = float(sl)
        sl_x = nodes[-1][0]
        fig.add_annotation(
            x=sl_x, y=sl_y,
            text=f"SL ({sl_y:.5f})",
            showarrow=False,
            font=dict(color="#D50000", size=11),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#D50000", borderwidth=1,
            xanchor="left", xshift=8,
        )


# ══════════════════════════════════════════════════════════════════════════════
# 📊 Financial Report + Loss Analysis + Recommendations + Download
# ══════════════════════════════════════════════════════════════════════════════
def render_financial_report(df, lot_size=0.01, symbol="—", period="—", raw_df=None, interval="1h"):
    st.markdown("### 📊 التقرير المالي الكامل")
    if df is None or df.empty:
        st.info("ℹ️ لا توجد صفقات"); return

    df = compute_pips(df); df = compute_dollar_pnl(df, lot=lot_size)
    rc = next((c for c in ["Result", "Head Result"] if c in df.columns), None)
    if rc is None: st.warning("⚠️ لا عمود نتيجة"); return

    s = df[rc].astype(str).str.upper()
    w_df = df[s.str.contains("WIN")]; l_df = df[s.str.contains("LOSS")]
    o_df = df[s.str.contains("OPEN")]; t_df = df[s.str.contains("TIMEOUT")]
    b_df = df[s.str.contains("BREAKEVEN")]

    w, l, o, t, b = len(w_df), len(l_df), len(o_df), len(t_df), len(b_df)
    total = len(df); closed = w + l
    wr = round(w / closed * 100, 1) if closed else 0
    lr = round(l / closed * 100, 1) if closed else 0

    wp = w_df["Pips"].dropna().sum() if not w_df.empty else 0
    lp = l_df["Pips"].dropna().sum() if not l_df.empty else 0
    wu = w_df["PnL_USD"].dropna().sum() if not w_df.empty else 0
    lu = l_df["PnL_USD"].dropna().sum() if not l_df.empty else 0
    net_p = wp + lp; net_u = wu + lu
    pf = round(abs(wu / lu), 2) if lu != 0 else float("inf")

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
    k8.metric("⚖️ تعادل", b)

    if wr >= 60 and pf >= 1.5: st.success("🌟 استراتيجية ممتازة")
    elif wr >= 50 and pf >= 1.2: st.success("✅ استراتيجية جيدة")
    elif wr >= 40 and pf >= 1.0: st.warning("🟡 استراتيجية مقبولة")
    else: st.error("🔴 استراتيجية ضعيفة")

    # ═══════════════════════════════════════════════════════════════════════
    # 🔍 تحليل الخسائر (القاسم المشترك)
    # ═══════════════════════════════════════════════════════════════════════
    if l > 0:
        st.markdown("---")
        st.markdown("### 🔍 تحليل الخسائر (القاسم المشترك)")
        c1, c2, c3 = st.columns(3)
        
        if "Loss Category" in l_df.columns and not l_df["Loss Category"].dropna().empty:
            common_cat = l_df["Loss Category"].mode().iloc[0]
            reason_text = REASON_MAP.get(common_cat, {}).get("reason", common_cat) if REASON_MAP else common_cat
            c1.metric("🚩 السبب الأكثر شيوعاً", reason_text)
        else:
            c1.metric("🚩 السبب الأكثر شيوعاً", "غير محدد")
            
        c2.metric("📉 متوسط الوصول للهدف", f"{l_df['Max Reach %'].mean():.1f}%")
        c3.metric("📏 متوسط النقاط الخاسرة", f"{l_df['Pips'].mean():.1f}")

    # ═══════════════════════════════════════════════════════════════════════
    # 🧠 التوصيات والحلول (من محرك التشخيص)
    # ═══════════════════════════════════════════════════════════════════════
    if diagnose_filters is not None and raw_df is not None and not raw_df.empty:
        st.markdown("---")
        st.markdown("### 🧠 توصيات وحلول الثغرات المستخرجة من البيانات")
        with st.spinner("جاري تحليل الثغرات..."):
            try:
                diag = diagnose_filters(raw_df, interval=interval, symbol=symbol)
                if diag and diag.get("smart_diagnosis"):
                    diag_smart = diag["smart_diagnosis"]
                    st.info(f"**الحكم النهائي:** {diag_smart.get('verdict', '—')}")
                    
                    action_plan = diag_smart.get("action_plan", [])
                    if action_plan:
                        for action in action_plan:
                            st.warning(action)
                    
                    with st.expander("📋 تفاصيل تشخيصية إضافية"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write("**توزيع الخسائر:**")
                            st.json(diag_smart.get("loss_breakdown", {}))
                        with col_b:
                            st.write("**إحصائيات الأرباح:**")
                            st.json(diag_smart.get("win_breakdown", {}))
            except Exception as e:
                st.caption(f"⚠️ تعذر تشغيل التشخيص التلقائي: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # 📥 زر تنزيل البيانات
    # ═══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 تنزيل بيانات الدورة (CSV)",
        data=csv,
        file_name=f"backtest_{symbol}_{period}.csv",
        mime="text/csv",
        use_container_width=True,
        type="primary"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 💰 Risk Calculator + Calculator
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

    # حساب النقاط الصافية
    try:
        pip = pip_size_for(sel)
        net_points = abs(float(tp_p) - float(entry)) / pip
        st.metric("🎯 النقاط الصافية للهدف (TP)", f"{net_points:.1f} نقطة")
    except Exception:
        pass

    chk = check_risk_limit(entry, sl_p, lot, sel, capital, risk_pct)
    try:
        rd = abs(float(entry) - float(sl_p)); rw = abs(float(tp_p) - float(entry))
        rr = round(rw / rd, 2) if rd > 0 else "—"
    except Exception: rr = "—"

    if chk["allowed"]: st.success("### ✅ مقبولة")
    else: st.error("### ❌ مرفوضة")

    m1, m2, m3 = st.columns(3)
    m1.metric("💸 المخاطرة", f"${chk['risk_usd']:,.2f}" if chk['risk_usd'] else "—")
    m2.metric("📊 النسبة", f"{chk['risk_pct_actual']}%" if chk['risk_pct_actual'] else "—")
    m3.metric("⚖️ R:R", f"1:{rr}" if rr != "—" else "—")
    st.info(f"**التفاصيل:** {chk['message']}")

    # ═══════════════════════════════════════════════════════════════════════
    # 🧮 حاسبة حسابية
    # ═══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### 🧮 حاسبة حسابية")
    st.caption("أدخل رقمين ثم اختر العملية")

    calc_key = f"{unique_id}_calc_result"
    if calc_key not in st.session_state:
        st.session_state[calc_key] = 0.0

    c_a, c_b = st.columns(2)
    with c_a:
        num_a = st.number_input("🔢 الرقم الأول:",
            value=float(st.session_state.get(f"{unique_id}_calc_a", 0.0)),
            step=1.0, format="%.4f", key=f"{unique_id}_calc_a")
    with c_b:
        num_b = st.number_input("🔢 الرقم الثاني:",
            value=float(st.session_state.get(f"{unique_id}_calc_b", 0.0)),
            step=1.0, format="%.4f", key=f"{unique_id}_calc_b")

    op1, op2, op3, op4 = st.columns(4)
    result_val = None; op_symbol = ""

    with op1:
        if st.button("➕ جمع", use_container_width=True, key=f"{unique_id}_calc_add"):
            result_val = num_a + num_b; op_symbol = "+"
    with op2:
        if st.button("➖ طرح", use_container_width=True, key=f"{unique_id}_calc_sub"):
            result_val = num_a - num_b; op_symbol = "−"
    with op3:
        if st.button("✖️ ضرب", use_container_width=True, key=f"{unique_id}_calc_mul"):
            result_val = num_a * num_b; op_symbol = "×"
    with op4:
        if st.button("➗ قسمة", use_container_width=True, key=f"{unique_id}_calc_div"):
            if num_b != 0:
                result_val = num_a / num_b; op_symbol = "÷"
            else:
                st.error("⚠️ لا يمكن القسمة على صفر")

    if result_val is not None:
        st.session_state[calc_key] = result_val
        st.session_state[f"{unique_id}_calc_last_op"] = op_symbol
        st.session_state[f"{unique_id}_calc_last_a"] = num_a
        st.session_state[f"{unique_id}_calc_last_b"] = num_b

    last_op = st.session_state.get(f"{unique_id}_calc_last_op", "")
    last_a = st.session_state.get(f"{unique_id}_calc_last_a", 0)
    last_b = st.session_state.get(f"{unique_id}_calc_last_b", 0)
    current_result = st.session_state.get(calc_key, 0.0)

    if last_op:
        st.success(f"### = `{current_result:.4f}`  ({last_a:.4f} {last_op} {last_b:.4f})")
    else:
        st.info(f"### النتيجة: `{current_result:.4f}`")

    ax1, ax2, ax3 = st.columns(3)
    with ax1:
        if st.button("↩️ مسح", use_container_width=True, key=f"{unique_id}_calc_clear"):
            st.session_state[calc_key] = 0.0
            st.session_state[f"{unique_id}_calc_last_op"] = ""
            st.session_state[f"{unique_id}_calc_a"] = 0.0
            st.session_state[f"{unique_id}_calc_b"] = 0.0
            st.rerun()
    with ax2:
        if st.button("📋 للدخول", use_container_width=True, key=f"{unique_id}_calc_copy_entry"):
            st.session_state[f"{unique_id}_e_{sel}"] = float(current_result)
            st.rerun()
    with ax3:
        if st.button("📋 للوت", use_container_width=True, key=f"{unique_id}_calc_copy_lot"):
            st.session_state[f"{unique_id}_lot_{sel}"] = max(0.0001, float(current_result))
            st.rerun()

    st.markdown("##### ⚡ عمليات سريعة")
    q1, q2, q3, q4, q5, q6 = st.columns(6)
    quick_ops = [("×2", "*2"), ("÷2", "/2"), ("×3", "*3"),
                 ("÷3", "/3"), ("+10%", "*1.10"), ("-10%", "*0.90")]
    for col, (label, op) in zip([q1,q2,q3,q4,q5,q6], quick_ops):
        with col:
            if st.button(label, use_container_width=True, key=f"{unique_id}_calc_q_{label}"):
                if op == "*2": r = current_result * 2
                elif op == "/2": r = current_result / 2
                elif op == "*3": r = current_result * 3
                elif op == "/3": r = current_result / 3
                elif op == "*1.10": r = current_result * 1.10
                else: r = current_result * 0.90
                st.session_state[calc_key] = r
                st.session_state[f"{unique_id}_calc_last_op"] = label
                st.session_state[f"{unique_id}_calc_last_a"] = current_result
                st.session_state[f"{unique_id}_calc_last_b"] = 0
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Session State
# ══════════════════════════════════════════════════════════════════════════════
for k, v in [
    ("current_symbol", "EURUSD=X"),
    ("status_summary", "⚡ H&S Analyzer"),
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

    st.markdown("### 🧪 مختبر H&S")

    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"],
        horizontal=True, key="bt_scan_mode")

    if bt_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="EURUSD=X", key="bt_sym")]
    else:
        av = get_available_symbols()
        dp = [s for s in st.session_state.get("bt_picked_symbols", []) if s in av]
        picked = st.multiselect("🔽 اختر:", av, default=dp, key="bt_multi")
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
                
                # حفظ البيانات دائماً حتى لو لم توجد صفقات
                dfs[sym] = df
                
                if trades:
                    tdf = pd.DataFrame(trades)
                    if "symbol" not in tdf.columns: tdf["symbol"] = sym
                    results.append({"symbol": sym, "trades_df": tdf, "total_signals": len(tdf)})
                else:
                    # إذا لم توجد صفقات، نضيف إدخالاً فارغاً مع علامة تشخيص
                    results.append({
                        "symbol": sym, 
                        "trades_df": pd.DataFrame(), 
                        "total_signals": 0,
                        "no_signal_reason": "لم يتم العثور على أنماط مطابقة للفلاتر."
                    })
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

        # ═══════════════════════════════════════════════════════════════════
        # 🔍 قسم التشخيص: لماذا لم توجد إشارات؟
        # ═══════════════════════════════════════════════════════════════════
        no_signal_symbols = [r for r in rl if r.get("total_signals", 0) == 0]
        if no_signal_symbols:
            with st.expander("🔍 **تحليل: لماذا لم يتم العثور على إشارات؟**", expanded=True):
                st.warning(f"تم فحص {len(no_signal_symbols)} أصل/أصول ولم يتم العثور على أي إشارة. إليك الأسباب المحتملة:")
                
                diag_sym = st.selectbox("اختر أصلاً لتحليل سبب عدم وجود إشارات:", [r["symbol"] for r in no_signal_symbols], key="diag_no_sig")
                if diag_sym and diag_sym in dfs_dict:
                    raw_d = dfs_dict[diag_sym]
                    if diagnose_no_signals is not None:
                        stats = diagnose_no_signals(raw_d, interval=interval)
                        if "error" in stats:
                            st.error(stats["error"])
                        else:
                            st.markdown(f"**نتائج تحليل الفلاتر لـ {diag_sym}:**")
                            
                            # عرض إحصائيات القمع (Funnel)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("إجمالي نقاط الـ Pivot", stats["total_pivots"])
                            c2.metric("نماذج أولية (6 نقاط)", stats["raw_candidates"])
                            c3.metric("نماذج مرت من الفلاتر", stats["passed"])
                            
                            st.markdown("#### 📊 تفصيل أسباب الرفض (Funnel):")
                            reasons = {
                                "rejected_pattern_structure": "هيكل النموذج غير مطابق (L-H-L-H-L-H)",
                                "rejected_time_filter": "الوقت بين القمم/القيعان أقل من الحد الأدنى",
                                "rejected_prior_trend": "الاتجاه السابق لا يتوافق مع النموذج (انعكاس/استمرار)",
                                "rejected_shoulder_diff": "الفرق بين الكتفين أكبر من المسموح",
                                "rejected_head_proportion": "الرأس ليس بارزاً بما فيه الكفاية",
                                "rejected_neckline_diff": "خط العنق غير مستوٍ",
                                "rejected_pattern_duration": "مدة النموذج أطول من الحد الأقصى",
                                "rejected_no_breakout": "لم يحدث اختراق لخط العنق",
                                "rejected_breakout_confirm": "الاختراق لم يتأكد بنسبة كافية",
                                "rejected_max_gap": "المسافة بين الكتف والاختراق كبيرة جداً",
                                "rejected_live_limit": "الاختراق قديم جداً (تجاوز 10 شموع)",
                                "rejected_right_shoulder_high": "الكتف الأيمن ليس أعلى نقطة بعد الرأس",
                            }
                            
                            chart_data = []
                            for k, v in stats.items():
                                if k.startswith("rejected_") and v > 0:
                                    chart_data.append({"السبب": reasons.get(k, k), "العدد": v})
                            
                            if chart_data:
                                st.dataframe(pd.DataFrame(chart_data).sort_values("العدد", ascending=False), use_container_width=True)
                                
                                # التوصيات المقترحة
                                st.markdown("#### 💡 توصيات لتحسين الإعدادات بناءً على البيانات:")
                                top_reason = max(chart_data, key=lambda x: x["العدد"])["السبب"]
                                
                                if "مدة النموذج" in top_reason:
                                    st.info(f"🔧 **الحل:** النموذج يستغرق وقتاً طويلاً. قم بزيادة `_get_max_pattern_duration` في `engine.py` (مثلاً لـ 1h اجعلها 150 بدلاً من 100)، أو قلل `ZIGZAG_DEPTH` إلى 10.")
                                elif "خط العنق" in top_reason:
                                    st.info(f"🔧 **الحل:** خط العنق غير مستوٍ. قم بزيادة `NECKLINE_DIFF_MAX_RATIO` في `engine.py` من 0.10 إلى 0.25 مثلاً.")
                                elif "الرأس ليس بارزاً" in top_reason:
                                    st.info(f"🔧 **الحل:** الرأس غير عميق. قم بتقليل `HEAD_PROPORTION_MIN_RATIO` في `engine.py` من 0.15 إلى 0.10.")
                                elif "الفرق بين الكتفين" in top_reason:
                                    st.info(f"🔧 **الحل:** الكتفان غير متساويين. قم بزيادة `SHOULDER_DIFF_MAX_RATIO` في `engine.py` من 0.35 إلى 0.50.")
                                elif "الاتجاه السابق" in top_reason:
                                    st.info(f"🔧 **الحل:** فلتر الاتجاه السابق يرفض النماذج. يمكنك تعطيل `ENABLE_REVERSAL` أو `ENABLE_CONTINUATION` مؤقتاً لمعرفة أي نوع يسبب الرفض، أو توسيع نطاق التاريخ.")
                                elif "هيكل النموذج" in top_reason:
                                    st.info(f"🔧 **الحل:** قم بتقليل `ZIGZAG_DEPTH` إلى 8 أو 10 لالتقاط المزيد من القمم/القيعان.")
                                elif "لم يحدث اختراق" in top_reason:
                                    st.info(f"🔧 **الحل:** لا يوجد اختراق لخط العنق في الفترة المحددة. قم بتوسيع نطاق التاريخ أو تقليل `BREAKOUT_MIN_PCT`.")
                                elif "الكتف الأيمن" in top_reason:
                                    st.info(f"🔧 **الحل:** السعر تجاوز الكتف الأيمن بعد الرأس. هذا الفلتر صارم جداً، إذا تكرر كثيراً يمكنك إزالته من كود `engine.py`.")
                                else:
                                    st.info(f"🔧 **الحل:** قم بمراجعة الإعدادات في `CONFIG` أو قم بتوسيع نطاق التاريخ.")
                            else:
                                st.success("✅ لم يتم رفض أي نموذج بسبب الفلاتر، ولكن ربما لا توجد بيانات كافية لتكوين نماذج في هذه الفترة.")
                    else:
                        st.warning("⚠️ دالة التشخيص غير متوفرة في `engine.py`.")

        all_dfs = [i["trades_df"] for i in rl if "trades_df" in i and not i["trades_df"].empty]
        if all_dfs:
            comb = pd.concat(all_dfs, ignore_index=True)
            
            # استخدام التبويبات لتنظيم المحتوى
            tab1, tab2, tab3 = st.tabs(["📊 التقرير المالي", "📉 الرسوم البيانية والصفقات", "🧠 التشخيص والحلول"])
            
            with tab1:
                render_financial_report(comb, lot_size=lot,
                                       symbol="كل الأصول", period=pd_disp)

            with tab2:
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
                    st.warning(f"⚠️ **{sym}** — لا توجد أنماط")
                else:
                    st.markdown(f"### 📊 {sym} — {len(tdf)} إشارة")

                    last = tdf.iloc[-1]
                    st.session_state["active_signal_symbol"] = sym
                    st.session_state["active_signal_entry"] = last.get("Entry Price") or last.get("Entry")
                    st.session_state["active_signal_sl"] = last.get("Stop Loss") or last.get("SL")
                    st.session_state["active_signal_tp"] = last.get("Take Profit") or last.get("TP")

                    if st.session_state.get("_last_sym") != sym:
                        st.session_state.signal_index = len(tdf) - 1
                        st.session_state["_last_sym"] = sym

                    si = max(0, min(st.session_state.signal_index, len(tdf) - 1))
                    n1, n2, n3, n4, n5 = st.columns([1, 1, 3, 1, 1])
                    with n1:
                        if st.button("⏮️", use_container_width=True, key="b1"): st.session_state.signal_index = 0; st.rerun()
                    with n2:
                        if st.button("◀", use_container_width=True, key="b2"): st.session_state.signal_index = max(0, si - 1); st.rerun()
                    with n3:
                        st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>إشارة {si+1} من {len(tdf)}</div>", unsafe_allow_html=True)
                    with n4:
                        if st.button("▶", use_container_width=True, key="b4"): st.session_state.signal_index = min(len(tdf)-1, si+1); st.rerun()
                    with n5:
                        if st.button("⏭️", use_container_width=True, key="b5"): st.session_state.signal_index = len(tdf)-1; st.rerun()

                    cur = tdf.iloc[si]
                    ptype = cur.get("Pattern Type", "—")
                    icon = "🔄" if ptype == "Reversal" else "➡️" if ptype == "Continuation" else "📊"
                    st.markdown(f"**{icon} النوع:** {ptype}")

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🎯 الدخول", f"{cur.get('Entry Price', '—')}")
                    m2.metric("🛑 SL", f"{cur.get('Stop Loss', '—')}")
                    m3.metric("🏆 TP", f"{cur.get('Take Profit', '—')}")
                    m4.metric("📊 النتيجة", f"{cur.get('Result', '—')}")

                    if cur.get("Trade Recommendation"):
                        st.info(cur["Trade Recommendation"])

                    if sym in dfs_dict and not dfs_dict[sym].empty:
                        df_chart = dfs_dict[sym].copy()
                        df_chart["EMA50"] = df_chart["Close"].ewm(span=50, adjust=False).mean()
                        df_chart["EMA200"] = df_chart["Close"].ewm(span=200, adjust=False).mean()

                        fig = go.Figure(data=[go.Candlestick(
                            x=df_chart.index,
                            open=df_chart["Open"], high=df_chart["High"],
                            low=df_chart["Low"], close=df_chart["Close"],
                            name="السعر")])
                        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA50"],
                            line=dict(color="orange", width=1.2), name="EMA 50"))
                        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA200"],
                            line=dict(color="blue", width=1.2), name="EMA 200"))

                        draw_hs_pattern(fig, cur, df_chart)

                        x_range = None
                        nodes = cur.get("nodes", [])
                        if nodes and len(nodes) >= 6:
                            try:
                                ps = nodes[0][0]; pe = nodes[-1][0]
                                span = pe - ps
                                xmin = ps - span * 1.0
                                xmax = pe + span * 1.5
                                if xmin < df_chart.index[0]: xmin = df_chart.index[0]
                                if xmax > df_chart.index[-1]: xmax = df_chart.index[-1]
                                x_range = [xmin, xmax]
                            except Exception:
                                x_range = None

                        fig.update_layout(
                            template="plotly_white", height=850, autosize=True,
                            margin=dict(l=50, r=15, t=40, b=50),
                            xaxis_rangeslider_visible=False, dragmode="pan",
                            hovermode="x unified",
                            yaxis=dict(side="left", automargin=True,
                                       tickfont=dict(size=11, color="#333"),
                                       showgrid=True, gridcolor="#EEEEEE", zeroline=False),
                            xaxis=dict(automargin=True, tickfont=dict(size=10),
                                       showgrid=True, gridcolor="#F5F5F5",
                                       rangeslider=dict(visible=False),
                                       fixedrange=False, range=x_range),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                        xanchor="center", x=0.5,
                                        bgcolor="rgba(255,255,255,0.9)",
                                        bordercolor="#DDDDDD", borderwidth=1),
                        )
                        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

                    with st.expander("📋 التفاصيل", expanded=False):
                        for col in ["Entry Date", "Exit Date", "Bias", "Pattern Type",
                                    "Result", "Entry Price", "Stop Loss", "Take Profit",
                                    "Structural SL", "Safe SL", "TP Factor Used",
                                    "Max Reach %", "Max Extension %", "SL Safety %",
                                    "Breakeven Activated", "Trailing Stage", "Loss Category"]:
                            if col in cur:
                                st.text(f"{col}: {cur[col]}")

            with tab3:
                st.markdown("### 🧠 تشخيص الإستراتيجية")
                if st.session_state.backtest_dfs:
                    sym_diag = st.selectbox("اختر الأصل للتشخيص:", list(st.session_state.backtest_dfs.keys()))
                    if sym_diag:
                        raw_d = st.session_state.backtest_dfs[sym_diag]
                        if diagnose_filters:
                            with st.spinner("جاري تحليل الثغرات..."):
                                diag = diagnose_filters(raw_d, interval=interval, symbol=sym_diag)
                                if diag and diag.get("smart_diagnosis"):
                                    diag_smart = diag["smart_diagnosis"]
                                    st.info(f"**الحكم النهائي:** {diag_smart.get('verdict', '—')}")
                                    action_plan = diag_smart.get("action_plan", [])
                                    if action_plan:
                                        for action in action_plan:
                                            st.warning(action)
                                    
                                    with st.expander("📋 تفاصيل تشخيصية إضافية"):
                                        col_a, col_b = st.columns(2)
                                        with col_a:
                                            st.write("**توزيع الخسائر:**")
                                            st.json(diag_smart.get("loss_breakdown", {}))
                                        with col_b:
                                            st.write("**إحصائيات الأرباح:**")
                                            st.json(diag_smart.get("win_breakdown", {}))
                                else:
                                    st.info("لا توجد بيانات كافية للتشخيص.")
                        else:
                            st.warning("⚠️ محرك التشخيص (diagnose_filters) غير متوفر.")


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
        picked = st.multiselect("🔽 اختر:", av, default=dp, key="live_multi")
        st.session_state["live_picked_symbols"] = picked
        symbols = picked
        if not symbols: st.warning("⚠️ اختر عملة")

    c1, c2 = st.columns(2)
    interval = c1.selectbox("⏱️ الإطار:", ALL_GLOBAL_INTERVALS, index=9, key="live_int")
    period = c2.selectbox("📅 النطاق:",
        ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"],
        index=4, key="live_period")

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
                if st.button("⏮️", use_container_width=True, key="l1"): st.session_state.signal_index = 0; st.rerun()
            with n2:
                if st.button("◀", use_container_width=True, key="l2"): st.session_state.signal_index = max(0, si - 1); st.rerun()
            with n3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>إشارة {si+1} من {len(sigs)}</div>", unsafe_allow_html=True)
            with n4:
                if st.button("▶", use_container_width=True, key="l4"): st.session_state.signal_index = min(len(sigs)-1, si+1); st.rerun()
            with n5:
                if st.button("⏭️", use_container_width=True, key="l5"): st.session_state.signal_index = len(sigs)-1; st.rerun()

            ar = sigs[si]["result"]
            asy = ar.get("symbol", "N/A")

            e1, e2, e3 = st.columns(3)
            e1.metric("🎯 الدخول", f"{ar.get('entry', 0)}")
            e2.metric("🛑 SL", f"{ar.get('sl', 0)}")
            e3.metric("🏆 TP", f"{ar.get('tp', 0)}")

            if ar.get("Trade Recommendation"):
                st.info(ar["Trade Recommendation"])

            st.session_state["active_signal_symbol"] = asy
            st.session_state["active_signal_entry"] = ar.get("entry")
            st.session_state["active_signal_sl"] = ar.get("sl")
            st.session_state["active_signal_tp"] = ar.get("tp")

            dfo = ar.get("df")
            if dfo is not None and not dfo.empty:
                df_chart = dfo.copy()
                df_chart["EMA50"] = df_chart["Close"].ewm(span=50, adjust=False).mean()
                df_chart["EMA200"] = df_chart["Close"].ewm(span=200, adjust=False).mean()

                fig = go.Figure(data=[go.Candlestick(
                    x=df_chart.index,
                    open=df_chart["Open"], high=df_chart["High"],
                    low=df_chart["Low"], close=df_chart["Close"],
                    name="السعر")])
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA50"],
                    line=dict(color="orange", width=1.2), name="EMA 50"))
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA200"],
                    line=dict(color="blue", width=1.2), name="EMA 200"))

                draw_hs_pattern(fig, ar, df_chart)

                x_range = None
                nodes = ar.get("nodes", [])
                if nodes and len(nodes) >= 6:
                    try:
                        ps = nodes[0][0]; pe = nodes[-1][0]
                        span = pe - ps
                        xmin = ps - span * 1.0
                        xmax = pe + span * 1.5
                        if xmin < df_chart.index[0]: xmin = df_chart.index[0]
                        if xmax > df_chart.index[-1]: xmax = df_chart.index[-1]
                        x_range = [xmin, xmax]
                    except Exception:
                        x_range = None

                fig.update_layout(
                    template="plotly_white", height=850, autosize=True,
                    margin=dict(l=50, r=15, t=40, b=50),
                    xaxis_rangeslider_visible=False, dragmode="pan",
                    hovermode="x unified",
                    yaxis=dict(side="left", automargin=True,
                               tickfont=dict(size=11, color="#333"),
                               showgrid=True, gridcolor="#EEEEEE", zeroline=False),
                    xaxis=dict(automargin=True, tickfont=dict(size=10),
                               showgrid=True, gridcolor="#F5F5F5",
                               rangeslider=dict(visible=False),
                               fixedrange=False, range=x_range),
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
with st.expander("💰 حاسبة المخاطرة المتقدمة + 🧮 حاسبة حسابية", expanded=False):
    render_advanced_risk_calculator(unique_id="end")
