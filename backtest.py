import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import importlib
import engine

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    get_symbols_from_sheet = None


# ==========================================================
# BACKTEST.PY
# HISTORICAL H&S BACKTESTER
# لا يغير شروط التعرف الموجودة في engine.py
# ==========================================================

st.set_page_config(
    page_title="H&S Ultimate Backtester Pro",
    page_icon="📊",
    layout="wide"
)


# ==========================================================
# STYLE
# ==========================================================

st.markdown(
    """
    <style>

    .stApp {
        background-color: #0e1117;
    }

    div.stExpander {
        background-color: #161b22;
        border-radius: 16px;
        border: 1px solid #30363d;
        padding: 10px;
    }

    .stButton > button {
        border-radius: 12px;
        background-color: #2563eb;
        color: white;
        font-weight: bold;
        border: none;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ==========================================================
# RELOAD ENGINE
# ==========================================================

engine = importlib.reload(engine)


# ==========================================================
# LANGUAGE
# ==========================================================

lang = st.sidebar.radio(
    "🌐 Language / اللغة",
    ["العربية", "English"],
    index=0
)


if lang == "العربية":

    st.title(
        "📊 الاختبار الرجعي الاحترافي للرأس والكتفين"
    )

    st.caption(
        "اختبار تاريخي زمني باستخدام محرك engine.py دون تغيير شروط التعرف على النمط."
    )

    txt_scan_mode = (
        "طريقة اختيار الأصول:"
    )

    txt_single = (
        "بحث فردي"
    )

    txt_sheet = (
        "قائمة Google Sheet"
    )

    txt_tf_label = (
        "الفواصل الزمنية:"
    )

    txt_period_label = (
        "الفترة التاريخية:"
    )

    txt_sl_strat = (
        "استراتيجية وقف الخسارة:"
    )

    txt_run = (
        "🚀 تشغيل الاختبار الرجعي"
    )

else:

    st.title(
        "📊 Professional Head & Shoulders Backtester"
    )

    st.caption(
        "Historical chronological backtest using engine.py without changing pattern rules."
    )

    txt_scan_mode = (
        "Asset Selection Method:"
    )

    txt_single = (
        "Single Asset"
    )

    txt_sheet = (
        "Google Sheet List"
    )

    txt_tf_label = (
        "Timeframes:"
    )

    txt_period_label = (
        "Historical Period:"
    )

    txt_sl_strat = (
        "Stop Loss Strategy:"
    )

    txt_run = (
        "🚀 Run Backtest"
    )


# ==========================================================
# SETTINGS
# ==========================================================

SHEET_ID = (
    "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
)

DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"


st.sidebar.header(
    "⚙️ الإعدادات / Settings"
)


scan_mode = st.sidebar.radio(
    txt_scan_mode,
    [
        txt_single,
        txt_sheet
    ],
    index=0
)


symbols_to_test = []


# ==========================================================
# SYMBOL SELECTION
# ==========================================================

if scan_mode == txt_single:

    symbol_input = st.sidebar.text_input(
        "Symbol",
        "BTC-USD"
    ).strip()

    if symbol_input:

        symbols_to_test = [
            symbol_input
        ]

else:

    if get_symbols_from_sheet is None:

        st.sidebar.error(
            "⚠️ ملف ffff.py غير موجود."
        )

    else:

        fetched_symbols, err = (
            get_symbols_from_sheet(
                SHEET_ID,
                DEFAULT_SHEET_NAME,
                DEFAULT_COL_NAME
            )
        )

        if err:

            st.sidebar.error(err)

        else:

            symbols_to_test = (
                fetched_symbols
            )

            if lang == "العربية":

                st.sidebar.success(
                    f"تم تحميل {len(symbols_to_test)} أصل."
                )

            else:

                st.sidebar.success(
                    f"Loaded {len(symbols_to_test)} assets."
                )


# ==========================================================
# TIMEFRAMES
# ==========================================================

selected_tfs = st.sidebar.multiselect(
    txt_tf_label,

    [
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "1d"
    ],

    default=[
        "1h",
        "4h",
        "1d"
    ]
)


# ==========================================================
# PERIOD
# ==========================================================

selected_period = st.sidebar.selectbox(
    txt_period_label,

    [
        "1mo",
        "3mo",
        "6mo",
        "1y",
        "2y",
        "5y",
        "max"
    ],

    index=2
)


# ==========================================================
# SL
# ==========================================================

sl_options_ar = [
    "الكل",
    "وقف الرأس فقط",
    "وقف الكتف فقط"
]

sl_options_en = [
    "All",
    "Head SL Only",
    "Shoulder SL Only"
]


sl_strategy = st.sidebar.radio(
    txt_sl_strat,

    (
        sl_options_ar
        if lang == "العربية"
        else sl_options_en
    )
)


run = st.sidebar.button(
    txt_run,
    use_container_width=True
)


# ==========================================================
# HELPERS
# ==========================================================

def clean_yfinance_data(df):

    if df is None or df.empty:

        return pd.DataFrame()

    df = df.copy()

    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = (
            df.columns
            .get_level_values(0)
        )

    required = [
        "Open",
        "High",
        "Low",
        "Close"
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:

        return pd.DataFrame()

    for col in required:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    )

    df = df[
        ~df.index.duplicated(
            keep="last"
        )
    ]

    df = df.sort_index()

    return df


def get_shoulder_sl(pattern):

    """
    مهم:
    لا نغير شروط التعرف.

    فقط نحدد وقف الكتف من الكتفين الحقيقيين.

    H&S:
        nodes:
        L0,H1,L1,H2,L2,H3,breakout

        الكتفان = H1 و H3
        أي nodes[1] و nodes[5]

    Inverse H&S:
        H0,L1,H1,L2,H2,L3,breakout

        الكتفان = L1 و L3
        أي nodes[1] و nodes[5]
    """

    nodes = pattern.get(
        "nodes",
        []
    )

    bias = pattern.get(
        "bias"
    )

    if len(nodes) < 6:

        return pattern.get(
            "sl"
        )

    if bias == "Bearish":

        return max(
            float(nodes[1][1]),
            float(nodes[5][1])
        )

    if bias == "Bullish":

        return min(
            float(nodes[1][1]),
            float(nodes[5][1])
        )

    return pattern.get(
        "sl"
    )


def calculate_trade_result(
    df,
    start_pos,
    bias,
    sl,
    tp
):

    """
    يحاكي الصفقة بعد تأكيد الاختراق.

    لا يستخدم أي شمعة قبل الدخول لمعرفة النتيجة.
    """

    future = df.iloc[
        start_pos + 1:
    ]

    for pos, (
        idx,
        row
    ) in enumerate(
        future.iterrows(),
        start=start_pos + 1
    ):

        high = float(
            row["High"]
        )

        low = float(
            row["Low"]
        )

        if bias == "Bearish":

            hit_sl = (
                high >= sl
            )

            hit_tp = (
                low <= tp
            )

        else:

            hit_sl = (
                low <= sl
            )

            hit_tp = (
                high >= tp
            )

        # ----------------------------------------------
        # إذا ضرب SL و TP في نفس الشمعة
        # ----------------------------------------------

        if hit_sl and hit_tp:

            return {
                "Outcome": "LOSS",
                "Exit_Date": str(idx),
                "Exit_Price": sl,
                "Bars_Held":
                    pos - start_pos,
                "Ambiguous_Bar": True
            }

        if hit_sl:

            return {
                "Outcome": "LOSS",
                "Exit_Date": str(idx),
                "Exit_Price": sl,
                "Bars_Held":
                    pos - start_pos,
                "Ambiguous_Bar": False
            }

        if hit_tp:

            return {
                "Outcome": "WIN",
                "Exit_Date": str(idx),
                "Exit_Price": tp,
                "Bars_Held":
                    pos - start_pos,
                "Ambiguous_Bar": False
            }

    return {
        "Outcome": "OPEN",
        "Exit_Date": str(
            df.index[-1]
        ),
        "Exit_Price": float(
            df["Close"].iloc[-1]
        ),
        "Bars_Held":
            len(df) - 1 - start_pos,
        "Ambiguous_Bar": False
    }


def pattern_key(pattern):

    return (
        str(
            pattern.get(
                "pattern"
            )
        ),
        str(
            pattern.get(
                "neckline_end_idx"
            )
        )
    )


def allowed_sl_types():

    if lang == "العربية":

        if sl_strategy == "الكل":
            return [
                "Head SL",
                "Shoulder SL"
            ]

        if (
            sl_strategy
            ==
            "وقف الرأس فقط"
        ):

            return [
                "Head SL"
            ]

        return [
            "Shoulder SL"
        ]

    else:

        if sl_strategy == "All":
            return [
                "Head SL",
                "Shoulder SL"
            ]

        if (
            sl_strategy
            ==
            "Head SL Only"
        ):

            return [
                "Head SL"
            ]

        return [
            "Shoulder SL"
        ]


# ==========================================================
# MAIN BACKTEST
# ==========================================================

if run:

    if not symbols_to_test:

        st.error(
            "⚠️ لا توجد أصول للاختبار."
            if lang == "العربية"
            else
            "⚠️ No assets available."
        )

    elif not selected_tfs:

        st.error(
            "⚠️ اختر فاصلًا زمنيًا واحدًا على الأقل."
            if lang == "العربية"
            else
            "⚠️ Select at least one timeframe."
        )

    else:

        st.info(
            "🚀 بدأ الاختبار الرجعي..."
            if lang == "العربية"
            else
            "🚀 Historical backtest started..."
        )

        progress = st.progress(
            0
        )

        status_box = st.empty()

        all_summary = []
        all_details = []

        total_jobs = (
            len(symbols_to_test)
            *
            len(selected_tfs)
        )

        completed_jobs = 0


        # ==================================================
        # SYMBOL LOOP
        # ==================================================

        for symbol in symbols_to_test:

            symbol_details = []

            symbol_summary = []

            # ----------------------------------------------
            # TIMEFRAME LOOP
            # ----------------------------------------------

            for tf in selected_tfs:

                completed_jobs += 1

                status_box.info(
                    (
                        f"جاري اختبار {symbol} | {tf}"
                        if lang == "العربية"
                        else
                        f"Testing {symbol} | {tf}"
                    )
                )

                progress.progress(
                    min(
                        completed_jobs
                        /
                        max(
                            total_jobs,
                            1
                        ),
                        1.0
                    )
                )


                # ==========================================
                # DOWNLOAD
                # ==========================================

                try:

                    df_raw = yf.download(
                        symbol,
                        period=selected_period,
                        interval=tf,
                        progress=False,
                        auto_adjust=False,
                        threads=False
                    )

                except Exception as e:

                    st.warning(
                        f"{symbol} - {tf}: {e}"
                    )

                    continue


                df = clean_yfinance_data(
                    df_raw
                )


                if df.empty:

                    continue


                if len(df) < 80:

                    continue


                # ==========================================
                # INDICATORS ONCE
                # ==========================================

                df_ind = (
                    engine.calculate_indicators(
                        df
                    )
                )

                # ==========================================
                # ZIGZAG ONCE
                # ==========================================

                df_ind = (
                    engine.calculate_zigzag(
                        df_ind
                    )
                )

                # ==========================================
                # PIVOTS ONCE
                # ==========================================

                pivots = (
                    engine.get_chronological_pivots(
                        df_ind
                    )
                )


                if len(pivots) < 6:

                    continue


                # ==========================================
                # IMPORTANT
                #
                # We process pattern candidates according
                # to their historical confirmation point.
                #
                # engine recognition rules are untouched.
                # ==========================================

                patterns = (
                    engine.detect_all_head_shoulders(
                        pivots,
                        df_ind
                    )
                )


                if not patterns:

                    continue


                # ==========================================
                # SORT BY CONFIRMATION
                # ==========================================

                patterns = sorted(
                    patterns,
                    key=lambda p:
                        df_ind.index.get_loc(
                            p[
                                "neckline_end_idx"
                            ]
                        )
                        if
                        p.get(
                            "neckline_end_idx"
                        )
                        in df_ind.index
                        else 10**9
                )


                used_trades = set()


                # ==========================================
                # PATTERN LOOP
                # ==========================================

                for pattern in patterns:

                    end_idx = pattern.get(
                        "neckline_end_idx"
                    )

                    if (
                        end_idx
                        not in
                        df_ind.index
                    ):

                        continue


                    key = pattern_key(
                        pattern
                    )


                    # ======================================
                    # ENTRY POSITION
                    # ======================================

                    try:

                        entry_pos = (
                            df_ind.index.get_loc(
                                end_idx
                            )
                        )

                    except Exception:

                        continue


                    entry = pattern.get(
                        "entry"
                    )

                    tp = pattern.get(
                        "tp"
                    )

                    bias = pattern.get(
                        "bias"
                    )


                    if (
                        entry is None
                        or
                        tp is None
                        or
                        bias not in
                        [
                            "Bearish",
                            "Bullish"
                        ]
                    ):

                        continue


                    # ======================================
                    # TWO SL METHODS
                    # ======================================

                    for sl_type in (
                        allowed_sl_types()
                    ):

                        trade_key = (
                            key,
                            sl_type
                        )

                        if (
                            trade_key
                            in
                            used_trades
                        ):

                            continue


                        used_trades.add(
                            trade_key
                        )


                        # ==================================
                        # SELECT SL
                        # ==================================

                        if (
                            sl_type
                            ==
                            "Head SL"
                        ):

                            sl = float(
                                pattern[
                                    "sl"
                                ]
                            )

                        else:

                            sl = float(
                                get_shoulder_sl(
                                    pattern
                                )
                            )


                        entry = float(
                            entry
                        )

                        tp = float(
                            tp
                        )


                        # ==================================
                        # SANITY
                        # ==================================

                        if bias == "Bearish":

                            if not (
                                sl > entry
                                and
                                tp < entry
                            ):

                                continue

                        else:

                            if not (
                                sl < entry
                                and
                                tp > entry
                            ):

                                continue


                        # ==================================
                        # SIMULATE TRADE
                        # ==================================

                        result = (
                            calculate_trade_result(
                                df_ind,
                                entry_pos,
                                bias,
                                sl,
                                tp
                            )
                        )


                        # =============
