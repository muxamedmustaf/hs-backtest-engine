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


# ══════════════════════════════════════════════════════════════════════════════
# ✅ compute_pips — النسخة المُصلَحة (بدون TypeError)
# ══════════════════════════════════════════════════════════════════════════════
def compute_pips(trades_df):
    if trades_df is None or trades_df.empty:
        return trades_df
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
        sl    = pick(row, ["Stop Loss", "SL", "sl"])
        tp    = pick(row, ["Take Profit", "TP", "tp"])
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias

        # ✅ pips — محمي من None
        pips = None
        if entry is not None and exit_ is not None:
            pips = (entry - exit_) / pip if is_sell else (exit_ - entry) / pip

        # ✅ risk — محمي
        risk = None
        if entry is not None and sl is not None:
            risk = abs((sl - entry) / pip if is_sell else (entry - sl) / pip)

        # ✅ reward — محمي
        reward = None
        if entry is not None and tp is not None:
            reward = abs((entry - tp) / pip if is_sell else (tp - entry) / pip)

        rr = round(reward / risk, 2) if (risk and reward and risk > 0) else None

        pips_l.append(round(pips, 1) if pips is not None else None)
        risk_l.append(round(risk, 1) if risk is not None else None)
        reward_l.append(round(reward, 1) if reward is not None else None)
        rr_l.append(rr)

    df["Pips"]        = pips_l
    df["Risk_Pips"]   = risk_l
    df["Reward_Pips"] = reward_l
    df["RR_Ratio"]    = rr_l
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ✅ compute_dollar_pnl — النسخة المُصلَحة
# ══════════════════════════════════════════════════════════════════════════════
def compute_dollar_pnl(trades_df, lot=0.01):
    if trades_df is None or trades_df.empty:
        return trades_df
    df = trades_df.copy()
    usd_list, pct_list = [], []

    for _, row in df.iterrows():
        sym = str(row.get("symbol") or row.get("Symbol") or "").upper()
        entry = row.get("Entry Price") or row.get("Entry")
        exit_ = row.get("Exit Price") or row.get("Exit")
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias

        try:
            entry_f = float(entry); exit_f = float(exit_)
        except (TypeError, ValueError):
            usd_list.append(None); pct_list.append(None); continue

        price_move = (exit_f - entry_f) if not is_sell else (entry_f - exit_f)

        if any(x in sym for x in ["BTC", "ETH"]):
            pnl_usd = price_move * lot * 1
        elif any(x in sym for x in ["US30", "NAS", "SPX", "US100", "US500"]):
            pnl_usd = price_move * lot * 1
        elif "XAU" in sym or "GC=F" in sym:
            pnl_usd = price_move * lot * 100
        elif "XAG" in sym or "SI=F" in sym:
            pnl_usd = price_move * lot * 5000
        else:
            if sym.endswith("USD"):
                pnl_usd = price_move * lot * 100000
            else:
                if exit_f == 0:
                    pnl_usd = None
                else:
                    pnl_usd = price_move * lot * 100000 / exit_f

        pct = (price_move / entry_f * 100) if entry_f else None

        usd_list.append(round(pnl_usd, 2) if pnl_usd is not None else None)
        pct_list.append(round(pct, 2) if pct is not None else None)

    df["PnL_USD"] = usd_list
    df["PnL_Pct"] = pct_list
    return df


def calculate_trade_risk_usd(entry, sl, lot, symbol):
    try:
        entry_f = float(entry); sl_f = float(sl); lot_f = float(lot)
    except (TypeError, ValueError): return None
    if entry_f == 0: return None
    price_move = abs(entry_f - sl_f)
    s = str(symbol).upper()
    if any(x in s for x in ["BTC", "ETH"]): return price_move * lot_f * 1
    if any(x in s for x in ["US30", "NAS", "SPX"]): return price_move * lot_f * 1
    if "XAU" in s or "GC=F" in s: return price_move * lot_f * 100
    if "XAG" in s or "SI=F" in s: return price_move * lot_f * 5000
    if s.endswith("USD"): return price_move * lot_f * 100000
    else:
        if entry_f == 0: return None
        return price_move * lot_f * 100000 / entry_f


def check_risk_limit(entry, sl, lot, symbol, capital, risk_pct):
    risk_usd = calculate_trade_risk_usd(entry, sl, lot, symbol)
    if risk_usd is None:
        return {"allowed": False, "risk_usd": None, "max_risk_usd": None,
                "risk_pct_actual": None, "message": "⚠️ لا يمكن حساب المخاطرة"}
    max_risk_usd = capital * (risk_pct / 100)
    risk_pct_actual = (risk_usd / capital * 100) if capital > 0 else 0
    allowed = risk_usd <= max_risk_usd
    if allowed:
        message = f"✅ مقبولة — المخاطرة {risk_usd:.2f}$ ({risk_pct_actual:.2f}%) ≤ الحد {max_risk_usd:.2f}$"
    else:
        message = f"❌ مرفوضة — المخاطرة {risk_usd:.2f}$ ({risk_pct_actual:.2f}%) > الحد {max_risk_usd:.2f}$"
    return {"allowed": allowed, "risk_usd": round(risk_usd, 2),
            "max_risk_usd": round(max_risk_usd, 2),
            "risk_pct_actual": round(risk_pct_actual, 2), "message": message}


def get_available_symbols():
    symbols_set = set(IC_MARKETS_SPECS.keys())
    try:
        for s in get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]:
            symbols_set.add(str(s).strip())
    except Exception: pass
    return sorted(list(symbols_set))


def get_last_known_price(symbol):
    if "backtest_dfs" in st.session_state:
        df = st.session_state.backtest_dfs.get(symbol)
        if df is not None and not df.empty:
            try: return float(df["Close"].iloc[-1])
            except Exception: pass
    return None


def _week_to_bars_label(interval):
    return "أسبوع واحد (7 أيام)"


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 draw_rectangle_pattern
# ══════════════════════════════════════════════════════════════════════════════
def draw_rectangle_pattern(fig, source):
    if source is None: return
    try:
        box = source.get("consolidation_box")
    except Exception:
        return
    if box is None: return
    x_start = int(box["x_start"]); x_end = int(box["x_end"])
    box_high = float(box["high"]); box_low = float(box["low"])

    fig.add_shape(type="rect", x0=x_start, y0=box_low, x1=x_end, y1=box_high,
                  line=dict(width=0), fillcolor="rgba(156, 39, 176, 0.07)", layer="below")
    fig.add_shape(type="line", x0=x_start, y0=box_high, x1=x_end, y1=box_high,
                  line=dict(color="#2962FF", width=4), layer="above")
    fig.add_shape(type="line", x0=x_start, y0=box_low, x1=x_end, y1=box_low,
                  line=dict(color="#FF5252", width=4), layer="above")
    fig.add_shape(type="line", x0=x_start, y0=box_low, x1=x_start, y1=box_high,
                  line=dict(color="#9C27B0", width=2, dash="dot"), layer="above")
    fig.add_shape(type="line", x0=x_end, y0=box_low, x1=x_end, y1=box_high,
                  line=dict(color="#9C27B0", width=2, dash="dot"), layer="above")

    top_nodes = source.get("top_nodes") or []
    bot_nodes = source.get("bot_nodes") or []
    if top_nodes:
        fig.add_trace(go.Scatter(x=[n[0] for n in top_nodes], y=[n[1] for n in top_nodes],
            mode="markers", name="قمم",
            marker=dict(size=13, color="#2962FF", symbol="circle",
                        line=dict(color="white", width=2.5)), showlegend=True))
    if bot_nodes:
        fig.add_trace(go.Scatter(x=[n[0] for n in bot_nodes], y=[n[1] for n in bot_nodes],
            mode="markers", name="قيعان",
            marker=dict(size=13, color="#FF5252", symbol="circle",
                        line=dict(color="white", width=2.5)), showlegend=True))

    entry_nodes = source.get("nodes") or []
    if entry_nodes:
        fig.add_trace(go.Scatter(x=[n[0] for n in entry_nodes], y=[n[1] for n in entry_nodes],
            mode="markers", name="الدخول",
            marker=dict(size=22, color="#FFC107", symbol="star",
                        line=dict(color="black", width=2)), showlegend=True))

    arrow = source.get("arrow")
    if isinstance(arrow, dict):
        col = "#00C853" if arrow.get("direction") == "BUY" else "#D50000"
        fig.add_annotation(x=arrow["x1"], y=arrow["y1"], ax=arrow["x0"], ay=arrow["y0"],
                           xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=2.5, arrowwidth=4,
                           arrowcolor=col, opacity=0.95, text="TP",
                           font=dict(color=col, size=13))


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Realtime Actions
# ══════════════════════════════════════════════════════════════════════════════
def render_realtime_actions(trades_df, is_live=False):
    st.markdown("### 🎯 التصرفات المطلوبة الآن")
    st.caption("إجراءات محدّدة لصفقاتك المفتوحة")
    if trades_df is None or trades_df.empty:
        st.info("ℹ️ لا توجد صفقات للتحليل")
        return

    actions = []
    relevant = trades_df.index.tolist() if is_live else trades_df.tail(5).index.tolist()

    for idx in relevant:
        row = trades_df.loc[idx]
        sym = row.get("symbol") or row.get("Symbol") or "?"
        result = str(row.get("Result", "")).upper()
        if not is_live and result in ["WIN", "LOSS", "TIMEOUT", "BREAKEVEN"]: continue
        try:
            entry_f = float(row.get("Entry Price") or row.get("Entry") or 0)
            sl_f = float(row.get("Stop Loss") or row.get("SL") or 0)
            tp_f = float(row.get("Take Profit") or row.get("TP") or 0)
        except (TypeError, ValueError): continue
        if entry_f == 0 or sl_f == 0 or tp_f == 0: continue

        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_bearish = "BEAR" in bias or "SELL" in bias
        progress = row.get("Max Reach %", 0) or 0
        if progress < 15: continue

        total_tp = abs(tp_f - entry_f)
        if progress >= 80:
            priority = "🔴 عاجل"; action = "إغلاق 50% + Trailing 60%"
            new_sl = entry_f + (0.6 * total_tp * (-1 if is_bearish else 1)); guaranteed = "60%"
        elif progress >= 50:
            priority = "🟠 عالي"; action = "تفعيل Trailing 30%"
            new_sl = entry_f + (0.3 * total_tp * (-1 if is_bearish else 1)); guaranteed = "30%"
        elif progress >= 25:
            priority = "🟡 متوسط"; action = "نقل SL إلى التعادل"
            new_sl = entry_f; guaranteed = "0%"
        else: continue

        actions.append({
            "الأولوية": priority, "الزوج": sym, "الوصول": f"{progress:.1f}%",
            "الإجراء": action, "SL الجديد": f"{new_sl:.5f}",
            "الربح المضمون": guaranteed,
            "_priority": {"🔴 عاجل": 0, "🟠 عالي": 1, "🟡 متوسط": 2}.get(priority, 99),
        })

    if not actions:
        st.success("✅ لا توجد صفقات تحتاج تصرفًا الآن")
        return

    actions.sort(key=lambda x: x["_priority"])
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 عاجل", sum(1 for a in actions if a["الأولوية"] == "🔴 عاجل"))
    c2.metric("🟠 عالي", sum(1 for a in actions if a["الأولوية"] == "🟠 عالي"))
    c3.metric("🟡 متوسط", sum(1 for a in actions if a["الأولوية"] == "🟡 متوسط"))

    for a in actions:
        msg = f"**{a['الأولوية']} | {a['الزوج']}** — {a['الإجراء']} — الوصول: {a['الوصول']} — SL: `{a['SL الجديد']}`"
        if a["الأولوية"] == "🔴 عاجل": st.error(msg)
        elif a["الأولوية"] == "🟠 عالي": st.warning(msg)
        else: st.info(msg)


# ══════════════════════════════════════════════════════════════════════════════
# 💰 Risk Calculator
# ══════════════════════════════════════════════════════════════════════════════
def render_advanced_risk_calculator(unique_id="main"):
    st.markdown("### 💰 حاسبة المخاطرة المتقدمة")
    st.caption("احسب حجم اللوت الآمن قبل الدخول")

    st.markdown("#### 1️⃣ الإعدادات العامة")
    c1, c2, c3 = st.columns(3)
    with c1:
        capital = st.number_input("💵 رأس المال ($):", min_value=10.0, max_value=10_000_000.0,
            value=1000.0, step=100.0, format="%.2f", key=f"{unique_id}_capital")
    with c2:
        risk_pct = st.selectbox("📊 نسبة المخاطرة (%):",
            options=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], index=4, key=f"{unique_id}_riskpct")
    max_risk_usd = capital * (risk_pct / 100)
    with c3:
        st.metric("🛑 الحد الأقصى", f"${max_risk_usd:,.2f}")

    st.markdown("---")
    st.markdown("#### 2️⃣ اختيار العملة")
    available_symbols = get_available_symbols()
    search_term = st.text_input("🔍 ابحث:", placeholder="EUR, GBP, BTC...",
        key=f"{unique_id}_search")
    if search_term:
        available_symbols = [s for s in available_symbols if search_term.upper() in s.upper()]
    if not available_symbols:
        st.warning("⚠️ لا توجد عملات مطابقة."); return

    active_signal_sym = st.session_state.get("active_signal_symbol")
    default_idx = 0
    if active_signal_sym and active_signal_sym in available_symbols:
        default_idx = available_symbols.index(active_signal_sym)

    col_sym, col_lot = st.columns([2, 1])
    with col_sym:
        selected_symbol = st.selectbox("🔽 العملة:", options=available_symbols,
            index=default_idx, key=f"{unique_id}_symbol")
    with col_lot:
        default_lot = get_default_lot_for_symbol(selected_symbol)
        custom_lot = st.number_input("💰 اللوت:", min_value=0.0001, max_value=100.0,
            value=default_lot, step=0.01, format="%.2f", key=f"{unique_id}_lot_{selected_symbol}")

    st.markdown("#### 3️⃣ بيانات الصفقة")
    if active_signal_sym == selected_symbol and st.session_state.get("active_signal_entry"):
        default_entry = float(st.session_state["active_signal_entry"])
        default_sl = float(st.session_state.get("active_signal_sl") or default_entry * 1.01)
        default_tp = float(st.session_state.get("active_signal_tp") or default_entry * 0.98)
        st.info(f"🔗 مُحمّل من الإشارة النشطة")
    else:
        last_price = get_last_known_price(selected_symbol)
        default_entry = float(last_price) if last_price else 1.0
        default_sl = default_entry * 1.01
        default_tp = default_entry * 0.98

    c_entry, c_sl, c_tp = st.columns(3)
    with c_entry:
        entry_price = st.number_input("📈 الدخول:", value=float(default_entry),
            format="%.5f", key=f"{unique_id}_entry_{selected_symbol}")
    with c_sl:
        sl_price = st.number_input("🛑 SL:", value=float(default_sl),
            format="%.5f", key=f"{unique_id}_sl_{selected_symbol}")
    with c_tp:
        tp_price = st.number_input("🏆 TP:", value=float(default_tp),
            format="%.5f", key=f"{unique_id}_tp_{selected_symbol}")

    c1_btn, c2_btn, c3_btn = st.columns(3)
    with c1_btn:
        if st.button("⚡ R:R = 1:2", key=f"{unique_id}_rr2_{selected_symbol}", use_container_width=True):
            new_tp = entry_price - 2 * (sl_price - entry_price) if sl_price > entry_price else entry_price + 2 * (entry_price - sl_price)
            st.session_state[f"{unique_id}_tp_{selected_symbol}"] = round(new_tp, 5); st.rerun()
    with c2_btn:
        if st.button("⚡ R:R = 1:3", key=f"{unique_id}_rr3_{selected_symbol}", use_container_width=True):
            new_tp = entry_price - 3 * (sl_price - entry_price) if sl_price > entry_price else entry_price + 3 * (entry_price - sl_price)
            st.session_state[f"{unique_id}_tp_{selected_symbol}"] = round(new_tp, 5); st.rerun()
    with c3_btn:
        if st.button("⚡ R:R = 1:1", key=f"{unique_id}_rr1_{selected_symbol}", use_container_width=True):
            new_tp = entry_price - (sl_price - entry_price) if sl_price > entry_price else entry_price + (entry_price - sl_price)
            st.session_state[f"{unique_id}_tp_{selected_symbol}"] = round(new_tp, 5); st.rerun()

    st.markdown("---")
    st.markdown("#### 4️⃣ النتيجة")
    check = check_risk_limit(entry_price, sl_price, custom_lot, selected_symbol, capital, risk_pct)

    try:
        risk_distance = abs(float(entry_price) - float(sl_price))
        reward_distance = abs(float(tp_price) - float(entry_price))
        rr = round(reward_distance / risk_distance, 2) if risk_distance > 0 else "—"
    except Exception: rr = "—"

    potential_profit_usd = None
    if check["risk_usd"] and isinstance(rr, (int, float)) and rr != "—":
        potential_profit_usd = round(check["risk_usd"] * rr, 2)

    if check["allowed"]: st.success("### ✅ مقبولة — ضمن حد المخاطرة")
    else: st.error("### ❌ مرفوضة — تجاوزت حد المخاطرة")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💸 المخاطرة", f"${check['risk_usd']:,.2f}" if check['risk_usd'] else "—")
    m2.metric("📊 النسبة الفعلية", f"{check['risk_pct_actual']}%" if check['risk_pct_actual'] else "—")
    m3.metric("⚖️ R:R", f"1:{rr}" if rr != "—" else "—")
    m4.metric("🎯 الربح المتوقع", f"${potential_profit_usd:,.2f}" if potential_profit_usd else "—")
    st.info(f"**التفاصيل:** {check['message']}")

    if not check["allowed"] and check["risk_usd"]:
        st.markdown("#### 💡 اقتراحات")
        suggested_lot = round(max(0.0001, custom_lot * (max_risk_usd / check["risk_usd"])), 4)
        st.warning(f"**اللوت المقترح:** `{suggested_lot}` — المخاطرة الجديدة: ${max_risk_usd:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# 📊 Financial Report
# ══════════════════════════════════════════════════════════════════════════════
def render_financial_report(trades_df, lot_size=0.01, symbol="—", period="—"):
    st.markdown("### 📊 التقرير المالي الكامل")
    if trades_df is None or trades_df.empty:
        st.info("ℹ️ لا توجد صفقات للتحليل"); return

    df = compute_pips(trades_df)
    df = compute_dollar_pnl(df, lot=lot_size)

    res_col = None
    for col in ["Result", "Head Result"]:
        if col in df.columns: res_col = col; break
    if res_col is None:
        st.warning("⚠️ عمود النتيجة غير موجود"); return

    res_series = df[res_col].astype(str).str.upper()
    wins_df = df[res_series.str.contains("WIN")]
    losses_df = df[res_series.str.contains("LOSS")]
    opens_df = df[res_series.str.contains("OPEN")]
    timeout_df = df[res_series.str.contains("TIMEOUT")]

    wins = len(wins_df); losses = len(losses_df); opens = len(opens_df); timeouts = len(timeout_df)
    total = len(df); closed = wins + losses
    win_rate = round(wins / closed * 100, 1) if closed > 0 else 0
    loss_rate = round(losses / closed * 100, 1) if closed > 0 else 0

    wins_pips = wins_df["Pips"].dropna().sum() if not wins_df.empty else 0
    losses_pips = losses_df["Pips"].dropna().sum() if not losses_df.empty else 0
    wins_usd = wins_df["PnL_USD"].dropna().sum() if not wins_df.empty else 0
    losses_usd = losses_df["PnL_USD"].dropna().sum() if not losses_df.empty else 0
    net_pips = wins_pips + losses_pips
    net_usd = wins_usd + losses_usd

    avg_win_pips = wins_df["Pips"].mean() if wins > 0 else 0
    avg_loss_pips = losses_df["Pips"].mean() if losses > 0 else 0
    avg_win_usd = wins_usd / wins if wins > 0 else 0
    avg_loss_usd = abs(losses_usd / losses) if losses > 0 else 0

    profit_factor = round(abs(wins_usd / losses_usd), 2) if losses_usd != 0 else float("inf")
    expectancy_pips = (net_pips / closed) if closed > 0 else 0
    expectancy_usd = (net_usd / closed) if closed > 0 else 0

    max_win_streak = 0; max_loss_streak = 0; cur_w = 0; cur_l = 0
    for r in res_series.tolist():
        if "WIN" in r: cur_w += 1; cur_l = 0; max_win_streak = max(max_win_streak, cur_w)
        elif "LOSS" in r: cur_l += 1; cur_w = 0; max_loss_streak = max(max_loss_streak, cur_l)
        else: cur_w = 0; cur_l = 0

    if not df["PnL_USD"].dropna().empty:
        pnl_series = df["PnL_USD"].dropna().cumsum()
        running_max = pnl_series.cummax()
        drawdown = pnl_series - running_max
        max_dd_usd = abs(drawdown.min()) if not drawdown.empty else 0
    else:
        max_dd_usd = 0

    st.markdown(f"#### 📍 الملخص — {symbol} · {period}")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 إجمالي الصفقات", total)
    k2.metric("✅ ناجحة", wins, delta=f"{win_rate}%")
    k3.metric("❌ خاسرة", losses, delta=f"{loss_rate}%", delta_color="inverse")
    k4.metric("⏳ مفتوحة", opens)

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("📏 إجمالي النقاط", f"{net_pips:+.1f}")
    k6.metric(f"💰 صافي الربح", f"${net_usd:+.2f}")
    k7.metric("⚖️ Profit Factor", f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞")
    k8.metric("📉 Max Drawdown", f"${max_dd_usd:.2f}")

    st.markdown("##### 📋 تفصيل الأداء")
    detail_df = pd.DataFrame([
        {"البند": "🟢 صفقات رابحة", "العدد": wins, "النقاط": round(wins_pips, 1),
         "بالدولار": round(wins_usd, 2), "المتوسط/صفقة": f"{avg_win_pips:+.1f} pts"},
        {"البند": "🔴 صفقات خاسرة", "العدد": losses, "النقاط": round(losses_pips, 1),
         "بالدولار": round(losses_usd, 2), "المتوسط/صفقة": f"{avg_loss_pips:+.1f} pts"},
        {"البند": "⏰ Timeout", "العدد": timeouts, "النقاط": "—", "بالدولار": "—", "المتوسط/صفقة": "—"},
        {"البند": "الصافي", "العدد": closed, "النقاط": round(net_pips, 1),
         "بالدولار": round(net_usd, 2), "المتوسط/صفقة": f"{expectancy_pips:+.1f} pts"},
    ])
    st.dataframe(detail_df, use_container_width=True, hide_index=True)

    st.markdown("##### 🎯 إحصاءات متقدمة")
    adv1, adv2, adv3, adv4 = st.columns(4)
    adv1.metric("📈 Expectancy (نقاط/صفقة)", f"{expectancy_pips:+.1f}")
    adv2.metric("💵 Expectancy ($/صفقة)", f"${expectancy_usd:+.2f}")
    adv3.metric("🔥 أطول سلسلة ربح", max_win_streak)
    adv4.metric("❄️ أطول سلسلة خسارة", max_loss_streak)

    avg_wl_ratio = (avg_win_usd / avg_loss_usd) if avg_loss_usd > 0 else 0
    st.info(f"📊 **متوسط الربح/الخسارة:** ${avg_win_usd:.2f} / ${avg_loss_usd:.2f} = **{avg_wl_ratio:.2f}x**")

    if win_rate >= 60 and profit_factor >= 1.5:
        st.success("🌟 **استراتيجية ممتازة** — نسبة ربح عالية + Profit Factor قوي")
    elif win_rate >= 50 and profit_factor >= 1.2:
        st.success("✅ **استراتيجية جيدة** — قابلة للاستخدام مع إدارة مخاطر صارمة")
    elif win_rate >= 40 and profit_factor >= 1.0:
        st.warning("🟡 **استراتيجية مقبولة** — تحتاج تحسينات")
    else:
        st.error("🔴 **استراتيجية ضعيفة** — لا يُنصح بالاعتماد عليها")


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
    ("signal_index", 0),
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
        ["سهم فردي", "🎯 مجموعة مخصصة"], horizontal=True, key="bt_scan_mode")

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
        end_date = f"{selected_year}-{selected_month:02d}-{last_day:02d}"
        period_label = f"{months_dict[selected_month]} {selected_year}"
    elif period_mode == "📅 نطاق مخصص":
        c1, c2 = st.columns(2)
        start_pick = c1.date_input("📅 من:", value=datetime.date(now.year, max(1, now.month-1), 1),
            min_value=datetime.date(now.year - 5, 1, 1), max_value=datetime.date.today(), key="bt_custom_start")
        end_pick = c2.date_input("📅 إلى:", value=datetime.date.today(),
            min_value=datetime.date(now.year - 5, 1, 1), max_value=datetime.date.today(), key="bt_custom_end")
        if start_pick < end_pick:
            start_date = start_pick.strftime("%Y-%m-%d"); end_date = end_pick.strftime("%Y-%m-%d")
            period_label = f"{start_date} → {end_date}"
    else:
        year_pick = st.columns(1)[0].selectbox("📅 السنة:", available_years, index=0, key="bt_full_year")
        start_date = f"{year_pick}-01-01"; end_date = f"{year_pick}-12-31"
        period_label = f"السنة {year_pick}"

    st.markdown("---")
    selected_interval = st.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=9, key="bt_interval")
    st.info(f"⏱️ **عمر المستطيل الأدنى:** {_week_to_bars_label(selected_interval)}")

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
        st.session_state.signal_index = 0
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
            combined_df = compute_dollar_pnl(combined_df, lot=lot_size)

            with st.expander("📊 التقرير المالي الشامل لكل الأصول", expanded=False):
                render_financial_report(combined_df, lot_size=lot_size,
                                       symbol="كل الأصول", period=period_display)

        if bt_scan_mode == "🎯 مجموعة مخصصة" and len(res_list) > 1:
            opts = [f"{i['symbol']} | إشارات: {i['total_signals']}" for i in res_list]
            active_item = res_list[opts.index(st.selectbox("👇 اختر الأصل:", opts))]
        else:
            active_item = res_list[0]

        active_sym = active_item["symbol"]
        trades_df = active_item["trades_df"]
        trades_df = compute_pips(trades_df)
        trades_df = compute_dollar_pnl(trades_df, lot=lot_size)
        st.session_state.current_symbol = active_sym

        if len(trades_df) == 0:
            st.warning(f"⚠️ **{active_sym}** — لا توجد مستطيلات أفقية مطابقة")
        else:
            st.markdown(f"### 📊 {active_sym} — {len(trades_df)} إشارة")

            if len(trades_df) > 0:
                last = trades_df.iloc[-1]
                st.session_state["active_signal_symbol"] = active_sym
                st.session_state["active_signal_entry"] = last.get("Entry Price") or last.get("Entry")
                st.session_state["active_signal_sl"] = last.get("Stop Loss") or last.get("SL")
                st.session_state["active_signal_tp"] = last.get("Take Profit") or last.get("TP")

            with st.expander(f"📊 تقرير مالي — {active_sym}", expanded=False):
                render_financial_report(trades_df, lot_size=lot_size,
                                       symbol=active_sym, period=period_display)

            with st.expander("🎯 التصرفات المطلوبة الآن", expanded=False):
                render_realtime_actions(trades_df, is_live=False)

            with st.expander("🔬 التقرير التشخيصي الذكي", expanded=False):
                if diagnose_filters is None:
                    st.error("⚠️ `diagnose_filters` غير متوفر")
                else:
                    try:
                        df_for_diag = dfs_dict.get(active_sym)
                        if df_for_diag is not None and not df_for_diag.empty:
                            diag = diagnose_filters(df_for_diag,
                                interval=selected_interval, symbol=active_sym)
                            if not diag.get("error"):
                                c1, c2, c3 = st.columns(3)
                                c1.metric("أنماط خام", diag["total_raw_candidates"])
                                c2.metric("بعد الفلاتر", diag["final_count"])
                                col_rate = diag['final_count'] / max(diag['total_raw_candidates'], 1) * 100
                                c3.metric("نسبة القبول", f"{round(col_rate, 1)}%")
                                smart = diag.get("smart_diagnosis", {})
                                if smart.get("verdict"):
                                    st.markdown(f"### 🎯 {smart['verdict']}")
                                if smart.get("action_plan"):
                                    for item in smart["action_plan"]:
                                        st.info(item)
                    except Exception as e:
                        st.error(f"⚠️ {type(e).__name__}: {e}")

            if st.session_state.get("_last_bt_sym") != active_sym:
                st.session_state.signal_index = len(trades_df) - 1
                st.session_state["_last_bt_sym"] = active_sym

            sig_idx = max(0, min(st.session_state.signal_index, len(trades_df) - 1))

            nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 3, 1, 1])
            with nav1:
                if st.button("⏮️ الأولى", use_container_width=True): st.session_state.signal_index = 0; st.rerun()
            with nav2:
                if st.button("◀ السابقة", use_container_width=True): st.session_state.signal_index = max(0, sig_idx - 1); st.rerun()
            with nav3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>"
                            f"إشارة {sig_idx + 1} من {len(trades_df)}</div>", unsafe_allow_html=True)
            with nav4:
                if st.button("التالية ▶", use_container_width=True): st.session_state.signal_index = min(len(trades_df) - 1, sig_idx + 1); st.rerun()
            with nav5:
                if st.button("الأخيرة ⏭️", use_container_width=True): st.session_state.signal_index = len(trades_df) - 1; st.rerun()

            current_sig = trades_df.iloc[sig_idx]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🎯 الدخول", f"{current_sig.get('Entry Price', '—')}")
            m2.metric("🛑 SL", f"{current_sig.get('Stop Loss', '—')}")
            m3.metric("🏆 TP", f"{current_sig.get('Take Profit', '—')}")
            m4.metric("📊 النتيجة", f"{current_sig.get('Result', '—')}")

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

            with st.expander("📋 تفاصيل الإشارة الحالية", expanded=False):
                for col in ["Entry Date", "Exit Date", "Bias", "Result", "Entry Price", "Stop Loss",
                            "Take Profit", "Pips", "RR_Ratio", "top_touches", "bot_touches",
                            "impulse_pct", "slope_pct", "cv_pct", "drift_pct", "flat_bars_pct", "bars_per_pct"]:
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
            sig_idx = max(0, min(st.session_state.signal_index, len(sigs) - 1))

            nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 3, 1, 1])
            with nav1:
                if st.button("⏮️ الأولى", use_container_width=True, key="live_nav_first"): st.session_state.signal_index = 0; st.rerun()
            with nav2:
                if st.button("◀ السابقة", use_container_width=True, key="live_nav_prev"): st.session_state.signal_index = max(0, sig_idx - 1); st.rerun()
            with nav3:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold'>"
                            f"إشارة {sig_idx + 1} من {len(sigs)}</div>", unsafe_allow_html=True)
            with nav4:
                if st.button("التالية ▶", use_container_width=True, key="live_nav_next"): st.session_state.signal_index = min(len(sigs) - 1, sig_idx + 1); st.rerun()
            with nav5:
                if st.button("الأخيرة ⏭️", use_container_width=True, key="live_nav_last"): st.session_state.signal_index = len(sigs) - 1; st.rerun()

            active_res = sigs[sig_idx]['result']
            active_sym = active_res.get("symbol", "N/A")

            e1, e2, e3 = st.columns(3)
            e1.metric("🎯 الدخول", f"{active_res.get('entry', 0)}")
            e2.metric("🛑 SL", f"{active_res.get('sl', 0)}")
            e3.metric("🏆 TP", f"{active_res.get('tp', 0)}")

            st.session_state["active_signal_symbol"] = active_sym
            st.session_state["active_signal_entry"] = active_res.get("entry")
            st.session_state["active_signal_sl"] = active_res.get("sl")
            st.session_state["active_signal_tp"] = active_res.get("tp")

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
# 💰 Risk Calculator (دائماً أسفل الصفحة)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("💰 حاسبة المخاطرة المتقدمة", expanded=False):
    render_advanced_risk_calculator(unique_id="end")


# ══════════════════════════════════════════════════════════════════════════════
# 📊 IC Markets Table
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("📊 جدول IC Markets Standard", expanded=False):
    ic_display = []
    for key, spec in IC_MARKETS_SPECS.items():
        ic_display.append({
            "الزوج": key, "النوع": spec["cat"],
            "حجم العقد": f"{spec['contract']:,}",
            "أقل لوت": spec["min_lot"],
            "خطوة اللوت": spec["step"],
            "حجم النقطة": spec["pip"],
        })
    st.dataframe(pd.DataFrame(ic_display), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 📖 Sharaxaad
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("📖 Sida loo isticmaalo App-ka", expanded=False):
    st.markdown("""
    ## 🎯 نمط المستطيل — Horizontal Rectangle Reversal

    ### الشروط:
    1. **انطلاقة قوية** قبل المستطيل (≥ 0.8%)
    2. **مستطيل أفقي** بعمر ≥ أسبوع
    3. **عرض ÷ ارتفاع ≥ 45** (يرفض العمودي)
    4. **≥ 3 لمسات** على كل حد
    5. **slope ≈ 0 · CV ≤ 0.35% · drift ≤ 0.45%**
    6. **كسر بإغلاق شمعة** خارج المستطيل
    7. **SL** على الجهة المقابلة، **TP = 3× المخاطرة**

    ### 📌 الأقسام المتوفرة:
    - 💰 **حاسبة المخاطرة المتقدمة** — أسفل الصفحة
    - 📊 **التقرير المالي الشامل** — داخل Backtest
    - 🎯 **التصرفات المطلوبة الآن** — إدارة الصفقات
    - 🔬 **التقرير التشخيصي** — تحليل الفلاتر
    - 🔽 **التنقل بين الإشارات** — أسهم ◀ ▶
    """)
