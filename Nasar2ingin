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
# H&S ULTIMATE BACKTESTER PRO
# ==========================================================

st.set_page_config(
    page_title="H&S Ultimate Backtester Pro",
    page_icon="📊",
    layout="wide"
)


# ==========================================================
# UI STYLE
# ==========================================================

st.markdown("""
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

.progress-label {
    font-size: 16px;
    font-weight: bold;
    margin-bottom: 5px;
}

</style>
""", unsafe_allow_html=True)


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
        "📊 نظام الاختبار الرجعي الاحترافي للرأس والكتفين"
    )

    st.caption(
        "اختبار تاريخي سريع باستخدام engine.py مع الحفاظ على شروط التعرف على الأنماط."
    )

    txt_scan_mode = "طريقة اختيار الأصول:"
    txt_single = "بحث فردي"
    txt_sheet = "قائمة Google Sheet"

    txt_tf_label = "الفواصل الزمنية:"
    txt_period_label = "الفترة التاريخية:"

    txt_sl_strat = "استراتيجية وقف الخسارة:"

    txt_run = "🚀 تشغيل الاختبار الرجعي"

else:

    st.title(
        "📊 Professional Head & Shoulders Backtester"
    )

    st.caption(
        "Fast historical testing using engine.py without changing pattern recognition rules."
    )

    txt_scan_mode = "Asset Selection Method:"
    txt_single = "Single Asset"
    txt_sheet = "Google Sheet List"

    txt_tf_label = "Timeframes:"
    txt_period_label = "Historical Period:"

    txt_sl_strat = "Stop Loss Strategy:"

    txt_run = "🚀 Run Backtest"


# ==========================================================
# GOOGLE SHEET
# ==========================================================

SHEET_ID = (
    "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
)

DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"


# ==========================================================
# SIDEBAR
# ==========================================================

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
# SYMBOLS
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

            st.sidebar.success(
                (
                    f"تم تحميل {len(symbols_to_test)} أصل بنجاح!"
                    if lang == "العربية"
                    else
                    f"Loaded {len(symbols_to_test)} assets!"
                )
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
# STOP LOSS
# ==========================================================

if lang == "العربية":

    sl_options = [
        "الكل",
        "وقف الرأس فقط",
        "وقف الكتف فقط"
    ]

else:

    sl_options = [
        "All",
        "Head SL Only",
        "Shoulder SL Only"
    ]


sl_strategy = st.sidebar.radio(
    txt_sl_strat,
    sl_options
)


run = st.sidebar.button(
    txt_run,
    use_container_width=True
)


# ==========================================================
# DATA CLEANER
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

    for col in required:

        if col not in df.columns:
            return pd.DataFrame()

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


# ==========================================================
# SHOULDER STOP LOSS
# ==========================================================

def get_shoulder_sl(pattern):

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

    # Head & Shoulders
    #
    # L0 - H1 - L1 - H2 - L2 - H3
    #
    # الكتف الأيسر = H1
    # الرأس = H2
    # الكتف الأيمن = H3

    if bias == "Bearish":

        return max(
            float(nodes[1][1]),
            float(nodes[5][1])
        )

    # Inverse Head & Shoulders
    #
    # H0 - L1 - H1 - L2 - H2 - L3
    #
    # الكتف الأيسر = L1
    # الرأس = L2
    # الكتف الأيمن = L3

    if bias == "Bullish":

        return min(
            float(nodes[1][1]),
            float(nodes[5][1])
        )

    return pattern.get(
        "sl"
    )


# ==========================================================
# TRADE RESULT
# ==========================================================

def calculate_trade_result(
    df,
    entry_pos,
    bias,
    sl,
    tp
):

    future_df = df.iloc[
        entry_pos + 1:
    ]

    for future_pos, (
        idx,
        row
    ) in enumerate(
        future_df.iterrows(),
        start=entry_pos + 1
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

        # إذا ضرب الوقف والهدف
        # في نفس الشمعة نعتبرها خسارة
        # لأن ترتيب الحركة داخل الشمعة غير معروف.

        if hit_sl and hit_tp:

            return {
                "Outcome": "LOSS",
                "Exit_Date": str(idx),
                "Exit_Price": sl,
                "Bars_Held":
                    future_pos - entry_pos,
                "Ambiguous_Bar": True
            }

        if hit_sl:

            return {
                "Outcome": "LOSS",
                "Exit_Date": str(idx),
                "Exit_Price": sl,
                "Bars_Held":
                    future_pos - entry_pos,
                "Ambiguous_Bar": False
            }

        if hit_tp:

            return {
                "Outcome": "WIN",
                "Exit_Date": str(idx),
                "Exit_Price": tp,
                "Bars_Held":
                    future_pos - entry_pos,
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
            len(df) - 1 - entry_pos,
        "Ambiguous_Bar": False
    }


# ==========================================================
# SL SELECTION
# ==========================================================

def get_selected_sl_types():

    if lang == "العربية":

        if sl_strategy == "الكل":

            return [
                "Head SL",
                "Shoulder SL"
            ]

        if sl_strategy == "وقف الرأس فقط":

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

        if sl_strategy == "Head SL Only":

            return [
                "Head SL"
            ]

        return [
            "Shoulder SL"
        ]


# ==========================================================
# RUN
# ==========================================================

if run:

    if not symbols_to_test:

        st.error(
            "⚠️ لا توجد أصول للاختبار."
            if lang == "العربية"
            else
            "⚠️ No assets available."
        )

        st.stop()


    if not selected_tfs:

        st.error(
            "⚠️ اختر فاصلًا زمنيًا واحدًا على الأقل."
            if lang == "العربية"
            else
            "⚠️ Select at least one timeframe."
        )

        st.stop()


    # ======================================================
    # BLUE PROGRESS BAR
    # ======================================================

    st.markdown(
        '<div class="progress-label">'
        + (
            "🔵 تقدم الاختبار:"
            if lang == "العربية"
            else
            "🔵 Backtest Progress:"
        )
        + "</div>",
        unsafe_allow_html=True
    )


    progress_bar = st.progress(
        0
    )


    progress_text = st.empty()


    current_task = st.empty()


    # ======================================================
    # TOTAL JOBS
    # ======================================================

    total_jobs = (
        len(symbols_to_test)
        *
        len(selected_tfs)
    )

    completed_jobs = 0


    all_summary = []
    all_details = []


    # ======================================================
    # SYMBOL LOOP
    # ======================================================

    for symbol_index, symbol in enumerate(
        symbols_to_test,
        start=1
    ):

        symbol_details = []


        # ==================================================
        # TIMEFRAME LOOP
        # ==================================================

        for tf_index, tf in enumerate(
            selected_tfs,
            start=1
        ):

            current_task.info(
                (
                    f"🔄 جاري تحليل {symbol} | "
                    f"{tf} "
                    f"— أصل {symbol_index}/{len(symbols_to_test)}"
                    if lang == "العربية"
                    else
                    f"🔄 Analyzing {symbol} | "
                    f"{tf} "
                    f"— Asset {symbol_index}/{len(symbols_to_test)}"
                )
            )


            # ==================================================
            # DOWNLOAD
            # ==================================================

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

                completed_jobs += 1

                percentage = (
                    completed_jobs
                    /
                    total_jobs
                )

                progress_bar.progress(
                    min(
                        percentage,
                        1.0
                    )
                )

                continue


            df = clean_yfinance_data(
                df_raw
            )


            if df.empty or len(df) < 80:

                completed_jobs += 1

                percentage = (
                    completed_jobs
                    /
                    total_jobs
                )

                progress_bar.progress(
                    min(
                        percentage,
                        1.0
                    )
                )

                continue


            # ==================================================
            # ENGINE CALCULATIONS
            # ==================================================

            df_ind = (
                engine.calculate_indicators(
                    df
                )
            )


            df_ind = (
                engine.calculate_zigzag(
                    df_ind
                )
            )


            pivots = (
                engine.get_chronological_pivots(
                    df_ind
                )
            )


            if len(pivots) < 6:

                completed_jobs += 1

                percentage = (
                    completed_jobs
                    /
                    total_jobs
                )

                progress_bar.progress(
                    min(
                        percentage,
                        1.0
                    )
                )

                continue


            # ==================================================
            # PATTERN ENGINE
            # ==================================================

            patterns = (
                engine.detect_all_head_shoulders(
                    pivots,
                    df_ind
                )
            )


            if not patterns:

                completed_jobs += 1

                percentage = (
                    completed_jobs
                    /
                    total_jobs
                )

                progress_bar.progress(
                    min(
                        percentage,
                        1.0
                    )
                )

                continue


            # ==================================================
            # SORT PATTERNS
            # ==================================================

            valid_patterns = []


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


                try:

                    end_pos = (
                        df_ind.index.get_loc(
                            end_idx
                        )
                    )

                except Exception:

                    continue


                valid_patterns.append(
                    (
                        end_pos,
                        pattern
                    )
                )


            valid_patterns.sort(
                key=lambda x: x[0]
            )


            # ==================================================
            # TEST PATTERNS
            # ==================================================

            used_trades = set()


            for entry_pos, pattern in (
                valid_patterns
            ):

                end_idx = pattern.get(
                    "neckline_end_idx"
                )

                pattern_name = pattern.get(
                    "pattern"
                )

                bias = pattern.get(
                    "bias"
                )

                entry = pattern.get(
                    "entry"
                )

                tp = pattern.get(
                    "tp"
                )


                if (
                    entry is None
                    or
                    tp is None
                ):

                    continue


                if bias not in [
                    "Bearish",
                    "Bullish"
                ]:

                    continue


                pattern_id = (
                    pattern_name,
                    str(end_idx)
                )


                # ==============================================
                # HEAD SL / SHOULDER SL
                # ==============================================

                for sl_type in (
                    get_selected_sl_types()
                ):

                    trade_id = (
                        pattern_id,
                        sl_type
                    )


                    if trade_id in used_trades:

                        continue


                    used_trades.add(
                        trade_id
                    )


                    # ==========================================
                    # STOP
                    # ==========================================

                    if sl_type == "Head SL":

                        sl = float(
                            pattern["sl"]
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


                    # ==========================================
                    # VALID PRICE STRUCTURE
                    # ==========================================

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


                    # ==========================================
                    # SIMULATE
                    # ==========================================

                    result = (
                        calculate_trade_result(
                            df_ind,
                            entry_pos,
                            bias,
                            sl,
                            tp
                        )
                    )


                    # ==========================================
                    # RISK / REWARD
                    # ==========================================

                    risk = abs(
                        entry - sl
                    )

                    reward = abs(
                        tp - entry
                    )

                    rr = (
                        reward / risk
                        if risk > 0
                        else 0
                    )


                    # ==========================================
                    # RECORD
                    # ==========================================

                    trade = {

                        "Symbol":
                            symbol,

                        "Timeframe":
                            tf,

                        "Pattern":
                            pattern_name,

                        "Direction":
                            bias,

                        "SL Type":
                            sl_type,

                        "Signal Date":
                            str(end_idx),

                        "Exit Date":
                            result[
                                "Exit_Date"
                            ],

                        "Entry":
                            round(
                                entry,
                                6
                            ),

                        "SL":
                            round(
                                sl,
                                6
                            ),

                        "TP":
                            round(
                                tp,
                                6
                            ),

                        "Risk":
                            round(
                                risk,
                                6
                            ),

                        "Reward":
                            round(
                                reward,
                                6
                            ),

                        "RR":
                            round(
                                rr,
                                2
                            ),

                        "Outcome":
                            result[
                                "Outcome"
                            ],

                        "Exit Price":
                            round(
                                result[
                                    "Exit_Price"
                                ],
                                6
                            ),

                        "Bars Held":
                            result[
                                "Bars_Held"
                            ],

                        "Ambiguous Bar":
                            result[
                                "Ambiguous_Bar"
                            ]
                    }


                    symbol_details.append(
                        trade
                    )

                    all_details.append(
                        trade
                    )


            # ==================================================
            # UPDATE BLUE BAR
            # ==================================================

            completed_jobs += 1

            percentage = (
                completed_jobs
                /
                total_jobs
            )


            progress_bar.progress(
                min(
                    percentage,
                    1.0
                )
            )


            progress_text.markdown(
                (
                    f"**{percentage * 100:.1f}%** "
                    f"— {completed_jobs}/{total_jobs}"
                    if lang == "العربية"
                    else
                    f"**{percentage * 100:.1f}%** "
                    f"— {completed_jobs}/{total_jobs}"
                )
            )


            # ==================================================
            # SUMMARY FOR CURRENT TF
            # ==================================================

            tf_trades = [
                t
                for t in symbol_details
                if t["Timeframe"] == tf
            ]


            for sl_type in [
                "Head SL",
                "Shoulder SL"
            ]:

                selected_trades = [
                    t
                    for t in tf_trades
                    if t["SL Type"]
                    ==
                    sl_type
                ]


                if not selected_trades:

                    continue


                wins = sum(
                    t["Outcome"] == "WIN"
                    for t in selected_trades
                )

                losses = sum(
                    t["Outcome"] == "LOSS"
                    for t in selected_trades
                )

                opens = sum(
                    t["Outcome"] == "OPEN"
                    for t in selected_trades
                )


                closed = (
                    wins
                    +
                    losses
                )


                win_rate = (
                    wins
                    /
                    closed
                    *
                    100
                    if closed
                    else
                    0
                )


                total_r = 0.0


                for trade in selected_trades:

                    if (
                        trade["Outcome"]
                        ==
                        "WIN"
                    ):

                        total_r += trade["RR"]

                    elif (
                        trade["Outcome"]
                        ==
                        "LOSS"
                    ):

                        total_r -= 1


                all_summary.append(
                    {

                        "Symbol":
                            symbol,

                        "Timeframe":
                            tf,

                        "SL Method":
                            sl_type,

                        "Signals":
                            len(
                                selected_trades
                            ),

                        "Wins":
                            wins,

                        "Losses":
                            losses,

                        "Open":
                            opens,

                        "Win Rate %":
                            round(
                                win_rate,
                                2
                            ),

                        "Total R":
                            round(
                                total_r,
                                2
                            )
                    }
                )


        # ======================================================
        # SYMBOL DISPLAY
        # ======================================================

        symbol_summary = [
            x
            for x in all_summary
            if x["Symbol"] == symbol
        ]


        if symbol_summary:

            summary_df = pd.DataFrame(
                symbol_summary
            )


            detail_df = pd.DataFrame(
                [
                    x
                    for x in all_details
                    if x["Symbol"] == symbol
                ]
            )


            with st.expander(
                f"📊 نتائج {symbol}",
                expanded=(
                    len(symbols_to_test)
                    ==
                    1
                )
            ):

                st.subheader(
                    (
                        "مقارنة الفواصل وطرق وقف الخسارة"
                        if lang == "العربية"
                        else
                        "Timeframe & Stop Loss Comparison"
                    )
                )


                st.dataframe(
                    summary_df,
                    use_container_width=True,
                    hide_index=True
                )


                st.subheader(
                    (
                        "السجل التاريخي للصفقات"
                        if lang == "العربية"
                        else
                        "Historical Trade Log"
                    )
                )


                if not detail_df.empty:

                    st.dataframe(
                        detail_df,
                        use_container_width=True,
                        hide_index=True
                    )


    # ========================================================
    # FINISHED
    # ========================================================

    progress_bar.progress(
        1.0
    )


    progress_text.markdown(
        (
            "**100% — اكتمل الاختبار الرجعي ✅**"
            if lang == "العربية"
            else
            "**100% — Backtest completed ✅**"
        )
    )


    current_task.success(
        (
            "✅ انتهى تحليل جميع الأصول والفواصل الزمنية."
            if lang == "العربية"
            else
            "✅ All assets and timeframes have been analyzed."
        )
    )


    # ========================================================
    # FINAL REPORT
    # ========================================================

    if all_summary:

        final_df = pd.DataFrame(
            all_summary
        )


        st.header(
            (
                "🏆 التقرير النهائي"
                if lang == "العربية"
                else
                "🏆 Final Report"
            )
        )


        total_signals = int(
            final_df["Signals"].sum()
        )

        total_wins = int(
            final_df["Wins"].sum()
        )

        total_losses = int(
            final_df["Losses"].sum()
        )

        total_open = int(
            final_df["Open"].sum()
        )


        closed = (
            total_wins
            +
            total_losses
        )


        overall_wr = (
            total_wins
            /
            closed
            *
            100
            if closed
            else
            0
        )


        total_r = round(
            final_df["Total R"].sum(),
            2
        )


        c1, c2, c3, c4, c5 = (
            st.columns(5)
        )


        c1.metric(
            (
                "الإشارات"
                if lang == "العربية"
                else
                "Signals"
            ),
            total_signals
        )

        c2.metric(
            "Wins",
            total_wins
        )

        c3.metric(
            "Losses",
            total_losses
        )

        c4.metric(
            "Win Rate",
            f"{overall_wr:.2f}%"
        )

        c5.metric(
            "Total R",
            total_r
        )


        # ====================================================
        # BEST CONFIGURATION
        # ====================================================

        best = (
            final_df
            .sort_values(
                [
                    "Win Rate %",
                    "Total R",
                    "Signals"
                ],
                ascending=[
                    False,
                    False,
                    False
                ]
            )
            .iloc[0]
        )


        st.subheader(
            (
                "🏆 أفضل إعداد"
                if lang == "العربية"
                else
                "🏆 Best Configuration"
            )
        )


        st.success(
            (
                f"الفاصل الأفضل: **{best['Timeframe']}** | "
                f"وقف الخسارة الأفضل: **{best['SL Method']}** | "
                f"Win Rate: **{best['Win Rate %']}%** | "
                f"Total R: **{best['Total R']}**"
                if lang == "العربية"
                else
                f"Best Timeframe: **{best['Timeframe']}** | "
                f"Best SL: **{best['SL Method']}** | "
                f"Win Rate: **{best['Win Rate %']}%** | "
                f"Total R: **{best['Total R']}**"
            )
        )


        # ====================================================
        # FINAL TABLE
        # ====================================================

        st.subheader(
            (
                "📊 المقارنة النهائية"
                if lang == "العربية"
                else
                "📊 Final Comparison"
            )
        )


        final_df = (
            final_df
            .sort_values(
                [
                    "Win Rate %",
                    "Total R"
                ],
                ascending=False
            )
        )


        st.dataframe(
            final_df,
            use_container_width=True,
            hide_index=True
        )


    else:

        st.warning(
            (
                "⚠️ لم يتم العثور على أي صفقات ضمن الإعدادات المحددة."
                if lang == "العربية"
                else
                "⚠️ No trades were found for the selected settings."
            )
)
