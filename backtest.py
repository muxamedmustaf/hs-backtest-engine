# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st, yfinance as yf, plotly.graph_objects as go, pandas as pd
from engine import run_full_analysis, backtest_strategy
try:
    from engine import diagnose_filters
except ImportError:
    diagnose_filters = None
try:
    from ffff import get_symbols_from_sheet
except ImportError:
    pass

st.set_page_config(
    page_title="Smart Market Analyzer & Backtest Lab",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
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
    "USDCNH=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Exotic"},
    "USDNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Scandinavian"},
    "USDSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
    "EURDKK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Scandinavian"},
    "CHFSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "🔀 Cross"},
    "SGDJPY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "💴 Cross"},
    "USDHKD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Exotic"},
    "NZDGBP=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "AUDSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "EURHKD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Exotic"},
    "EURNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Scandinavian"},
    "EURPLN=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
    "EURSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPNOK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Scandinavian"},
    "GBPSGD=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "🔀 Cross"},
    "GBPTRY=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
    "NOKSEK=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.0001, "cat": "⚠️ Scandinavian"},
    "USDTHB=X": {"contract": 100000, "min_lot": 0.01, "step": 0.01, "pip": 0.01,   "cat": "⚠️ Exotic"},
}

def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ["XAUUSD", "XAUUSD=X", "GOLD"]:
        return "GC=F"
    if sym in ["XAGUSD", "XAGUSD=X", "SILVER"]:
        return "SI=F"
    if sym == "GBPADY=X":
        return "GBPNZD=X"
    if len(sym) == 6 and sym.isalpha():
        return f"{sym}=X"
    return sym

def pip_size_for(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s:
            return spec["pip"]
    if "XAU" in s or "GOLD" in s: return 0.1
    if "XAG" in s or "SILVER" in s: return 0.01
    if any(x in s for x in ["BTC", "ETH"]): return 1.0
    if any(x in s for x in ["US30", "NAS", "SPX", "US100", "US500"]): return 1.0
    if "JPY" in s: return 0.01
    high_price = ["HUF", "TRY", "SEK", "NOK", "CZK", "MXN", "ZAR",
                  "PLN", "INR", "THB", "DKK", "HKD", "SGD", "PHP", "IDR"]
    if any(c in s for c in high_price):
        return 0.01
    return 0.0001

def get_default_lot_for_symbol(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s:
            return spec["min_lot"]
    if any(x in s for x in ["BTC", "ETH"]): return 0.01
    if any(x in s for x in ["US30", "NAS", "SPX"]): return 0.1
    return 0.01

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
        entry  = pick(row, ["Entry Price", "Entry", "entry"])
        exit_  = pick(row, ["Exit Price", "Exit", "exit", "Close Price"])
        sl     = pick(row, ["Stop Loss", "SL", "sl"])
        tp     = pick(row, ["Take Profit", "TP", "tp"])
        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_sell = "SELL" in bias or "SHORT" in bias or "BEAR" in bias

        pips = None
        if entry is not None and exit_ is not None:
            pips = (entry - exit_) / pip if is_sell else (exit_ - entry) / pip
        risk = None
        if entry is not None and sl is not None:
            risk = (sl - entry) / pip if is_sell else (entry - sl) / pip
            risk = abs(risk)
        reward = None
        if entry is not None and tp is not None:
            reward = (entry - tp) / pip if is_sell else (tp - entry) / pip
            reward = abs(reward)
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

        if entry_f and entry_f != 0:
            pct = price_move / entry_f * 100
        else:
            pct = None

        usd_list.append(round(pnl_usd, 2) if pnl_usd is not None else None)
        pct_list.append(round(pct, 2) if pct is not None else None)

    df["PnL_USD"] = usd_list
    df["PnL_Pct"] = pct_list
    return df


def calculate_trade_risk_usd(entry, sl, lot, symbol):
    try:
        entry_f = float(entry); sl_f = float(sl); lot_f = float(lot)
    except (TypeError, ValueError):
        return None
    if entry_f == 0:
        return None

    price_move = abs(entry_f - sl_f)
    s = str(symbol).upper()

    if any(x in s for x in ["BTC", "ETH"]):
        return price_move * lot_f * 1
    if any(x in s for x in ["US30", "NAS", "SPX"]):
        return price_move * lot_f * 1
    if "XAU" in s or "GC=F" in s: return price_move * lot_f * 100
    if "XAG" in s or "SI=F" in s: return price_move * lot_f * 5000

    if s.endswith("USD"):
        return price_move * lot_f * 100000
    else:
        if entry_f == 0: return None
        return price_move * lot_f * 100000 / entry_f


def check_risk_limit(entry, sl, lot, symbol, capital, risk_pct):
    risk_usd = calculate_trade_risk_usd(entry, sl, lot, symbol)

    if risk_usd is None:
        return {
            "allowed": False, "risk_usd": None, "max_risk_usd": None,
            "risk_pct_actual": None,
            "message": "⚠️ لا يمكن حساب المخاطرة — بيانات ناقصة"
        }

    max_risk_usd = capital * (risk_pct / 100)
    risk_pct_actual = (risk_usd / capital * 100) if capital > 0 else 0
    allowed = risk_usd <= max_risk_usd

    if allowed:
        message = f"✅ مقبولة — المخاطرة {risk_usd:.2f}$ ({risk_pct_actual:.2f}%) ≤ الحد {max_risk_usd:.2f}$"
    else:
        message = f"❌ مرفوضة — المخاطرة {risk_usd:.2f}$ ({risk_pct_actual:.2f}%) > الحد {max_risk_usd:.2f}$"

    return {
        "allowed": allowed,
        "risk_usd": round(risk_usd, 2),
        "max_risk_usd": round(max_risk_usd, 2),
        "risk_pct_actual": round(risk_pct_actual, 2),
        "message": message
    }


def get_available_symbols():
    symbols_set = set(IC_MARKETS_SPECS.keys())

    try:
        sheet_symbols = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]
        for s in sheet_symbols:
            symbols_set.add(str(s).strip())
    except Exception:
        pass

    if "backtest_scanned_signals" in st.session_state:
        for item in st.session_state.backtest_scanned_signals:
            if "symbol" in item:
                symbols_set.add(item["symbol"])

    if "scanned_signals" in st.session_state:
        for item in st.session_state.scanned_signals:
            if "symbol" in item:
                symbols_set.add(item["symbol"])

    return sorted(list(symbols_set))


def get_last_known_price(symbol):
    if "backtest_dfs" in st.session_state:
        df = st.session_state.backtest_dfs.get(symbol)
        if df is not None and not df.empty:
            try:
                return float(df["Close"].iloc[-1])
            except Exception:
                pass

    if "scanned_signals" in st.session_state:
        for item in st.session_state.scanned_signals:
            if item.get("symbol") == symbol:
                entry = item["result"].get("entry")
                if entry:
                    return float(entry)

    return None


def get_active_symbols():
    """Liiska symbols-ka leh signals furan."""
    active = set()
    if "backtest_scanned_signals" in st.session_state:
        for item in st.session_state.backtest_scanned_signals:
            if "symbol" in item:
                active.add(item["symbol"])
    if "scanned_signals" in st.session_state:
        for item in st.session_state.scanned_signals:
            if "symbol" in item:
                active.add(item["symbol"])
    return sorted(list(active))


def get_near_symbols():
    """Liiska symbols-ka dhow inay jabaan."""
    near = set()
    if "near_signals" in st.session_state:
        for item in st.session_state.near_signals:
            near.add(item["symbol"])
    return sorted(list(near))


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Realtime Actions — Trailing alerts
# ══════════════════════════════════════════════════════════════════════════════
def render_realtime_actions(trades_df, is_live=False, live_prices=None):
    st.markdown("### 🎯 التصرفات المطلوبة الآن")
    st.caption("إجراءات محدّدة لصفقاتك")

    if trades_df is None or trades_df.empty:
        st.info("ℹ️ لا توجد صفقات للتحليل")
        return

    actions = []

    if is_live:
        relevant = trades_df.index.tolist()
    else:
        relevant = trades_df.tail(5).index.tolist() if len(trades_df) > 5 else trades_df.index.tolist()

    for idx in relevant:
        row = trades_df.loc[idx]
        sym = row.get("symbol") or row.get("Symbol") or "?"
        result = str(row.get("Result", "")).upper()

        if not is_live and result in ["WIN", "LOSS", "TIMEOUT", "BREAKEVEN"]:
            continue

        try:
            entry_f = float(row.get("Entry Price") or row.get("Entry") or 0)
            sl_f = float(row.get("Stop Loss") or row.get("SL") or 0)
            tp_f = float(row.get("Take Profit") or row.get("TP") or 0)
        except (TypeError, ValueError):
            continue

        if entry_f == 0 or sl_f == 0 or tp_f == 0:
            continue

        bias = str(row.get("bias") or row.get("Bias") or "").upper()
        is_bearish = "BEAR" in bias or "SELL" in bias
        progress = row.get("Max Reach %", 0) or 0

        if is_live and live_prices and sym in live_prices:
            current_price = live_prices[sym]
            progress = ((entry_f - current_price) if is_bearish else (current_price - entry_f)) / abs(tp_f - entry_f) * 100
            progress = max(0, min(progress, 200))

        if progress < 15:
            continue

        total_tp = abs(tp_f - entry_f)

        if progress >= 80:
            priority = "🔴 عاجل"
            action = "إغلاق 50% + Trailing 60%"
            new_sl = entry_f + (0.6 * total_tp * (-1 if is_bearish else 1))
            guaranteed = "60%"
        elif progress >= 50:
            priority = "🟠 عالي"
            action = "تفعيل Trailing 30%"
            new_sl = entry_f + (0.3 * total_tp * (-1 if is_bearish else 1))
            guaranteed = "30%"
        elif progress >= 25:
            priority = "🟡 متوسط"
            action = "نقل SL إلى التعادل"
            new_sl = entry_f
            guaranteed = "0%"
        else:
            continue

        try:
            lot = row.get("Lot") or 0.01
            if any(x in sym.upper() for x in ["BTC", "ETH"]):
                dollar_profit = abs(entry_f - new_sl) * float(lot)
            elif is_bearish:
                dollar_profit = (entry_f - new_sl) * float(lot) * 100000 / entry_f
            else:
                dollar_profit = (new_sl - entry_f) * float(lot) * 100000 / entry_f
        except Exception:
            dollar_profit = None

        actions.append({
            "الأولوية": priority, "الزوج": sym, "الوصول": f"{progress:.1f}%",
            "الإجراء": action, "SL الحالي": f"{sl_f:.5f}", "SL الجديد": f"{new_sl:.5f}",
            "الربح المضمون": guaranteed,
            "بالدولار": f"+${dollar_profit:.2f}" if dollar_profit else "—",
            "_priority": {"🔴 عاجل": 0, "🟠 عالي": 1, "🟡 متوسط": 2}.get(priority, 99),
        })

    if not actions:
        st.success("✅ لا توجد صفقات تحتاج تصرفًا الآن")
        st.caption("الصفقات لم تتجاوز 15% من الهدف بعد — انتظر")
        return

    actions.sort(key=lambda x: x["_priority"])

    urgent = sum(1 for a in actions if a["الأولوية"] == "🔴 عاجل")
    high = sum(1 for a in actions if a["الأولوية"] == "🟠 عالي")
    medium = sum(1 for a in actions if a["الأولوية"] == "🟡 متوسط")

    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 عاجل", urgent)
    c2.metric("🟠 عالي", high)
    c3.metric("🟡 متوسط", medium)

    for action in actions:
        priority = action["الأولوية"]
        msg = f"""
**{priority} | {action['الزوج']}**

🎯 **الإجراء:** {action['الإجراء']}
📊 **الوصول:** {action['الوصول']} من الهدف
🛑 **SL:** `{action['SL الحالي']}` → **`{action['SL الجديد']}`**
💰 **الربح المضمون:** {action['الربح المضمون']} ({action['بالدولار']})
        """
        if priority == "🔴 عاجل":
            st.error(msg)
        elif priority == "🟠 عالي":
            st.warning(msg)
        else:
            st.info(msg)

    with st.expander("📋 جدول مختصر"):
        df_display = pd.DataFrame([{
            "الأولوية": a["الأولوية"], "الزوج": a["الزوج"], "الوصول": a["الوصول"],
            "الإجراء": a["الإجراء"], "SL الجديد": a["SL الجديد"],
            "الربح المضمون": a["الربح المضمون"],
        } for a in actions])
        st.dataframe(df_display, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# ⏳ NEAR SIGNALS — Patterns dhow inay jabaan
# ══════════════════════════════════════════════════════════════════════════════
def detect_near_signals(df, interval="5m", symbol=None, proximity_pct=2.0):
    """
    Soo hel patterns-ka qiimaha u dhow yahay inuu jabiyo neckline.
    proximity_pct: meeqa % u dhow (default 2%).
    """
    try:
        from engine import (calculate_indicators, calculate_zigzag,
                            get_chronological_pivots, detect_all_head_shoulders,
                            CONFIG, _get_max_gap, _get_max_pattern_duration)
    except ImportError:
        return []

    if df is None or df.empty or len(df) < 30:
        return []

    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns:
            return []
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    if len(df) < 30:
        return []

    try:
        df = calculate_indicators(df)
        df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
        pivots = get_chronological_pivots(df)

        max_gap = _get_max_gap(interval)
        max_pattern_dur = _get_max_pattern_duration(interval)

        all_patterns = detect_all_head_shoulders(
            pivots, df, is_backtest=True,
            max_gap=max_gap, max_pattern_duration=max_pattern_dur
        )
    except Exception:
        return []

    if not all_patterns:
        return []

    current_price = float(df["Close"].iloc[-1])
    last_pos = len(df) - 1
    near_signals = []

    for p in all_patterns[-50:]:
        end_pos = p.get("end_pos", 0)
        if (last_pos - end_pos) > 60 or (last_pos - end_pos) < 0:
            continue

        entry = p.get("entry")
        sl = p.get("sl")
        tp = p.get("tp")
        bias = str(p.get("bias", ""))

        if entry is None or entry == 0:
            continue

        if "Bear" in bias:
            distance_pct = (current_price - entry) / entry * 100
        else:
            distance_pct = (entry - current_price) / entry * 100

        if 0 <= distance_pct <= proximity_pct:
            near_signals.append({
                "symbol": symbol,
                "pattern": p.get("pattern", "H&S"),
                "bias": bias,
                "neckline": round(entry, 5),
                "current_price": round(current_price, 5),
                "distance_pct": round(distance_pct, 2),
                "sl": round(sl, 5) if sl else None,
                "tp": round(tp, 5) if tp else None,
                "candles_since": last_pos - end_pos,
            })

    near_signals.sort(key=lambda x: x["distance_pct"])
    return near_signals


def render_near_signals(near_signals):
    """Muuji liiska signals-ka dhow inay jabaan."""
    if not near_signals:
        st.info("ℹ️ Ma jiraan signals dhow inay jabaan — suug ilaa xog cusub")
        return

    st.warning(f"⚠️ **{len(near_signals)}** signal oo dhow inay jabaan")

    df_disp = pd.DataFrame([{
        "Zoug": s["symbol"],
        "Pattern": s["pattern"],
        "Bias": s["bias"],
        "Neckline": s["neckline"],
        "Qiimaha": s["current_price"],
        "Masaafo %": f"{s['distance_pct']:.2f}%",
        "SL": s["sl"],
        "TP": s["tp"],
        "Candles": s["candles_since"],
    } for s in near_signals])

    st.dataframe(df_disp, use_container_width=True, hide_index=True)

    if st.button("🔗 U rar signals-ka calculator-ka", key="load_near_sig", use_container_width=True):
        first = near_signals[0]
        st.session_state["active_signal_symbol"] = first["symbol"]
        st.session_state["active_signal_entry"] = first["neckline"]
        st.session_state["active_signal_sl"] = first["sl"]
        st.session_state["active_signal_tp"] = first["tp"]
        st.session_state["active_signal_bias"] = first["bias"]
        st.success(f"✅ La raray: {first['symbol']}")


# ══════════════════════════════════════════════════════════════════════════════
# 💰 Advanced Risk Calculator
# ══════════════════════════════════════════════════════════════════════════════
def render_advanced_risk_calculator(unique_id="main"):
    st.markdown("### 💰 حاسبة المخاطرة المتقدمة")
    st.caption("اختر العملة، أدخل السعر واللوت — التحليل يتصل تلقائيًا")

    # ═══ 1️⃣ Agaasinka Guud ═══
    st.markdown("#### 1️⃣ الإعدادات العامة")
    c1, c2, c3 = st.columns(3)

    with c1:
        capital = st.number_input(
            "💵 رأس المال ($):",
            min_value=10.0, max_value=10_000_000.0, value=1000.0,
            step=100.0, format="%.2f", key=f"{unique_id}_adv_risk_capital"
        )

    with c2:
        risk_pct = st.selectbox(
            "📊 نسبة المخاطرة (%):",
            options=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            index=4, key=f"{unique_id}_adv_risk_pct"
        )

    max_risk_usd = capital * (risk_pct / 100)

    with c3:
        st.metric("🛑 الحد الأقصى للمخاطرة", f"${max_risk_usd:,.2f}")

    st.markdown("---")

    # ═══ 2️⃣ Dooro Symbol — Search + Active/Near filter ═══
    st.markdown("#### 2️⃣ اختيار العملة")

    src_choice = st.radio(
        "مصدر القائمة:",
        ["📋 الإشارات النشطة", "⏳ المراقبة (قريب)", "📚 القائمة الكاملة"],
        horizontal=True,
        key=f"{unique_id}_src_choice"
    )

    active_syms = get_active_symbols()
    near_syms = get_near_symbols()

    if src_choice == "📋 الإشارات النشطة":
        available_symbols = active_syms if active_syms else []
    elif src_choice == "⏳ المراقبة (قريب)":
        available_symbols = near_syms if near_syms else []
    else:
        available_symbols = get_available_symbols()

    search_term = st.text_input(
        "🔍 ابحث بالاسم:",
        placeholder="EUR, GBP, BTC, XAU...",
        key=f"{unique_id}_search_{src_choice}"
    )
    if search_term:
        available_symbols = [s for s in available_symbols if search_term.upper() in s.upper()]

    if not available_symbols:
        st.warning("⚠️ لا توجد عملات مطابقة. جرب مصدر آخر أو ابحث باسم مختلف.")
        return

    active_signal_sym   = st.session_state.get("active_signal_symbol")
    active_signal_entry = st.session_state.get("active_signal_entry")
    active_signal_sl    = st.session_state.get("active_signal_sl")
    active_signal_tp    = st.session_state.get("active_signal_tp")
    active_signal_bias  = st.session_state.get("active_signal_bias")

    default_idx = 0
    if active_signal_sym and active_signal_sym in available_symbols:
        default_idx = available_symbols.index(active_signal_sym)

    col_sym, col_lot = st.columns([2, 1])

    with col_sym:
        selected_symbol = st.selectbox(
            "🔽 اختر العملة:",
            options=available_symbols, index=default_idx,
            key=f"{unique_id}_adv_risk_symbol"
        )

    with col_lot:
        default_lot = get_default_lot_for_symbol(selected_symbol)
        custom_lot = st.number_input(
            "💰 اللوت المخصص:",
            min_value=0.0001, max_value=100.0,
            value=default_lot, step=0.01, format="%.2f",
            key=f"{unique_id}_adv_risk_lot_{selected_symbol}",
            help="IC Markets Standard: min 0.01"
        )

    # ═══ 3️⃣ Xogta Signal-ka ═══
    st.markdown("#### 3️⃣ بيانات الصفقة")

    if active_signal_sym == selected_symbol and active_signal_entry:
        default_entry = float(active_signal_entry)
        default_sl    = float(active_signal_sl) if active_signal_sl else default_entry * 1.01
        default_tp    = float(active_signal_tp) if active_signal_tp else default_entry * 0.98
        st.info(f"🔗 **Xogta laga soo qaatay signal-ka:** {active_signal_bias}")
    else:
        last_price = get_last_known_price(selected_symbol)
        default_entry = float(last_price) if last_price else 1.0
        default_sl    = default_entry * 1.01
        default_tp    = default_entry * 0.98

    c_entry, c_sl, c_tp = st.columns(3)

    with c_entry:
        entry_price = st.number_input(
            "📈 سعر الدخول:", value=float(default_entry),
            format="%.5f", key=f"{unique_id}_adv_entry_{selected_symbol}"
        )

    with c_sl:
        sl_price = st.number_input(
            "🛑 وقف الخسارة:", value=float(default_sl),
            format="%.5f", key=f"{unique_id}_adv_sl_{selected_symbol}"
        )

    with c_tp:
        tp_price = st.number_input(
            "🏆 الهدف:", value=float(default_tp),
            format="%.5f", key=f"{unique_id}_adv_tp_{selected_symbol}"
        )

    # ⚡ Badhanka TP
    c1_btn, c2_btn, c3_btn = st.columns(3)
    with c1_btn:
        if st.button("⚡ TP (R:R = 1:2)", key=f"{unique_id}_tp_2x_{selected_symbol}",
                     use_container_width=True):
            if sl_price > entry_price:
                new_tp = entry_price - 2 * (sl_price - entry_price)
            else:
                new_tp = entry_price + 2 * (entry_price - sl_price)
            st.session_state[f"{unique_id}_adv_tp_{selected_symbol}"] = round(new_tp, 5)
            st.rerun()
    with c2_btn:
        if st.button("⚡ TP (R:R = 1:3)", key=f"{unique_id}_tp_3x_{selected_symbol}",
                     use_container_width=True):
            if sl_price > entry_price:
                new_tp = entry_price - 3 * (sl_price - entry_price)
            else:
                new_tp = entry_price + 3 * (entry_price - sl_price)
            st.session_state[f"{unique_id}_adv_tp_{selected_symbol}"] = round(new_tp, 5)
            st.rerun()
    with c3_btn:
        if st.button("⚡ TP (R:R = 1:1)", key=f"{unique_id}_tp_1x_{selected_symbol}",
                     use_container_width=True):
            if sl_price > entry_price:
                new_tp = entry_price - (sl_price - entry_price)
            else:
                new_tp = entry_price + (entry_price - sl_price)
            st.session_state[f"{unique_id}_adv_tp_{selected_symbol}"] = round(new_tp, 5)
            st.rerun()

    # ═══ 4️⃣ Natiijada Degdegga ═══
    st.markdown("---")
    st.markdown("#### 4️⃣ النتيجة الفورية")

    check = check_risk_limit(
        entry_price, sl_price, custom_lot,
        selected_symbol, capital, risk_pct
    )

    try:
        risk_distance = abs(float(entry_price) - float(sl_price))
        reward_distance = abs(float(tp_price) - float(entry_price))
        rr = round(reward_distance / risk_distance, 2) if risk_distance > 0 else "—"
    except Exception:
        rr = "—"

    potential_profit_usd = None
    if check["risk_usd"] is not None and isinstance(rr, (int, float)) and rr != "—":
        potential_profit_usd = round(check["risk_usd"] * rr, 2)

    if check["allowed"]:
        st.success("### ✅ مقبولة — ضمن حد المخاطرة")
    else:
        st.error("### ❌ مرفوضة — تجاوزت حد المخاطرة")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💸 المخاطرة", f"${check['risk_usd']:,.2f}" if check['risk_usd'] else "—")
    m2.metric("📊 النسبة الفعلية", f"{check['risk_pct_actual']}%" if check['risk_pct_actual'] else "—")
    m3.metric("⚖️ R:R", f"1:{rr}" if rr != "—" else "—")
    m4.metric("🎯 الربح المتوقع", f"${potential_profit_usd:,.2f}" if potential_profit_usd else "—")

    st.info(f"**التفاصيل:** {check['message']}")

    # ═══ 5️⃣ Talooyin ═══
    if not check["allowed"] and check["risk_usd"]:
        st.markdown("#### 💡 اقتراحات للتصحيح")

        suggested_lot = custom_lot * (max_risk_usd / check["risk_usd"])
        suggested_lot = round(max(0.0001, suggested_lot), 4)

        sl_distance = abs(float(entry_price) - float(sl_price))
        suggested_sl_distance = sl_distance * (max_risk_usd / check["risk_usd"])
        is_sell = sl_price > entry_price
        suggested_sl = entry_price + suggested_sl_distance if is_sell else entry_price - suggested_sl_distance

        c1, c2 = st.columns(2)
        with c1:
            st.warning(f"""
            **🔽 الخيار 1: تقليل اللوت**
            - اللوت الحالي: `{custom_lot}`
            - اللوت المقترح: `{suggested_lot}`
            - المخاطرة الجديدة: `${max_risk_usd:.2f}`
            """)
        with c2:
            st.warning(f"""
            **📉 الخيار 2: تقريب SL**
            - SL الحالي: `{sl_price:.5f}`
            - SL المقترح: `{suggested_sl:.5f}`
            """)

    # ═══ 6️⃣ Jadwalka IC Markets ═══
    with st.expander("📋 جدول IC Markets Standard — Contract & Lot specs"):
        ic_data = []
        for sym in available_symbols[:30]:
            s = str(sym).upper()
            spec = None
            for key, sp in IC_MARKETS_SPECS.items():
                if key.upper() == s:
                    spec = sp
                    break
            if spec is None:
                spec = {"contract": 100000, "min_lot": 0.01, "step": 0.01,
                        "pip": pip_size_for(sym), "cat": "—"}
            ic_data.append({
                "الزوج": sym,
                "النوع": spec["cat"],
                "حجم العقد": f"{spec['contract']:,}",
                "أقل لوت": spec["min_lot"],
                "خطوة اللوت": spec["step"],
                "حجم النقطة": spec["pip"],
            })
        st.dataframe(
            pd.DataFrame(ic_data),
            use_container_width=True,
            hide_index=True
        )

    # ═══ 7️⃣ Isticmaalka ═══
    with st.expander("ℹ️ كيف تستخدم الحاسبة؟"):
        st.markdown("""
        **1. أدخل رأس المال** (مثال: $1000)  
        **2. اختر نسبة المخاطرة** (مثال: 5%)  
        **3. اختر مصدر القائمة:**
        - 📋 **الإشارات النشطة** — signals furan
        - ⏳ **المراقبة (قريب)** — dhow inay jabaan
        - 📚 **القائمة الكاملة** — 50 pairs
        **4. ابحث بالاسم** — ku qor "EUR" ama "BTC"  
        **5. Riix "⚡ TP (R:R = 1:2)"** si aad u hesho TP sax ah  
        **6. Eeg natiijada:**
        - ✅ **مقبولة** → furi
        - ❌ **مرفوضة** → yaree lot ama SL
        """)


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
    ("near_signals", []),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# Sharipta Sare
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;direction:rtl;">
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:16px;padding:8px 14px;font-weight:700;color:#0B57D0;">📈 {st.session_state.current_symbol}</div>
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:30px;padding:8px 14px;font-weight:700;color:#0B57D0;">{st.session_state.status_summary}</div>
</div>''', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Dooro Habka
# ══════════════════════════════════════════════════════════════════════════════
app_mode = st.radio(
    "وضع التطبيق:",
    ["🚀 الماسح الحي للأسواق", "🧪 مختبر الاختبار الرجعي (Backtest)"],
    horizontal=True
)
st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ================= BACKTEST MODE =================
# ══════════════════════════════════════════════════════════════════════════════
if app_mode == "🧪 مختبر الاختبار الرجعي (Backtest)":

    st.markdown("### 🧪 مختبر تحليل الأداء التاريخي")

    bt_scan_mode = st.radio(
        "طريقة فحص الاختبار الرجعي:",
        ["سهم فردي", "مسح كلي لشيت الأصول"],
        horizontal=True, key="bt_scan_mode"
    )

    if bt_scan_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="EURUSD=X", key="bt_single_symbol")]
    else:
        try:
            bt_symbols = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]
        except Exception as e:
            st.error(f"⚠️ فشل جلب الرموز: {e}")
            bt_symbols = ["EURUSD=X"]

    now = datetime.datetime.now()
    available_years = [now.year, now.year - 1, now.year - 2]
    months_dict = {
        1: "01 - يناير", 2: "02 - فبراير", 3: "03 - مارس", 4: "04 - إبريل",
        5: "05 - مايو", 6: "06 - يونيو", 7: "07 - يوليو", 8: "08 - أغسطس",
        9: "09 - سبتمبر", 10: "10 - أكتوبر", 11: "11 - نوفمبر", 12: "12 - ديسمبر"
    }

    st.markdown("#### 📅 اختيار الفترة الزمنية")
    period_mode = st.radio(
        "نمط الفترة:",
        ["📆 شهر واحد", "📅 نطاق مخصص", "📊 أشهر متعددة", "🗓️ سنة كاملة"],
        horizontal=True, key="bt_period_mode"
    )

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
        start_pick = c1.date_input("📅 من تاريخ:",
            value=datetime.date(now.year, max(1, now.month - 1), 1),
            min_value=datetime.date(now.year - 5, 1, 1),
            max_value=datetime.date.today(), key="bt_custom_start")
        end_pick = c2.date_input("📅 إلى تاريخ:",
            value=datetime.date.today(),
            min_value=datetime.date(now.year - 5, 1, 1),
            max_value=datetime.date.today(), key="bt_custom_end")
        if start_pick >= end_pick:
            st.error("⚠️ تاريخ البداية يجب أن يكون قبل تاريخ النهاية")
        else:
            start_date = start_pick.strftime("%Y-%m-%d")
            end_date = end_pick.strftime("%Y-%m-%d")
            period_label = f"من {start_date} إلى {end_date} ({(end_pick-start_pick).days} يوم)"

    elif period_mode == "📊 أشهر متعددة":
        c_yr, c_months = st.columns([1, 2])
        multi_year = c_yr.selectbox("📅 السنة:", available_years, index=0, key="bt_multi_year")
        default_months = [m for m in [max(1, now.month-2), max(1, now.month-1), now.month] if m >= 1]
        selected_months = c_months.multiselect("🗓️ اختر الأشهر:", options=list(months_dict.keys()),
            format_func=lambda x: months_dict[x], default=default_months, key="bt_multi_months")
        if not selected_months:
            st.warning("⚠️ اختر شهراً واحداً على الأقل")
        else:
            sm = sorted(selected_months)
            first_m, last_m = sm[0], sm[-1]
            _, last_last = calendar.monthrange(multi_year, last_m)
            start_date = f"{multi_year}-{first_m:02d}-01"
            end_date   = f"{multi_year}-{last_m:02d}-{last_last:02d}"
            period_label = f"{' + '.join([months_dict[m] for m in sm])} {multi_year}"

    elif period_mode == "🗓️ سنة كاملة":
        year_pick = st.columns(1)[0].selectbox("📅 السنة:", available_years, index=0, key="bt_full_year")
        start_date = f"{year_pick}-01-01"
        end_date   = f"{year_pick}-12-31"
        period_label = f"السنة {year_pick} كاملة"

    st.markdown("---")
    selected_interval = st.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=9, key="bt_interval")

    st.markdown("#### 💰 إعدادات رأس المال")
    lot_size = st.number_input(
        "حجم اللوت لكل صفقة:", min_value=0.01, max_value=100.0,
        value=0.01, step=0.01, format="%.2f", key="bt_lot_size"
    )

    if start_date and end_date:
        st.success(f"✅ الفترة: **{period_label}**")
        st.caption(f"📅 من `{start_date}` إلى `{end_date}` | ⏱️ `{selected_interval}` | 💰 لوت `{lot_size}`")
        max_days = INTERVAL_LIMITS.get(selected_interval)
        if max_days:
            actual_days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
            if actual_days > max_days:
                st.warning(f"⚠️ الإطار `{selected_interval}` مدعوم فقط لآخر **{max_days} يوم**.")

    if st.button("📊 بدء محاكاة الاختبار الرجعي", use_container_width=True) and bt_symbols and start_date and end_date:
        results, dfs = [], {}
        dl_int = selected_interval if selected_interval in ["1m","5m","15m","30m","1h","1d","1wk","1mo"] else "1h"
        p_bar = st.progress(0); s_txt = st.empty(); error_log = []

        for idx, sym in enumerate(bt_symbols):
            s_txt.text(f"محاكاة ({idx+1}/{len(bt_symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(bt_symbols))
            try:
                sym_fixed = fix_symbol(sym)
                df = yf.download(sym_fixed, start=start_date, end=end_date,
                                 interval=dl_int, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if df is None or df.empty:
                    error_log.append(f"⚠️ {sym}: لا توجد بيانات"); continue
                trades = backtest_strategy(df, interval=selected_interval, symbol=sym)
                if trades:
                    tdf = pd.DataFrame(trades)
                    if "symbol" not in tdf.columns:
                        tdf["symbol"] = sym
                    results.append({"symbol": sym, "trades_df": tdf, "total_signals": len(tdf)})
                    dfs[sym] = df
            except Exception as e:
                error_log.append(f"❌ {sym}: {type(e).__name__}: {e}")

        s_txt.empty(); p_bar.empty()
        st.session_state.backtest_scanned_signals = results
        st.session_state.backtest_dfs = dfs
        st.session_state.backtest_period = period_label
        st.session_state.backtest_start = start_date
        st.session_state.backtest_end = end_date
        if error_log:
            with st.expander(f"⚠️ تحذيرات ({len(error_log)})"):
                for msg in error_log: st.text(msg) 

# ══════════════════════════════════════════════════════════════════════════
# Natiijada Backtest
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.backtest_scanned_signals:
    res_list = st.session_state.backtest_scanned_signals
    dfs_dict = st.session_state.backtest_dfs
    period_display = st.session_state.get("backtest_period", "غير محدد")

    all_dfs = [i["trades_df"] for i in res_list if "trades_df" in i and not i["trades_df"].empty]

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_df = compute_pips(combined_df)
        combined_df = compute_dollar_pnl(combined_df, lot=lot_size)

        g_res_col = None
        for col in ["Result", "Head Result"]:
            if col in combined_df.columns:
                g_res_col = col
                break

        if g_res_col:
            g_series = combined_df[g_res_col].astype(str).str.upper()
            g_wins   = len(combined_df[g_series.str.contains("WIN")])
            g_losses = len(combined_df[g_series.str.contains("LOSS")])
            g_opens  = len(combined_df[g_series.str.contains("OPEN")])
        else:
            g_wins = g_losses = g_opens = 0

        g_closed = g_wins + g_losses
        g_win_rate  = round((g_wins / g_closed) * 100, 1) if g_closed > 0 else 0.0
        g_loss_rate = round((g_losses / g_closed) * 100, 1) if g_closed > 0 else 0.0
        g_total = len(combined_df)

        total_pips  = combined_df["Pips"].dropna().sum()
        avg_pips    = combined_df["Pips"].dropna().mean()
        total_usd   = combined_df["PnL_USD"].dropna().sum()
        wins_pips   = combined_df.loc[g_series.str.contains("WIN"),  "Pips"].dropna().sum() if g_res_col else 0
        losses_pips = combined_df.loc[g_series.str.contains("LOSS"), "Pips"].dropna().sum() if g_res_col else 0
        wins_usd    = combined_df.loc[g_series.str.contains("WIN"),  "PnL_USD"].dropna().sum() if g_res_col else 0
        losses_usd  = combined_df.loc[g_series.str.contains("LOSS"), "PnL_USD"].dropna().sum() if g_res_col else 0

        profit_factor = round(abs(wins_usd / losses_usd), 2) if losses_usd != 0 else float("inf")

        st.markdown(f"#### 🌍 الملخص الإجمالي — **{period_display}**")

        gm1, gm2, gm3, gm4 = st.columns(4)
        gm1.metric("📊 إجمالي الصفقات", g_total)
        gm2.metric("✅ ناجحة", g_wins, delta=f"{g_win_rate}%")
        gm3.metric("❌ خاسرة", g_losses, delta=f"{g_loss_rate}%", delta_color="inverse")
        gm4.metric("⏳ مفتوحة", g_opens)

        gm5, gm6, gm7, gm8 = st.columns(4)
        gm5.metric("📏 إجمالي النقاط", f"{total_pips:+.1f}")
        gm6.metric("📐 متوسط النقاط", f"{avg_pips:+.1f}" if pd.notna(avg_pips) else "—")
        gm7.metric(f"💰 صافي الربح (لوت {lot_size})", f"{total_usd:+.2f} $")
        gm8.metric("⚖️ Profit Factor",
                   f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞")

        st.markdown("##### 📊 تفصيل النقاط والأرباح")
        detail = pd.DataFrame([
            {"البند": "صفقات رابحة", "العدد": g_wins,   "النقاط": round(wins_pips, 1),
             "بالدولار": round(wins_usd, 2)},
            {"البند": "صفقات خاسرة", "العدد": g_losses, "النقاط": round(losses_pips, 1),
             "بالدولار": round(losses_usd, 2)},
            {"البند": "الصافي",       "العدد": g_closed, "النقاط": round(wins_pips + losses_pips, 1),
             "بالدولار": round(wins_usd + losses_usd, 2)},
        ])
        st.dataframe(detail, use_container_width=True, hide_index=True)

        st.markdown("---")
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            csv_combined = combined_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 تنزيل كل الصفقات (CSV)",
                data=csv_combined,
                file_name=f"backtest_ALL_{period_display.replace(' ', '_').replace('/', '-')}.csv",
                mime="text/csv", use_container_width=True
            )

        with dl_col2:
            stats_summary = pd.DataFrame([{
                "Period": period_display,
                "Start": st.session_state.get("backtest_start", ""),
                "End": st.session_state.get("backtest_end", ""),
                "Interval": selected_interval,
                "Lot": lot_size,
                "Total": g_total,
                "Wins": g_wins, "Losses": g_losses, "Opens": g_opens,
                "Win_Rate_%": g_win_rate, "Loss_Rate_%": g_loss_rate,
                "Total_Pips": round(total_pips, 1),
                "Wins_Pips": round(wins_pips, 1),
                "Losses_Pips": round(losses_pips, 1),
                "Net_PnL_USD": round(wins_usd + losses_usd, 2),
                "Profit_Factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
            }])
            csv_stats = stats_summary.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📊 تنزيل الإحصائيات (CSV)",
                data=csv_stats,
                file_name=f"backtest_STATS_{period_display.replace(' ', '_').replace('/', '-')}.csv",
                mime="text/csv", use_container_width=True
            )

        st.markdown("---")

    # Dooro symbol
    if bt_scan_mode == "مسح كلي لشيت الأصول":
        opts = [f"{i['symbol']} | الصفقات: {i['total_signals']}" for i in res_list]
        active_item = res_list[opts.index(st.selectbox("👇 اختر الأصل:", opts))]
    else:
        active_item = res_list[0]

    active_sym = active_item["symbol"]
    trades_df = active_item["trades_df"]
    trades_df = compute_pips(trades_df)
    trades_df = compute_dollar_pnl(trades_df, lot=lot_size)
    st.session_state.current_symbol = active_sym

    # Hubi signals — u rar calculator-ka
    if len(trades_df) > 0:
        last_row = trades_df.iloc[-1]
        st.session_state["active_signal_symbol"] = active_sym
        st.session_state["active_signal_entry"]  = last_row.get("Entry Price") or last_row.get("Entry")
        st.session_state["active_signal_sl"]     = last_row.get("Stop Loss") or last_row.get("SL")
        st.session_state["active_signal_tp"]     = last_row.get("Take Profit") or last_row.get("TP")
        st.session_state["active_signal_bias"]   = last_row.get("bias") or last_row.get("Bias")

    res_col = None
    for col in ["Result", "Head Result"]:
        if col in trades_df.columns:
            res_col = col
            break

    if res_col:
        res_series = trades_df[res_col].astype(str).str.upper()
        wins   = len(trades_df[res_series.str.contains("WIN")])
        losses = len(trades_df[res_series.str.contains("LOSS")])
        opens  = len(trades_df[res_series.str.contains("OPEN")])
    else:
        wins = losses = opens = 0

    closed_trades = wins + losses
    win_rate  = round((wins / closed_trades) * 100, 1) if closed_trades > 0 else 0.0
    loss_rate = round((losses / closed_trades) * 100, 1) if closed_trades > 0 else 0.0

    sym_total_pips = trades_df["Pips"].dropna().sum()
    sym_avg_pips   = trades_df["Pips"].dropna().mean()
    sym_total_usd  = trades_df["PnL_USD"].dropna().sum()

    dur_str = "غير متاح"
    if "Entry Date" in trades_df.columns and "Exit Date" in trades_df.columns:
        entry_dt = pd.to_datetime(trades_df["Entry Date"], errors="coerce")
        exit_dt  = pd.to_datetime(trades_df["Exit Date"], errors="coerce")
        days = (exit_dt - entry_dt).dt.days.dropna()
        if len(days) > 0:
            dur_str = f"{days.mean():.1f} يوم"

    st.markdown(f"### 📊 نتائج **{active_sym}** — {period_display}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ أ. ناجحة", wins, delta=f"{win_rate}%")
    m2.metric("❌ ب. خاسرة", losses, delta=f"{loss_rate}%", delta_color="inverse")
    m3.metric("⏳ ج. مفتوحة", opens)
    m4.metric("⏱️ د. مدة المركز", dur_str)

    m5, m6, m7 = st.columns(3)
    m5.metric("📏 إجمالي النقاط", f"{sym_total_pips:+.1f}")
    m6.metric("📐 متوسط النقاط", f"{sym_avg_pips:+.1f}" if pd.notna(sym_avg_pips) else "—")
    m7.metric(f"💰 صافي الربح", f"{sym_total_usd:+.2f} $")

    # Symmetry
    sym_scores = []
    if "nodes" in trades_df.columns:
        for _, row in trades_df.iterrows():
            nodes = row.get("nodes")
            if isinstance(nodes, list) and len(nodes) >= 5:
                prices = [n[1] for n in nodes]
                ls, nl1, head, nl2, rs = prices[:5]
                head_range = abs(head - (nl1 + nl2) / 2) + 1e-5
                shoulder_diff = abs(ls - rs)
                neck_diff = abs(nl1 - nl2)
                s_sym = max(0, 100 - (shoulder_diff / head_range) * 100)
                n_sym = max(0, 100 - (neck_diff / head_range) * 100)
                sym_scores.append((s_sym + n_sym) / 2)

    avg_symmetry = f"{round(sum(sym_scores)/len(sym_scores), 1)}%" if sym_scores else "—"
    avg_mfe = f"{round(trades_df['Max Reach %'].mean(), 1)}%" if "Max Reach %" in trades_df.columns else "—"
    avg_mae_safety = f"{round(trades_df['SL Safety %'].mean(), 1)}%" if "SL Safety %" in trades_df.columns else "—"

    conds = []
    for col in ["Entry Conditions", "Pattern", "pattern"]:
        if col in trades_df.columns:
            conds = trades_df[col].dropna().unique().tolist()
            break
    cond_str = " | ".join(map(str, conds)) if conds else "اختراق خط العنق"

    st.info(f"**شروط الدخول:** {cond_str} | **دقة الهيكل:** {avg_symmetry}")
    st.success(f"📈 **متوسط الحركة:** السوق يصل إلى **{avg_mfe}** قبل الارتداد، SL Safety: **{avg_mae_safety}**")

    # Download
    csv_symbol = trades_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label=f"📥 تنزيل صفقات {active_sym} (CSV)",
        data=csv_symbol,
        file_name=f"backtest_{active_sym.replace('=', '_')}_{period_display.replace(' ', '_').replace('/', '-')}.csv",
        mime="text/csv", use_container_width=True
    )

    # Chart
    if active_sym in dfs_dict and not dfs_dict[active_sym].empty:
        df_res = dfs_dict[active_sym].copy()
        df_res['EMA50']  = df_res['Close'].ewm(span=50,  adjust=False).mean()
        df_res['EMA200'] = df_res['Close'].ewm(span=200, adjust=False).mean()

        fig = go.Figure(data=[go.Candlestick(
            x=df_res.index, open=df_res["Open"], high=df_res["High"],
            low=df_res["Low"], close=df_res["Close"], name="السعر"
        )])
        fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA50'],
                                 line=dict(color='orange', width=1.2), name="EMA 50"))
        fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA200'],
                                 line=dict(color='blue', width=1.2), name="EMA 200"))

        if "nodes" in trades_df.columns:
            for idx, row in trades_df.iterrows():
                if isinstance(row.get('nodes'), list) and row['nodes']:
                    sn = sorted(row['nodes'], key=lambda x: pd.to_datetime(x[0]))
                    fig.add_trace(go.Scatter(
                        x=[n[0] for n in sn], y=[n[1] for n in sn],
                        mode="lines+markers", name=f"نمط #{idx+1}"
                    ))

        fig.update_layout(
            template="plotly_white", height=600, autosize=True,
            margin=dict(l=80, r=20, t=40, b=40),
            xaxis_rangeslider_visible=False,
            yaxis=dict(side="left", automargin=True,
                       tickfont=dict(size=12, color="#333"),
                       showgrid=True, gridcolor="#E5E5E5"),
            xaxis=dict(automargin=True, tickfont=dict(size=10)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True, config={'responsive': True})

    # Table
    display_cols = [c for c in [
        "Entry Date", "Exit Date", "Symbol", "symbol", "Bias", "bias", "Result",
        "Entry Price", "Entry", "Exit Price", "Stop Loss", "SL", "Take Profit", "TP",
        "Pips", "Risk_Pips", "Reward_Pips", "RR_Ratio", "PnL_USD", "Loss Category"
    ] if c in trades_df.columns]
    st.dataframe(trades_df[display_cols] if display_cols else trades_df,
                 use_container_width=True)

    # Talo — signal u rar calculator
    if st.button(f"🔗 Isticmaal xogta {active_sym} xisaabiyaha", use_container_width=True):
        st.session_state["active_signal_symbol"] = active_sym
        if len(trades_df) > 0:
            last_row = trades_df.iloc[-1]
            st.session_state["active_signal_entry"] = last_row.get("Entry Price") or last_row.get("Entry")
            st.session_state["active_signal_sl"]    = last_row.get("Stop Loss") or last_row.get("SL")
            st.session_state["active_signal_tp"]    = last_row.get("Take Profit") or last_row.get("TP")
            st.session_state["active_signal_bias"]  = last_row.get("bias") or last_row.get("Bias")
        st.success("✅ Xogta la raray xisaabiyaha — hoos u eeg")

    # Report
    with st.expander("🔬 التقرير التشخيصي الذكي", expanded=False):
        if diagnose_filters is None:
            st.error("⚠️ `diagnose_filters` oo maqan — ku dar `engine.py`")
        else:
            try:
                df_for_diag = dfs_dict.get(active_sym)
                if df_for_diag is not None and not df_for_diag.empty:
                    with st.spinner("جاري التشخيص..."):
                        diag = diagnose_filters(df_for_diag,
                                                interval=selected_interval,
                                                symbol=active_sym)
                    if diag.get("error"):
                        st.error(f"❌ {diag['error']}")
                    else:
                        col1, col2, col3 = st.columns(3)
                        col1.metric("أنماط خام", diag["total_raw_candidates"])
                        col2.metric("بعد الفلاتر", diag["final_count"])
                        col3.metric("نسبة القبول",
                            f"{round(diag['final_count'] / max(diag['total_raw_candidates'], 1) * 100, 1)}%")

                        smart = diag.get("smart_diagnosis", {})
                        if smart.get("verdict"):
                            st.markdown(f"### 🎯 الحكم: {smart['verdict']}")

                        wb = smart.get("win_breakdown", {})
                        if wb.get("total_wins", 0) > 0:
                            st.markdown("#### ✅ الصفقات الناجحة")
                            w1, w2 = st.columns(2)
                            w1.metric("العدد", wb["total_wins"])
                            w2.metric("متوسط الوصول", f"{wb['avg_max_reach']}%")

                        lb = smart.get("loss_breakdown", {})
                        if any(v > 0 for v in lb.values()):
                            st.markdown("#### ❌ الخاسرة")
                            f1, f2, f3, f4 = st.columns(4)
                            f1.metric("رفض فوري", lb.get("immediate_rejection", 0))
                            f2.metric("انعكاس مبكر", lb.get("early_reversal", 0))
                            f3.metric("انعكاس متوسط", lb.get("mid_reversal", 0))
                            f4.metric("انعكاس متأخر", lb.get("late_reversal", 0))

                            u1, u2 = st.columns(2)
                            u1.metric("⚪ لا مفر", lb.get("unavoidable", 0))
                            u2.metric("🔴 قابلة للتجنب", lb.get("avoidable", 0))

                        if smart.get("action_plan"):
                            st.markdown("#### 🎯 خطة العمل")
                            for item in smart["action_plan"]:
                                if item.startswith("🔴"):   st.error(item)
                                elif item.startswith("🟡"): st.warning(item)
                                elif item.startswith("🟢"): st.success(item)
                                else:                       st.info(item)

                        trades_analysis = diag.get("trade_analysis", [])
                        if trades_analysis:
                            st.markdown("#### 📋 تحليل كل صفقة")
                            trade_table = pd.DataFrame([{
                                "#": t["trade_num"],
                                "الاتجاه": t["bias"],
                                "النتيجة": t["result"],
                                "التصنيف": {
                                    "immediate_rejection": "🔴 رفض فوري",
                                    "early_reversal": "🟠 انعكاس مبكر",
                                    "mid_reversal": "🟡 انعكاس متوسط",
                                    "late_reversal": "⚪ انعكاس متأخر",
                                    "breakeven": "⚖️ تعادل",
                                    "timeout": "⏰ انتهاء وقت",
                                    "success": "✅ نجاح",
                                    "open": "⏳ مفتوحة",
                                }.get(t["category"], t["category"]),
                                "الوصول %": f"{t['max_reach_%']}%",
                                "R:R": t["rr_ratio"],
                                "لا مفر": "نعم" if t["is_unavoidable"] else "لا",
                                "السبب": t["reason"][:80] + "..." if len(t["reason"]) > 80 else t["reason"],
                                "التصرف": t.get("action", "—"),
                                "الوقاية": t.get("prevention", "—"),
                            } for t in trades_analysis])
                            st.dataframe(trade_table, use_container_width=True)

                        st.markdown("#### 📊 مراحل الفلترة")
                        stages_data = []
                        for stage_name, stage_data in diag["stages"].items():
                            stages_data.append({
                                "الفلتر": stage_name,
                                "قبل": stage_data.get("before", 0),
                                "بعد": stage_data.get("after", 0),
                                "مرفوض": stage_data.get("rejected", 0),
                                "نسبة القبول": stage_data.get("pass_rate", "0%"),
                            })
                        st.dataframe(pd.DataFrame(stages_data), use_container_width=True)

                        if diag["recommendations"]:
                            st.markdown("#### 🎯 توصيات عامة")
                            for r in diag["recommendations"]:
                                if "حرج" in r["severity"]:   st.error(f"🔴 {r['message']}")
                                elif "متوسط" in r["severity"]: st.warning(f"🟡 {r['message']}")
                                else:                          st.info(f"ℹ️ {r['message']}")
            except Exception as e:
                import traceback
                st.error(f"⚠️ خطأ: {type(e).__name__}: {e}")
                st.code(traceback.format_exc()) 


# ══════════════════════════════════════════════════════════════════════════════
# ================= LIVE SCAN MODE =================
# ══════════════════════════════════════════════════════════════════════════════
else:

    scan_mode = st.radio(
        "طريقة الفحص:",
        ["سهم فردي", "مسح كلي لشيت الأصول"],
        horizontal=True, key="live_scan_mode"
    )

    if scan_mode == "سهم فردي":
        symbols = [st.text_input("رمز الأصل", value="NZDCAD=X", key="live_single_symbol")]
    else:
        try:
            symbols = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]
        except Exception as e:
            st.error(f"⚠️ فشل جلب الرموز: {e}")
            symbols = ["NZDCAD=X"]

    c1, c2 = st.columns(2)
    selected_interval = c1.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=9, key="live_interval")
    selected_period = c2.selectbox(
        "📅 نطاق البيانات:",
        ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
        index=3, key="live_period"
    )

    if st.button("🚀 بدء المسح والتحليل الفوري", use_container_width=True) and symbols:
        valid = []; p_bar = st.progress(0); s_txt = st.empty(); error_log = []
        dl_int = selected_interval if selected_interval in ["1m","5m","15m","30m","1h","1d","1wk","1mo"] else "1h"

        for idx, sym in enumerate(symbols):
            s_txt.text(f"فحص ({idx+1}/{len(symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(symbols))
            try:
                sym_fixed = fix_symbol(sym)
                df = yf.download(sym_fixed, period=selected_period, interval=dl_int,
                                 progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if df is None or df.empty:
                    error_log.append(f"⚠️ {sym}: لا توجد بيانات"); continue
                if len(df) >= 20:
                    res = run_full_analysis(df, interval=selected_interval, symbol=sym)
                    if res["signal"] in ["STRONG BUY", "STRONG SELL"] or scan_mode == "سهم فردي":
                        valid.append({"symbol": sym, "result": res})
                    else:
                        if scan_mode == "سهم فردي":
                            st.info(f"ℹ️ {sym}: لا يوجد نمط حالياً (Signal: {res['signal']})")
            except Exception as e:
                error_log.append(f"❌ {sym}: {type(e).__name__}: {e}")

        s_txt.empty(); p_bar.empty()
        st.session_state.scanned_signals = valid
        if error_log:
            with st.expander(f"⚠️ تحذيرات ({len(error_log)})"):
                for msg in error_log: st.text(msg)

    # ══════════════════════════════════════════════════════════════════════════
    # ⏳ NEAR SIGNALS — Raadi signals-ka dhow inay jabaan
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### ⏳ Baaritaanka Signals-ka Dhow (Near Signals)")

    col_prox, col_limit = st.columns([3, 1])
    with col_prox:
        proximity_pct = st.slider(
            "Masaafada u dhow (%):",
            min_value=0.5, max_value=10.0, value=2.0, step=0.5,
            help="Meeqa % u dhow yahay neckline. 2% = caadi, 1% = adag, 5% = fudud",
            key="near_prox"
        )
    with col_limit:
        max_near_check = st.number_input(
            "Xadka baaritaanka:",
            min_value=5, max_value=50, value=20, step=5,
            key="near_limit"
        )

    if st.button("⏳ Raadi signals-ka dhow inay jabaan", use_container_width=True):
        near = []
        p_bar2 = st.progress(0)
        s_txt2 = st.empty()
        check_list = symbols[:int(max_near_check)]

        for idx, sym in enumerate(check_list):
            s_txt2.text(f"Baaraya ({idx+1}/{len(check_list)}): {sym}...")
            p_bar2.progress((idx + 1) / len(check_list))
            try:
                sym_fixed = fix_symbol(sym)
                df_n = yf.download(sym_fixed, period=selected_period,
                                   interval=dl_int,
                                   progress=False, auto_adjust=False)
                if isinstance(df_n.columns, pd.MultiIndex):
                    df_n.columns = df_n.columns.get_level_values(0)
                if df_n is None or df_n.empty or len(df_n) < 30:
                    continue
                ns = detect_near_signals(
                    df_n,
                    interval=selected_interval,
                    symbol=sym,
                    proximity_pct=proximity_pct
                )
                if ns:
                    near.extend(ns)
            except Exception:
                continue

        s_txt2.empty(); p_bar2.empty()
        st.session_state.near_signals = near
        if near:
            st.success(f"✅ La helay **{len(near)}** signal oo dhow inay jabaan")
        else:
            st.info(f"ℹ️ Ma jiraan signals dhow (proximity = {proximity_pct}%). Isku day qiime sare.")

    # ══════════════════════════════════════════════════════════════════════════
    # ⏳ Render Near Signals — Halkan
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.get("near_signals"):
        with st.expander("⏳ ليستة المراقبة — Signals قريبة من الكسر", expanded=True):
            render_near_signals(st.session_state.near_signals)

    # ══════════════════════════════════════════════════════════════════════════
    # 📊 Natiijada Signal-ka Firfircoon
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.scanned_signals:
        sigs = st.session_state.scanned_signals
        if scan_mode == "مسح كلي لشيت الأصول":
            opts = [f"{i['symbol']} | {i['result']['signal']}" for i in sigs]
            active_res = sigs[opts.index(st.selectbox("👇 اختر الأصل:", opts))]['result']
        else:
            active_res = sigs[0]['result']

        active_sym = active_res.get("symbol", symbols[0] if symbols else "N/A")
        st.session_state.current_symbol = active_sym

        # Isku xir signal-ka xisaabiyaha
        st.session_state["active_signal_symbol"] = active_sym
        st.session_state["active_signal_entry"]  = active_res.get("entry")
        st.session_state["active_signal_sl"]     = active_res.get("sl")
        st.session_state["active_signal_tp"]     = active_res.get("tp")
        st.session_state["active_signal_bias"]   = active_res.get("bias")

        e1, e2, e3 = st.columns(3)
        e1.metric("🎯 سعر الدخول", f"{active_res.get('entry', 0)}")
        e2.metric("🛑 وقف الخسارة", f"{active_res.get('sl', 0)}")
        e3.metric("🏆 الهدف",       f"{active_res.get('tp', 0)}")

        _live_entry = active_res.get('entry') or 0
        _live_sl    = active_res.get('sl')    or 0
        _live_tp    = active_res.get('tp')    or 0
        _pip = pip_size_for(active_sym)
        _risk_pips   = round(abs(_live_entry - _live_sl) / _pip, 1) if _live_entry and _live_sl else 0
        _reward_pips = round(abs(_live_tp - _live_entry) / _pip, 1) if _live_entry and _live_tp else 0
        _rr = round(_reward_pips / _risk_pips, 2) if _risk_pips > 0 else "—"

        e4, e5, e6 = st.columns(3)
        e4.metric("📏 نقاط المخاطرة", _risk_pips)
        e5.metric("🎯 نقاط الهدف",   _reward_pips)
        e6.metric("⚖️ R:R",          _rr)

        df_res = active_res.get("df")
        if df_res is not None and not df_res.empty:
            df_res = df_res.copy()
            df_res['EMA50']  = df_res['Close'].ewm(span=50,  adjust=False).mean()
            df_res['EMA200'] = df_res['Close'].ewm(span=200, adjust=False).mean()

            fig = go.Figure(data=[go.Candlestick(
                x=df_res.index, open=df_res["Open"], high=df_res["High"],
                low=df_res["Low"], close=df_res["Close"], name="السعر"
            )])
            fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA50'],
                                     line=dict(color='orange', width=1.2), name="EMA 50"))
            fig.add_trace(go.Scatter(x=df_res.index, y=df_res['EMA200'],
                                     line=dict(color='blue', width=1.2), name="EMA 200"))

            live_nodes = active_res.get("nodes") or active_res.get("pattern_nodes")
            if isinstance(live_nodes, list) and live_nodes:
                sn = sorted(live_nodes, key=lambda x: pd.to_datetime(x[0]))
                fig.add_trace(go.Scatter(
                    x=[n[0] for n in sn], y=[n[1] for n in sn],
                    mode="lines+markers", name="النمط المكتشف",
                    line=dict(color="#9C27B0", width=2), marker=dict(size=8)
                ))

            for val, col, txt in [
                (active_res.get('entry'), "#2196F3", "دخول"),
                (active_res.get('sl'),    "#F44336", "وقف"),
                (active_res.get('tp'),    "#4CAF50", "هدف"),
            ]:
                if val:
                    fig.add_hline(y=val, line_dash="dash", line_color=col, annotation_text=txt)

            fig.update_layout(
                template="plotly_white", height=600, autosize=True,
                margin=dict(l=80, r=20, t=40, b=40),
                xaxis_rangeslider_visible=False,
                yaxis=dict(side="left", automargin=True,
                           tickfont=dict(size=12, color="#333"),
                           showgrid=True, gridcolor="#E5E5E5"),
                xaxis=dict(automargin=True, tickfont=dict(size=10)),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True, config={'responsive': True})

        # Smart Diagnosis — Live
        with st.expander("🔬 تشخيص النمط الحالي — Live", expanded=False):
            df_for_live = active_res.get("df")
            if df_for_live is not None and not df_for_live.empty and diagnose_filters is not None:
                try:
                    with st.spinner("جاري التشخيص..."):
                        diag_live = diagnose_filters(df_for_live,
                                                    interval=selected_interval,
                                                    symbol=active_sym)
                    if not diag_live.get("error"):
                        col1, col2, col3 = st.columns(3)
                        col1.metric("أنماط خام", diag_live["total_raw_candidates"])
                        col2.metric("بعد الفلاتر", diag_live["final_count"])
                        col3.metric("نسبة القبول",
                            f"{round(diag_live['final_count'] / max(diag_live['total_raw_candidates'], 1) * 100, 1)}%")

                        smart = diag_live.get("smart_diagnosis", {})
                        if smart.get("verdict"):
                            st.markdown(f"### 🎯 {smart['verdict']}")

                        if smart.get("action_plan"):
                            st.markdown("#### 🎯 خطة العمل")
                            for item in smart["action_plan"]:
                                if item.startswith("🔴"):   st.error(item)
                                elif item.startswith("🟡"): st.warning(item)
                                elif item.startswith("🟢"): st.success(item)
                                else:                       st.info(item)

                        st.markdown("#### 📊 مراحل الفلترة")
                        stages_data = []
                        for stage_name, stage_data in diag_live["stages"].items():
                            stages_data.append({
                                "الفلتر": stage_name,
                                "قبل": stage_data.get("before", 0),
                                "بعد": stage_data.get("after", 0),
                                "مرفوض": stage_data.get("rejected", 0),
                                "نسبة القبول": stage_data.get("pass_rate", "0%"),
                            })
                        st.dataframe(pd.DataFrame(stages_data), use_container_width=True)
                except Exception as e:
                    st.error(f"⚠️ خطأ: {type(e).__name__}: {e}")
            elif diagnose_filters is None:
                st.warning("⚠️ `diagnose_filters` oo maqan")
            else:
                st.info("ℹ️ Xog ku filan ma jirto") 


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 TILMAAMAHA DEGDEGGA — Wuxuu shaqeeyaa labada nooc
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")

if app_mode == "🧪 مختبر الاختبار الرجعي (Backtest)":
    if st.session_state.backtest_scanned_signals:
        _bt_item = st.session_state.backtest_scanned_signals[-1]
        _bt_trades = _bt_item["trades_df"].copy()
        _bt_trades = compute_pips(_bt_trades)
        _bt_trades = compute_dollar_pnl(_bt_trades, lot=st.session_state.get("bt_lot_size", 0.01))
        with st.expander("🎯 التصرفات المطلوبة الآن", expanded=False):
            render_realtime_actions(_bt_trades, is_live=False)
    else:
        with st.expander("🎯 التصرفات المطلوبة الآن", expanded=False):
            st.info("ℹ️ Bilow backtest si aad u aragto tilmaamaha")
else:
    if st.session_state.scanned_signals:
        with st.expander("🎯 التصرفات المطلوبة الآن", expanded=True):
            _live_df = pd.DataFrame([{
                "symbol": i["symbol"],
                "Entry Price": i["result"].get("entry"),
                "Stop Loss": i["result"].get("sl"),
                "Take Profit": i["result"].get("tp"),
                "bias": i["result"].get("bias"),
                "Result": "OPEN",
                "Max Reach %": i["result"].get("Max Reach %", 0),
                "Lot": 0.01,
            } for i in st.session_state.scanned_signals])
            render_realtime_actions(_live_df, is_live=True)
    else:
        with st.expander("🎯 التصرفات المطلوبة الآن", expanded=False):
            st.info("ℹ️ Bilow scan-ka si aad u aragto tilmaamaha")


# ══════════════════════════════════════════════════════════════════════════════
# 💰 XISAABIYAHA KHATARTA — Wuxuu shaqeeyaa labada nooc
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("💰 حاسبة المخاطرة المتقدمة", expanded=False):
    render_advanced_risk_calculator(unique_id="end")


# ══════════════════════════════════════════════════════════════════════════════
# ⏳ LIISKA WAARITAANKA — Signals-ka dhow inay jabaan
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")

with st.expander("⏳ ليستة المراقبة — Signals قريبة من الكسر", expanded=False):
    if st.session_state.get("near_signals"):
        render_near_signals(st.session_state.near_signals)
    else:
        st.info("ℹ️ Riix '⏳ Raadi signals-ka dhow' ee Live Scan si aad u buuxiso liiska")
        st.caption("""
        **Sida loo isticmaalo:**
        1. Tag **🚀 الماسح الحي للأسواق**
        2. Riix **"⏳ Raadi signals-ka dhow inay jabaan"**
        3. Halkan waxaa ka soo muuqan doona liiska signals-ka dhow
        4. Dooro mid → u rar xisaabiyaha
        """)


# ══════════════════════════════════════════════════════════════════════════════
# 📊 JADWALKA GUUD — IC Markets Standard
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### 📊 Jadwalka IC Markets Standard — 50 Pairs")

ic_display = []
for key, spec in IC_MARKETS_SPECS.items():
    ic_display.append({
        "Zoug": key,
        "Nooca": spec["cat"],
        "Contract": f"{spec['contract']:,}",
        "Min Lot": spec["min_lot"],
        "Step": spec["step"],
        "Pip Size": spec["pip"],
    })

st.dataframe(
    pd.DataFrame(ic_display),
    use_container_width=True,
    hide_index=True
)


# ══════════════════════════════════════════════════════════════════════════════
# 📖 SHARAXAAD — Sida loo isticmaalo
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")

with st.expander("📖 Sida loo isticmaalo App-ka", expanded=False):
    st.markdown("""
    ## 🚀 Habka 1: Live Scan (Suuqa Hadda)

    1. Tag **🚀 الماسح الحي للأسواق**
    2. Dooro **"سهم فردي"** ama **"مسح كلي لشيت الأصول"**
    3. Dooro **Interval** (1h, 4h, 1d) iyo **Period** (3mo, 6mo)
    4. Riix **"🚀 بدء المسح والتحليل الفوري"**
    5. Eeg natiijada — signals-ka furan

    ### ⏳ Near Signals (Signals-ka Dhow):
    - Riix **"⏳ Raadi signals-ka dhow inay jabaan"**
    - Dooro **proximity %** (1% = adag, 2% = caadi, 5% = fudud)
    - Liiska ayaa soo muuqan doona — dhow inay jabaan

    ---

    ## 🧪 Habka 2: Backtest (Taariikh)

    1. Tag **🧪 مختبر الاختبار الرجعي (Backtest)**
    2. Dooro **"سهم فردي"** ama **"مسح كلي لشيت الأصول"**
    3. Dooro **Period** (شهر، نطاق مخصص، أشهر متعددة، سنة كاملة)
    4. Dooro **Interval** (5m, 15m, 1h, 4h, 1d)
    5. Geli **Lot Size** (0.01 = min)
    6. Riix **"📊 بدء محاكاة الاختبار الرجعي"**
    7. Eeg:
       - 📊 الملخص الإجمالي
       - 📈 نتائج كل symbol
       - 🔬 التقرير التشخيصي
       - 📥 Download CSV

    ---

    ## 💰 Risk Calculator (Xisaabiyaha Khatarta)

    1. Geli **رأس المال** (Capital, tusaale: $1000)
    2. Dooro **نسبة المخاطرة** (1% - 10%, caadi 5%)
    3. Dooro **Source**:
       - 📋 **الإشارات النشطة** — signals furan
       - ⏳ **المراقبة (قريب)** — dhow inay jabaan
       - 📚 **القائمة الكاملة** — 50 pairs
    4. Ku qor **magaca** (EUR, GBP, BTC...) si aad u raadiso
    5. Dooro **symbol** → lot
    6. Riix **"⚡ TP (R:R = 1:2)"** si aad u hesho TP sax ah
    7. Eeg natiijada:
       - ✅ **مقبولة** → Furi trade
       - ❌ **مرفوضة** → Yaree lot ama SL

    ---

    ## 🎯 Realtime Actions (Tilmaamaha Degdegga)

    Marka trade-kaagu socdo:
    - 25% → nalka **"نقل SL إلى التعادل"**
    - 50% → nalka **"تفعيل Trailing 30%"**
    - 80% → nalka **"إغلاق 50% + Trailing 60%"**

    ---

    ## ⚠️ Digniin

    - **Risk per trade ≤ 5%** — muhiim!
    - **Demo 3 bilood** ka hor live
    - **Max 3-5 trades furan** isku mar
    - **Ha ka boodin stop loss** — waa xeer

    ---

    ## 🔧 Fixes la sameeyay

    - ✅ **XAUUSD** → `GC=F` (Yahoo Gold)
    - ✅ **GBPADY=X** → `GBPNZD=X`
    - ✅ **Y-axis** bidix (qiimaha wuu muuqdaa)
    - ✅ **IC Markets specs** — 50 pairs
    - ✅ **Search** xisaabiyaha
    - ✅ **Near signals** detection
    - ✅ **Tareen degdeg** (CSS optimized)
    """)
