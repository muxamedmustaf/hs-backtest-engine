import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import importlib
import engine

st.set_page_config(
    page_title="Pattern Backtest",
    page_icon="📊",
    layout="wide"
)

# إضافة CSS لتوسيع نافذة الشارت أفقياً لملء كامل عرض الشاشة
st.markdown("""
    <style>
        .main .block-container {
            max-width: 100% !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        div[data-testid="stPlotlyChart"],
        div[data-testid="stPlotlyChart"] > div,
        .js-plotly-plot,
        .plot-container,
        .svg-container,
        svg.main-svg {
            width: 100% !important;
            min-width: 100% !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Pattern Backtest")
st.caption("هذا الملف ثابت ويقرأ نمط الاختبار من engine.py في كل تشغيل.")

# إعادة تحميل engine حتى يقرأ آخر نسخة محفوظة منه
engine = importlib.reload(engine)

st.sidebar.header("إعدادات الاختبار")

symbol = st.sidebar.text_input("Symbol", "NZDCAD=X")
interval = st.sidebar.selectbox(
    "Timeframe",
    ["1h", "4h", "1d"],
    index=1
)

period = st.sidebar.selectbox(
    "Historical Data",
    ["3mo", "6mo", "1y", "2y", "5y"],
    index=1
)

# 4H في Yahoo Finance: نجلب 1h ثم نعيد التجميع
yf_interval = "1h" if interval == "4h" else interval

run = st.sidebar.button("🚀 تشغيل الاختبار", use_container_width=True)

if run:
    with st.spinner("جلب البيانات وتشغيل الاختبار الرجعي..."):
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=yf_interval,
                progress=False,
                auto_adjust=False
            )

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty:
                st.error("لم يتم الحصول على بيانات.")
                st.stop()

            required = ["Open", "High", "Low", "Close"]
            df = df[required].dropna()

            if interval == "4h":
                df = (
                    df.resample("4h")
                    .agg({
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last"
                    })
                    .dropna()
                )

            if len(df) < 60:
                st.error(f"البيانات غير كافية: {len(df)} شمعة فقط.")
                st.stop()

            # --------------------------------------------------
            # الاختبار الحقيقي:
            # كل نقطة زمنية تستخدم البيانات السابقة فقط.
            # engine.py هو الذي يحتوي منطق النمط.
            # --------------------------------------------------
            detections = []

            for end in range(60, len(df)):
                history = df.iloc[:end].copy()

                try:
                    result = engine.run_full_analysis(history)
                except Exception:
                    continue

                if not isinstance(result, dict):
                    continue

                pattern = str(
                    result.get("pattern")
                    or result.get("name")
                    or ""
                )

                # لا نعتمد على signal فقط؛ نبحث عن اسم النمط
                # الذي يكتشفه engine.py.
                if "head" in pattern.lower() and "shoulder" in pattern.lower():
                    detections.append({
                        "pos": end - 1,
                        "time": df.index[end - 1],
                        "price": float(df["Close"].iloc[end - 1]),
                        "pattern": pattern,
                        "signal": result.get("signal", ""),
                        "bias": result.get("bias", ""),
                        "entry": result.get(
                            "entry",
                            result.get("entry_trigger", None)
                        ),
                        "sl": result.get("sl", None),
                        "tp": result.get(
                            "tp",
                            result.get("target", None)
                        ),
                        "nodes": result.get("nodes", [])
                    })

            st.session_state["bt_df"] = df
            st.session_state["bt_detections"] = detections

        except Exception as e:
            st.error(f"خطأ أثناء الاختبار: {e}")
            st.stop()

if "bt_df" in st.session_state:

    df = st.session_state["bt_df"]
    detections = st.session_state["bt_detections"]

    st.subheader("نتيجة الاختبار")

    c1, c2, c3 = st.columns(3)
    c1.metric("عدد مرات ظهور النمط", len(detections))
    c2.metric("الشموع المختبرة", len(df))
    c3.metric("الفترة", period)

    if not detections:
        st.warning(
            "لم يكتشف engine.py نمط الرأس والكتفين في الفترة المختبرة."
        )
        st.stop()

    # --------------------------------------------------
    # رسم آخر ظهور مكتشف
    # --------------------------------------------------
    selected = st.selectbox(
        "اختر ظهوراً لعرضه على الشارت",
        range(len(detections)),
        format_func=lambda i:
            f"{i + 1} — {detections[i]['time']} — "
            f"{detections[i]['pattern']}"
    )

    d = detections[selected]

    # نعرض منطقة حول النمط
    start = max(0, d["pos"] - 45)
    end = min(len(df), d["pos"] + 15)
    chart_df = df.iloc[start:end]

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

    nodes = d.get("nodes", [])

    if nodes:
        x = []
        y = []

        for node in nodes:
            try:
                x.append(node[0])
                y.append(float(node[1]))
            except Exception:
                pass

        if x:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines+markers",
                    name=d["pattern"],
                    line=dict(width=3),
                    marker=dict(size=8)
                )
            )

    fig.update_layout(
        template="plotly_white",
        height=600,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=20, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("كل مرات ظهور النمط")

    table = pd.DataFrame([
        {
            "الرقم": i + 1,
            "التاريخ": x["time"],
            "السعر": x["price"],
            "النمط": x["pattern"],
            "الإشارة": x["signal"],
            "الاتجاه": x["bias"]
        }
        for i, x in enumerate(detections)
    ])

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "ملاحظة: هذا الاختبار يقيس مرات اكتشاف النمط بواسطة engine.py. "
        "ولا يعتبر النجاح ربحاً إلا إذا أضفنا لاحقاً قاعدة واضحة لقياس "
        "هل وصل السعر إلى TP قبل SL."
    )
else:
    st.info(
        "ضع هذا الملف باسم backtest.py بجانب engine.py، "
        "ثم شغله. عند تغيير engine.py لا تحتاج إلى تغيير backtest.py."
    )
    
