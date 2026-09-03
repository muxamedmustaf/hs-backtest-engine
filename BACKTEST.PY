
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import importlib
import engine
from datetime import datetime

# ==========================================================
# BACKTEST.PY
# اختبار احترافي لـ Head & Shoulders / Inverse H&S
# يعتمد على engine.py الحالي بدون تعديل منطق المحرك
#
# الوظائف:
# 1) عدّ الإشارات الحقيقية
# 2) اختبار Entry لكل إشارة
# 3) SL عند الكتف الأيمن
# 4) قياس TP + التجاوز + الرجوع بعد TP
# 5) مقارنة Shoulder SL مع Head SL
# 6) Dashboard واضح
# 7) مقارنة جميع Timeframes من 5m إلى 1D
# ==========================================================

st.set_page_config(
    page_title="H&S Backtest Pro",
    page_icon="📊",
    layout="wide"
)

# إعادة تحميل آخر نسخة من engine.py
engine = importlib.reload(engine)

# ==========================================================
# إعدادات الواجهة
# ==========================================================

st.title("📊 H&S Backtest Pro")
st.caption(
    "اختبار تاريخي لـ Head & Shoulders و Inverse Head & Shoulders "
    "باستخدام engine.py الحالي."
)

st.sidebar.header("⚙️ إعدادات الاختبار")

symbol = st.sidebar.text_input(
    "Symbol",
    "NZDCAD=X"
).strip()

period = st.sidebar.selectbox(
    "الفترة التاريخية",
    ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
    index=2
)

timeframes = st.sidebar.multiselect(
    "Timeframes",
    ["5m", "15m", "30m", "1h", "2h", "4h", "1d"],
    default=["5m", "15m", "30m", "1h", "2h", "4h", "1d"]
)

# عدد الشموع التي لا تدخل فيها الصفقة إذا لم يكن هناك TP/SL
# نتركها مفتوحة حتى نهاية البيانات افتراضياً.
MAX_HOLDING_CANDLES = st.sidebar.number_input(
    "الحد الأقصى لشموع الصفقة (0 = حتى نهاية البيانات)",
    min_value=0,
    value=0,
    step=10
)

run = st.sidebar.button(
    "🚀 تشغيل الاختبار الكامل",
    use_container_width=True
)

# ==========================================================
# أدوات مساعدة
# ==========================================================

def normalize_ohlcv(df):
    """تنظيف بيانات Yahoo وتحويل الأعمدة إلى OHLC عادية."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        # yfinance قد يعيد MultiIndex
        if "Close" in df.columns.get_level_values(0):
            df.columns = df.columns.get_level_values(0)
        else:
            df.columns = [
                c[0] if isinstance(c, tuple) else c
                for c in df.columns
            ]

    required = ["Open", "High", "Low", "Close"]

    missing = [c for c in required if c not in df.columns]
    if missing:
        return pd.DataFrame()

    df = df[required].copy()

    for col in required:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(subset=required)

    # إزالة التكرار في الفهرس
    df = df[~df.index.duplicated(keep="last")]

    # ترتيب زمني
    df = df.sort_index()

    return df


def resample_4h(df):
    """تجميع 1H إلى 4H."""
    if df.empty:
        return df

    out = (
        df.resample("4h")
        .agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last"
        })
        .dropna()
    )

    return out


def download_timeframe(symbol, period, timeframe):
    """
    جلب البيانات من Yahoo.
    Yahoo لا يوفر كل الفواصل الصغيرة لنفس المدة.
    لذلك يتم اختيار مصدر مناسب ثم التجميع عند الحاجة.
    """
    # Yahoo يفرض قيوداً على intraday:
    # 5m/15m/30m/1h غالباً تكون لفترات أقصر.
    if timeframe == "4h":
        raw_interval = "1h"
    elif timeframe == "2h":
        raw_interval = "1h"
    else:
        raw_interval = timeframe

    try:
        data = yf.download(
            symbol,
            period=period,
            interval=raw_interval,
            progress=False,
            auto_adjust=False,
            threads=False
        )
    except Exception as e:
        return pd.DataFrame(), str(e)

    data = normalize_ohlcv(data)

    if data.empty:
        return data, (
            "لم تتوفر بيانات بهذا الـTimeframe/الفترة "
            "من Yahoo Finance."
        )

    if timeframe == "2h":
        data = (
            data.resample("2h")
            .agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last"
            })
            .dropna()
        )

    elif timeframe == "4h":
        data = resample_4h(data)

    return data, None


def safe_float(value):
    try:
        if value is None:
            return None
        value = float(value)
        if not np.isfinite(value):
            return None
        return value
    except Exception:
        return None


def normalize_timestamp(value):
    """تحويل timestamp إلى قيمة قابلة للمقارنة."""
    try:
        return pd.Timestamp(value)
    except Exception:
        return None


def pattern_key(result):
    """
    مفتاح يمنع عدّ نفس النمط مرات عديدة أثناء
    تحرك نافذة الاختبار.
    """
    pattern = str(result.get("pattern", ""))

    nodes = result.get("nodes", [])

    if len(nodes) >= 6:
        first_six = nodes[:6]
        parts = []

        for node in first_six:
            try:
                ts = str(node[0])
                val = round(float(node[1]), 8)
                parts.append((ts, val))
            except Exception:
                pass

        if len(parts) == 6:
            return (
                pattern,
                tuple(parts)
            )

    # fallback
    end_time = None
    if nodes:
        try:
            end_time = str(nodes[-1][0])
        except Exception:
            pass

    return (
        pattern,
        end_time,
        safe_float(result.get("entry")),
        safe_float(result.get("tp"))
    )


def extract_signal(result, full_df):
    """
    استخراج معلومات الإشارة من نتيجة engine.py.
    نستخدم آخر node لأنه في engine الحالي هو شمعة breakout.
    """
    if not isinstance(result, dict):
        return None

    pattern = str(
        result.get("pattern")
        or result.get("name")
        or ""
    )

    p_lower = pattern.lower()

    if (
        "head" not in p_lower
        or "shoulder" not in p_lower
    ):
        return None

    if (
        "head and shoulders" not in p_lower
        and "inverse head and shoulders" not in p_lower
    ):
        return None

    entry = safe_float(
        result.get(
            "entry",
            result.get("entry_trigger")
        )
    )

    tp = safe_float(
        result.get(
            "tp",
            result.get("target")
        )
    )

    nodes = result.get("nodes", [])

    if len(nodes) < 6:
        return None

    try:
        pivots = nodes[:6]

        pivot_times = [
            normalize_timestamp(x[0])
            for x in pivots
        ]

        pivot_values = [
            safe_float(x[1])
            for x in pivots
        ]

        if any(x is None for x in pivot_times):
            return None

        if any(x is None for x in pivot_values):
            return None

    except Exception:
        return None

    # آخر node يضاف في engine.py هو breakout
    breakout_time = None
    breakout_price = None

    if len(nodes) >= 7:
        try:
            breakout_time = normalize_timestamp(
                nodes[-1][0]
            )
            breakout_price = safe_float(
                nodes[-1][1]
            )
        except Exception:
            pass

    if breakout_time is None:
        # fallback: neckline end
        try:
            breakout_time = normalize_timestamp(
                result.get("neckline_end_idx")
            )
        except Exception:
            pass

    if breakout_time is None:
        return None

    try:
        breakout_pos = full_df.index.get_loc(
            breakout_time
        )
    except Exception:
        # get_loc قد يعيد slice في حالات نادرة
        try:
            matches = np.where(
                full_df.index == breakout_time
            )[0]
            if len(matches) == 0:
                return None
            breakout_pos = int(matches[-1])
        except Exception:
            return None

    if not isinstance(breakout_pos, (int, np.integer)):
        try:
            breakout_pos = int(np.asarray(breakout_pos).ravel()[-1])
        except Exception:
            return None

    direction = (
        "Bearish"
        if "inverse" not in p_lower
        else "Bullish"
    )

    # ------------------------------------------------------
    # النقاط:
    #
    # H&S:
    # p = L0, H1, L1, H2, L2, H3
    # Right Shoulder = H3
    # Head = H2
    #
    # Inverse:
    # p = H0, L1, H1, L2, H2, L3
    # Right Shoulder = L3
    # Head = L2
    # ------------------------------------------------------

    if direction == "Bearish":
        head_sl = pivot_values[3]
        shoulder_sl = pivot_values[5]
    else:
        head_sl = pivot_values[3]
        shoulder_sl = pivot_values[5]

    if entry is None or tp is None:
        return None

    if direction == "Bearish":
        if not (
            shoulder_sl > entry
            and head_sl > entry
            and tp < entry
        ):
            return None
    else:
        if not (
            shoulder_sl < entry
            and head_sl < entry
            and tp > entry
        ):
            return None

    return {
        "key": pattern_key(result),
        "pattern": pattern,
        "direction": direction,
        "entry": entry,
        "tp": tp,
        "head_sl": head_sl,
        "shoulder_sl": shoulder_sl,
        "breakout_time": breakout_time,
        "breakout_pos": int(breakout_pos),
        "breakout_price": (
            breakout_price
            if breakout_price is not None
            else safe_float(
                full_df["Close"].iloc[breakout_pos]
            )
        ),
        "nodes": nodes
    }


def first_touch_result(
    df,
    start_pos,
    entry,
    tp,
    sl,
    direction,
    max_holding=0
):
    """
    يراقب الشموع بعد breakout.

    إذا لامست الشمعة TP وSL معاً:
    نعتبر SL أولاً (قاعدة محافظة).

    النتيجة:
      TP = TP hit first
      SL = SL hit first
      OPEN = لم يصل لأي منهما
    """
    n = len(df)

    start = start_pos + 1

    if start >= n:
        return {
            "result": "OPEN",
            "hit_pos": None,
            "hit_time": None,
            "mfe_pct": 0.0,
            "mae_pct": 0.0,
            "bars_to_result": None,
            "tp_extension_pct": 0.0,
            "reversed_after_tp": False,
            "max_after_tp_pct": 0.0,
            "return_after_tp_to_entry": False
        }

    stop = n

    if max_holding and max_holding > 0:
        stop = min(
            n,
            start + int(max_holding)
        )

    result = "OPEN"
    hit_pos = None
    hit_time = None

    mfe = 0.0
    mae = 0.0

    tp_hit_price = None
    tp_hit_pos = None

    # ------------------------------------------------------
    # مراقبة TP / SL
    # ------------------------------------------------------

    for pos in range(start, stop):

        high = float(df["High"].iloc[pos])
        low = float(df["Low"].iloc[pos])

        if direction == "Bearish":
            favorable = (
                (entry - low) / entry * 100
            )

            adverse = (
                (high - entry) / entry * 100
            )

            mfe = max(mfe, favorable)
            mae = max(mae, adverse)

            tp_hit = low <= tp
            sl_hit = high >= sl

        else:
            favorable = (
                (high - entry) / entry * 100
            )

            adverse = (
                (entry - low) / entry * 100
            )

            mfe = max(mfe, favorable)
            mae = max(mae, adverse)

            tp_hit = high >= tp
            sl_hit = low <= sl

        # إذا حدث الاثنان داخل نفس الشمعة:
        # القاعدة المحافظة = SL أولاً
        if tp_hit and sl_hit:
            result = "SL"
            hit_pos = pos
            hit_time = df.index[pos]
            break

        if sl_hit:
            result = "SL"
            hit_pos = pos
            hit_time = df.index[pos]
            break

        if tp_hit:
            result = "TP"
            hit_pos = pos
            hit_time = df.index[pos]
            tp_hit_price = tp
            tp_hit_pos = pos
            break

    # ------------------------------------------------------
    # إذا لم يصل TP بعد، لا توجد عملية "بعد TP"
    # ------------------------------------------------------

    if result != "TP":
        return {
            "result": result,
            "hit_pos": hit_pos,
            "hit_time": hit_time,
            "mfe_pct": mfe,
            "mae_pct": mae,
            "bars_to_result": (
                hit_pos - start + 1
                if hit_pos is not None
                else None
            ),
            "tp_extension_pct": 0.0,
            "reversed_after_tp": False,
            "max_after_tp_pct": 0.0,
            "return_after_tp_to_entry": False
        }

    # ------------------------------------------------------
    # TP تحقق.
    # الآن نبحث:
    # 1) هل السعر تجاوز TP؟
    # 2) هل عاد بعد ذلك؟
    # ------------------------------------------------------

    max_after_tp = 0.0
    reversed_after_tp = False
    returned_to_entry = False

    for pos in range(
        tp_hit_pos,
        stop
    ):
        high = float(df["High"].iloc[pos])
        low = float(df["Low"].iloc[pos])

        if direction == "Bearish":
            extension = (
                (tp - low) / entry * 100
            )
            max_after_tp = max(
                max_after_tp,
                extension
            )

            # رجوع إلى Entry أو أعلى
            if high >= entry:
                returned_to_entry = True

        else:
            extension = (
                (high - tp) / entry * 100
            )
            max_after_tp = max(
                max_after_tp,
                extension
            )

            # رجوع إلى Entry أو أقل
            if low <= entry:
                returned_to_entry = True

        # تعريف "الرجوع":
        # بعد تحقيق TP عاد السعر إلى منطقة Entry.
        if returned_to_entry:
            reversed_after_tp = True
            break

    # نسبة التجاوز فوق TP فقط
    if direction == "Bearish":
        max_favorable_price = min(
            float(df["Low"].iloc[tp_hit_pos:stop].min()),
            tp
        )
        tp_extension_pct = max(
            0.0,
            (tp - max_favorable_price) / entry * 100
        )
    else:
        max_favorable_price = max(
            float(df["High"].iloc[tp_hit_pos:stop].max()),
            tp
        )
        tp_extension_pct = max(
            0.0,
            (max_favorable_price - tp) / entry * 100
        )

    return {
        "result": "TP",
        "hit_pos": hit_pos,
        "hit_time": hit_time,
        "mfe_pct": mfe,
        "mae_pct": mae,
        "bars_to_result": (
            hit_pos - start + 1
            if hit_pos is not None
            else None
        ),
        "tp_extension_pct": tp_extension_pct,
        "reversed_after_tp": reversed_after_tp,
        "max_after_tp_pct": max_after_tp,
        "return_after_tp_to_entry": returned_to_entry
    }


def backtest_signal(signal, df, max_holding=0):
    """
    اختبار نفس signal مرتين:
    - Shoulder SL
    - Head SL
    """
    base = {
        "signal_key": str(signal["key"]),
        "pattern": signal["pattern"],
        "direction": signal["direction"],
        "entry": signal["entry"],
        "tp": signal["tp"],
        "shoulder_sl": signal["shoulder_sl"],
        "head_sl": signal["head_sl"],
        "breakout_time": signal["breakout_time"],
        "breakout_price": signal["breakout_price"]
    }

    shoulder = first_touch_result(
        df=df,
        start_pos=signal["breakout_pos"],
        entry=signal["entry"],
        tp=signal["tp"],
        sl=signal["shoulder_sl"],
        direction=signal["direction"],
        max_holding=max_holding
    )

    head = first_touch_result(
        df=df,
        start_pos=signal["breakout_pos"],
        entry=signal["entry"],
        tp=signal["tp"],
        sl=signal["head_sl"],
        direction=signal["direction"],
        max_holding=max_holding
    )

    row = dict(base)

    # Shoulder
    row["shoulder_result"] = shoulder["result"]
    row["shoulder_hit_time"] = shoulder["hit_time"]
    row["shoulder_mfe_pct"] = shoulder["mfe_pct"]
    row["shoulder_mae_pct"] = shoulder["mae_pct"]
    row["shoulder_bars"] = shoulder["bars_to_result"]
    row["shoulder_tp_extension_pct"] = shoulder["tp_extension_pct"]
    row["shoulder_reversed_after_tp"] = shoulder["reversed_after_tp"]

    # Head
    row["head_result"] = head["result"]
    row["head_hit_time"] = head["hit_time"]
    row["head_mfe_pct"] = head["mfe_pct"]
    row["head_mae_pct"] = head["mae_pct"]
    row["head_bars"] = head["bars_to_result"]
    row["head_tp_extension_pct"] = head["tp_extension_pct"]
    row["head_reversed_after_tp"] = head["reversed_after_tp"]

    return row


def run_engine_backtest(df):
    """
    تشغيل engine.py تاريخياً:
    كل مرة يرى engine فقط البيانات حتى تلك الشمعة.
    """
    detections = []
    seen = set()

    if len(df) < 60:
        return detections

    for end in range(60, len(df) + 1):

        history = df.iloc[:end].copy()

        try:
            result = engine.run_full_analysis(
                history
            )
        except Exception:
            continue

        signal = extract_signal(
            result,
            history
        )

        if signal is None:
            continue

        key = signal["key"]

        if key in seen:
            continue

        seen.add(key)
        detections.append(signal)

    return detections


def summarize(results):
    """تلخيص نتائج SL لكل استراتيجية."""
    if not results:
        return {
            "trades": 0,
            "tp": 0,
            "sl": 0,
            "open": 0,
            "win_rate": 0.0,
            "avg_mfe": 0.0,
            "avg_mae": 0.0,
            "tp_extension_count": 0,
            "reversed_count": 0
        }

    s = pd.Series(
        [x for x in results]
    )

    trades = len(s)

    tp = int(
        (s == "TP").sum()
    )

    sl = int(
        (s == "SL").sum()
    )

    open_count = int(
        (s == "OPEN").sum()
    )

    decided = tp + sl

    win_rate = (
        tp / decided * 100
        if decided
        else 0.0
    )

    return {
        "trades": trades,
        "tp": tp,
        "sl": sl,
        "open": open_count,
        "win_rate": win_rate
    }


def build_summary_table(all_rows):
    rows = []

    for timeframe, data in all_rows.items():

        results = data["results"]

        shoulder_results = [
            x["shoulder_result"]
            for x in results
        ]

        head_results = [
            x["head_result"]
            for x in results
        ]

        ss = summarize(
            shoulder_results
        )

        hs = summarize(
            head_results
        )

        avg_mfe_shoulder = (
            np.mean([
                x["shoulder_mfe_pct"]
                for x in results
            ])
            if results else 0
        )

        avg_mfe_head = (
            np.mean([
                x["head_mfe_pct"]
                for x in results
            ])
            if results else 0
        )

        tp_shoulder = int(
            sum(
                x["shoulder_result"] == "TP"
                for x in results
            )
        )

        tp_head = int(
            sum(
                x["head_result"] == "TP"
                for x in results
            )
        )

        reversed_shoulder = int(
            sum(
                x["shoulder_reversed_after_tp"]
                for x in results
            )
        )

        reversed_head = int(
            sum(
                x["head_reversed_after_tp"]
                for x in results
            )
        )

        rows.append({
            "Timeframe": timeframe,
            "Signals": len(results),

            "Shoulder TP": ss["tp"],
            "Shoulder SL": ss["sl"],
            "Shoulder OPEN": ss["open"],
            "Shoulder Win %": round(
                ss["win_rate"],
                2
            ),
            "Shoulder Avg MFE %": round(
                avg_mfe_shoulder,
                2
            ),
            "Shoulder TP→Reversal": reversed_shoulder,

            "Head TP": hs["tp"],
            "Head SL": hs["sl"],
            "Head OPEN": hs["open"],
            "Head Win %": round(
                hs["win_rate"],
                2
            ),
            "Head Avg MFE %": round(
                avg_mfe_head,
                2
            ),
            "Head TP→Reversal": reversed_head
        })

    return pd.DataFrame(rows)


def calculate_best_timeframe(summary_df):
    """
    الأفضلية تعتمد أساساً على:
    1) Win Rate
    2) TP count
    3) Avg MFE
    مع عدم اعتبار OPEN خسارة.
    """
    if summary_df.empty:
        return None

    temp = summary_df.copy()

    temp["Best Win %"] = temp[
        ["Shoulder Win %", "Head Win %"]
    ].max(axis=1)

    temp["Best TP"] = temp[
        ["Shoulder TP", "Head TP"]
    ].max(axis=1)

    temp["Best MFE"] = temp[
        ["Shoulder Avg MFE %", "Head Avg MFE %"]
    ].max(axis=1)

    temp = temp.sort_values(
        by=[
            "Best Win %",
            "Best TP",
            "Best MFE"
        ],
        ascending=False
    )

    return temp.iloc[0]


# ==========================================================
# التشغيل
# ==========================================================

if run:

    if not symbol:
        st.error("أدخل Symbol أولاً.")
        st.stop()

    if not timeframes:
        st.error(
            "اختر Timeframe واحداً على الأقل."
        )
        st.stop()

    all_rows = {}
    errors = []

    progress = st.progress(
        0,
        text="بدء الاختبار..."
    )

    total_tf = len(timeframes)

    for tf_index, timeframe in enumerate(timeframes):

        progress.progress(
            tf_index / total_tf,
            text=f"اختبار {timeframe}..."
        )

        df, error = download_timeframe(
            symbol,
            period,
            timeframe
        )

        if error:
            errors.append({
                "Timeframe": timeframe,
                "Error": error
            })

        if df.empty:
            continue

        if len(df) < 60:
            errors.append({
                "Timeframe": timeframe,
                "Error": (
                    f"البيانات غير كافية "
                    f"({len(df)} شمعة)."
                )
            })
            continue

        detections = run_engine_backtest(
            df
        )

        results = []

        for signal in detections:

            try:
                result = backtest_signal(
                    signal,
                    df,
                    MAX_HOLDING_CANDLES
                )

                results.append(result)

            except Exception:
                continue

        all_rows[timeframe] = {
            "df": df,
            "signals": detections,
            "results": results
        }

    progress.progress(
        1.0,
        text="اكتمل الاختبار ✅"
    )

    st.session_state["all_rows"] = all_rows
    st.session_state["errors"] = errors
    st.session_state["symbol"] = symbol
    st.session_state["period"] = period


# ==========================================================
# عرض النتائج
# ==========================================================

if "all_rows" in st.session_state:

    all_rows = st.session_state["all_rows"]
    errors = st.session_state.get(
        "errors",
        []
    )

    if not all_rows:
        st.error(
            "لم تتوفر بيانات صالحة للاختبار."
        )
        st.stop()

    st.header("📊 النتائج الإجمالية")

    summary_df = build_summary_table(
        all_rows
    )

    # ------------------------------------------------------
    # أفضل Timeframe
    # ------------------------------------------------------

    best = calculate_best_timeframe(
        summary_df
    )

    if best is not None:

        best_tf = best["Timeframe"]
        best_win = best["Best Win %"]

        st.success(
            f"🏆 أفضل Timeframe حالياً: "
            f"**{best_tf}** — أفضل Win Rate = "
            f"**{best_win:.2f}%**"
        )

    # ------------------------------------------------------
    # بطاقات عامة
    # ------------------------------------------------------

    total_signals = int(
        sum(
            len(x["results"])
            for x in all_rows.values()
        )
    )

    total_tp_shoulder = int(
        sum(
            sum(
                r["shoulder_result"] == "TP"
                for r in x["results"]
            )
            for x in all_rows.values()
        )
    )

    total_tp_head = int(
        sum(
            sum(
                r["head_result"] == "TP"
                for r in x["results"]
            )
            for x in all_rows.values()
        )
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "🔎 إجمالي الإشارات",
        total_signals
    )

    c2.metric(
        "🎯 TP — Shoulder SL",
        total_tp_shoulder
    )

    c3.metric(
        "🎯 TP — Head SL",
        total_tp_head
    )

    c4.metric(
        "⏱️ Timeframes",
        len(all_rows)
    )

    # ------------------------------------------------------
    # جدول مقارنة Timeframes
    # ------------------------------------------------------

    st.subheader(
        "🏆 مقارنة جميع Timeframes"
    )

    display_summary = summary_df.copy()

    st.dataframe(
        display_summary,
        use_container_width=True,
        hide_index=True
    )

    # ------------------------------------------------------
    # مقارنة SL بشكل مباشر
    # ------------------------------------------------------

    st.subheader(
        "🛑 مقارنة SL: الكتف الأيمن مقابل الرأس"
    )

    comparison_rows = []

    for _, row in summary_df.iterrows():

        shoulder_win = row["Shoulder Win %"]
        head_win = row["Head Win %"]

        if shoulder_win > head_win:
            best_sl = "Shoulder SL 🏆"
        elif head_win > shoulder_win:
            best_sl = "Head SL 🏆"
        else:
            best_sl = "تعادل"

        comparison_rows.append({
            "Timeframe": row["Timeframe"],
            "Shoulder Win %": shoulder_win,
            "Head Win %": head_win,
            "الفرق %": round(
                head_win - shoulder_win,
                2
            ),
            "الأفضل": best_sl
        })

    st.dataframe(
        pd.DataFrame(comparison_rows),
        use_container_width=True,
        hide_index=True
    )

    # ------------------------------------------------------
    # TP / Reversal
    # ------------------------------------------------------

    st.subheader(
        "🎯 تحليل TP والتجاوز والرجوع"
    )

    tp_rows = []

    for timeframe, data in all_rows.items():

        results = data["results"]

        if not results:
            continue

        shoulder_tp = sum(
            r["shoulder_result"] == "TP"
            for r in results
        )

        head_tp = sum(
            r["head_result"] == "TP"
            for r in results
        )

        shoulder_reversal = sum(
            r["shoulder_reversed_after_tp"]
            for r in results
        )

        head_reversal = sum(
            r["head_reversed_after_tp"]
            for r in results
        )

        shoulder_extension = np.mean([
            r["shoulder_tp_extension_pct"]
            for r in results
            if r["shoulder_result"] == "TP"
        ]) if shoulder_tp else 0

        head_extension = np.mean([
            r["head_tp_extension_pct"]
            for r in results
            if r["head_result"] == "TP"
        ]) if head_tp else 0

        tp_rows.append({
            "Timeframe": timeframe,
            "Shoulder TP Hit": shoulder_tp,
            "Shoulder TP→Reversal": shoulder_reversal,
            "Shoulder Avg TP Extension %": round(
                shoulder_extension,
                2
            ),
            "Head TP Hit": head_tp,
            "Head TP→Reversal": head_reversal,
            "Head Avg TP Extension %": round(
                head_extension,
                2
            )
        })

    st.dataframe(
        pd.DataFrame(tp_rows),
        use_container_width=True,
        hide_index=True
    )

    # ------------------------------------------------------
    # تفاصيل كل Timeframe
    # ------------------------------------------------------

    st.subheader(
        "📋 تفاصيل الإشارات"
    )

    selected_tf = st.selectbox(
        "اختر Timeframe لعرض كل الصفقات",
        list(all_rows.keys())
    )

    selected_data = all_rows[
        selected_tf
    ]

    detail_rows = selected_data[
        "results"
    ]

    if detail_rows:

        detail_table = []

        for i, r in enumerate(
            detail_rows,
            start=1
        ):

            detail_table.append({
                "#": i,
                "النمط": r["pattern"],
                "الاتجاه": r["direction"],
                "وقت Entry": r["breakout_time"],
                "Entry": round(
                    r["entry"],
                    6
                ),
                "TP": round(
                    r["tp"],
                    6
                ),
                "Shoulder SL": round(
                    r["shoulder_sl"],
                    6
                ),
                "Head SL": round(
                    r["head_sl"],
                    6
                ),
                "نتيجة Shoulder": r[
                    "shoulder_result"
                ],
                "نتيجة Head": r[
                    "head_result"
                ],
                "MFE Shoulder %": round(
                    r["shoulder_mfe_pct"],
                    2
                ),
                "MFE Head %": round(
                    r["head_mfe_pct"],
                    2
                ),
                "TP Extension Shoulder %": round(
                    r["shoulder_tp_extension_pct"],
                    2
                ),
                "TP Extension Head %": round(
                    r["head_tp_extension_pct"],
                    2
                ),
                "رجوع بعد TP Shoulder": (
                    "نعم"
                    if r[
                        "shoulder_reversed_after_tp"
                    ]
                    else "لا"
                ),
                "رجوع بعد TP Head": (
                    "نعم"
                    if r[
                        "head_reversed_after_tp"
                    ]
                    else "لا"
                )
            })

        st.dataframe(
            pd.DataFrame(detail_table),
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info(
            "لم توجد إشارات مكتملة لهذا Timeframe."
        )

    # ------------------------------------------------------
    # عرض الشارت لإشارة محددة
    # ------------------------------------------------------

    st.subheader(
        "📈 عرض إشارة على الشارت"
    )

    signals = selected_data[
        "signals"
    ]

    if signals:

        signal_index = st.selectbox(
            "اختر الإشارة",
            range(len(signals)),
            format_func=lambda i:
                f"{i + 1} — "
                f"{signals[i]['breakout_time']} — "
                f"{signals[i]['pattern']}"
        )

        sig = signals[
            signal_index
        ]

        df = selected_data[
            "df"
        ]

        start = max(
            0,
            sig["breakout_pos"] - 50
        )

        end = min(
            len(df),
            sig["breakout_pos"] + 40
        )

        chart_df = df.iloc[
            start:end
        ]

        fig = go.Figure()

        fig.add_trace(
            go.Candlestick(
                x=chart_df.index,
                open=chart_df["Open"],
                high=chart_df["High"],
                low=chart_df["Low"],
                close=chart_df["Close"],
                name="Price"
            )
        )

        nodes = sig.get(
            "nodes",
            []
        )

        if nodes:

            x = []
            y = []

            for node in nodes:

                try:
                    x.append(
                        node[0]
                    )
                    y.append(
                        float(node[1])
                    )
                except Exception:
                    pass

            if x:

                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines+markers",
                        name=sig[
                            "pattern"
                        ],
                        line=dict(
                            width=3
                        ),
                        marker=dict(
                            size=8
                        )
                    )
                )

        # Entry
        fig.add_hline(
            y=sig["entry"],
            line_dash="dash",
            annotation_text="ENTRY"
        )

        # TP
        fig.add_hline(
            y=sig["tp"],
            line_dash="dot",
            annotation_text="TP"
        )

        # Shoulder SL
        fig.add_hline(
            y=sig["shoulder_sl"],
            line_dash="dash",
            annotation_text="Shoulder SL"
        )

        # Head SL
        fig.add_hline(
            y=sig["head_sl"],
            line_dash="dash",
            annotation_text="Head SL"
        )

        fig.update_layout(
            template="plotly_white",
            height=650,
            xaxis_rangeslider_visible=False,
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            )
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # ------------------------------------------------------
    # معلومات قيود Yahoo
    # ------------------------------------------------------

    if errors:

        st.warning(
            "⚠️ بعض Timeframes لم تتوفر لها "
            "البيانات المطلوبة من Yahoo Finance."
        )

        st.dataframe(
            pd.DataFrame(errors),
            use_container_width=True,
            hide_index=True
        )

    # ------------------------------------------------------
    # شرح منهجية الاختبار
    # ------------------------------------------------------

    with st.expander(
        "ℹ️ منهجية الاختبار"
    ):

        st.markdown(
            """
**كيف يعمل الاختبار؟**

- يتم تشغيل `engine.py` على البيانات التاريخية شمعةً بعد شمعة.
- لا يتم إعطاء الـengine الشموع المستقبلية أثناء اكتشاف الإشارة.
- يتم عدّ النمط مرة واحدة فقط حتى لا يتكرر نفس Head & Shoulders.
- يتم استخدام Entry الذي أعاده `engine.py`.
- في H&S العادي:
  - Head SL = قمة الرأس.
  - Shoulder SL = قمة الكتف الأيمن.
- في Inverse H&S:
  - Head SL = قاع الرأس.
  - Shoulder SL = قاع الكتف الأيمن.
- TP هو الهدف الذي أعاده `engine.py`.
- إذا لامست شمعة واحدة TP وSL معاً، يتم احتساب SL أولاً كقاعدة محافظة.
- إذا وصل السعر إلى TP ثم عاد إلى Entry، يتم تسجيل ذلك كـ **TP ثم Reversal** وليس كخسارة.
- **MFE** يقيس أقصى حركة لصالح الصفقة بعد Entry.
- `OPEN` تعني أن السعر لم يصل إلى TP أو SL قبل نهاية البيانات/مدة الاختبار.
- أفضل Timeframe يتم اختياره بناءً على أفضل Win Rate، ثم عدد TP، ثم متوسط MFE.
"""
        )

else:

    st.info(
        "اختر Symbol والفترة وTimeframes، "
        "ثم اضغط 🚀 تشغيل الاختبار الكامل."
    )
