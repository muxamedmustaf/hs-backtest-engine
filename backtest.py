import streamlit as st
import pandas as pd
import datetime
import data_provider as dp
# import engine  # قم بإزالة التعليق عندما تريد ربط محرك البحث

# --- إعدادات الصفحة ---
st.set_page_config(page_title="مختبر الصناديق السعرية", page_icon="🧪", layout="wide")

# --- دالة مساعدة لفلترة البيانات وعرضها (لتجنب تكرار الكود) ---
def _run_backtest(df, start_date, end_date):
    # فلترة البيانات حسب التاريخ المختار
    df_filtered = df[(df.index >= pd.to_datetime(start_date)) & 
                     (df.index <= pd.to_datetime(end_date))]
    
    if df_filtered.empty:
        st.warning("⚠️ لا توجد بيانات في هذا النطاق الزمني المحدد (من - إلى).")
    else:
        st.info(f"تم فلترة البيانات. عدد الشمعات المتاحة للمحاكاة: {len(df_filtered)}")
        
        # هنا يتم تمرير البيانات لمحرك engine.py
        # trades = engine.run_backtest(df_filtered, ...)
        
        st.write("### نظرة عامة على السعر (للتأكيد):")
        st.line_chart(df_filtered['close'])

# --- القائمة الجانبية (Sidebar) ---
with st.sidebar:
    st.header("⚙️ إعدادات النظام")
    
    st.markdown("### تحديث البيانات")
    st.info("لتجنب حظر الـ API (8 طلبات/دقيقة)، سيستغرق تحديث كل رمز 8 ثوانٍ.")
    
    symbols_to_update = st.text_area("الرموز (مفصولة بفاصلة):", "BTC/USD, ETH/USD, EUR/USD")
    interval_update = st.selectbox("الإطار الزمني للتحديث:", ["1h", "4h", "1day"])
    
    if st.button("📥 تحديث وحفظ في GitHub", use_container_width=True):
        symbols_list = [s.strip() for s in symbols_to_update.split(",") if s.strip()]
        
        with st.status(f"جاري تحديث {len(symbols_list)} رموز... يرجى الانتظار", expanded=True) as status:
            st.write("بدء عملية الجلب...")
            success = dp.update_multiple_symbols(symbols_list, interval_update)
            status.update(label=f"✅ تم تحديث {success} من أصل {len(symbols_list)} رموز بنجاح!", state="complete", expanded=False)
            st.cache_data.clear()
            st.success("تم الحفظ في GitHub بنجاح.")

    st.divider()
    st.caption("تطبيق تحليل البرايس أكشن - إصدار 2.1")

# --- واجهة المستخدم الرئيسية ---
st.title("🧪 مختبر الصناديق السعرية (Box Breakout)")
st.markdown("تحليل وتداول نماذج الصناديق باستخدام البرايس أكشن الخالص.")

# إنشاء التبويبات الثلاثة
tab1, tab2, tab3 = st.tabs(["🚀 الماسح الحي", "🧪 مختبر الاختبار", "📊 عرض بيانات الرمز"])

# ==========================================
# التبويب الأول: الماسح الحي
# ==========================================
with tab1:
    st.subheader("الماسح الحي (Live Scanner)")
    st.info("يقوم هذا القسم بمسح الرموز المحددة بحثاً عن نماذج مكتملة (موجة حافزة -> صندوق -> كسر -> إعادة اختبار).")
    
    col1, col2 = st.columns(2)
    with col1:
        scan_interval = st.selectbox("الإطار الزمني للمسح:", ["1h", "4h", "1day"], key="scan_tf")
    with col2:
        scan_symbols = st.text_input("الرموز المراد مسحها:", "BTC/USD, ETH/USD", key="scan_syms")
        
    if st.button("بدء المسح الآن 🚀", use_container_width=True):
        with st.spinner("جاري فحص الرموز..."):
            # هنا يتم استدعاء محرك البحث engine.py
            st.write("### النتائج:")
            st.success("تم الانتهاء من المسح (يجب ربط المحرك هنا).")

# ==========================================
# التبويب الثاني: مختبر الاختبار (تم تعديله ليقرأ من المحلي)
# ==========================================
with tab2:
    st.subheader("مختبر الاختبار الرجعي (Backtest)")
    
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            method = st.radio("طريقة الفحص:", ["سهم فردي", "مجموعة"], horizontal=True)
            symbol = st.text_input("رمز الأصل:", "BTC/USD")
        with col2:
            st.write("") 
            st.write("")
            interval = st.selectbox("الإطار الزمني:", ["1h", "4h", "1day"])

        col3, col4 = st.columns(2)
        with col3:
            start_date = st.date_input("من:", datetime.date(2025, 1, 1))
        with col4:
            end_date = st.date_input("إلى:", datetime.date(2026, 10, 20))

        st.divider()
        
        # ⬇️⬇️ خيار مصدر البيانات ⬇️⬇️
        data_source = st.radio(
            "📁 مصدر البيانات للمحاكاة:",
            ["البيانات المحفوظة (GitHub - سريع جداً)", "جلب مباشر من الإنترنت (API - بطيء)"],
            help="اختر 'البيانات المحفوظة' لاستخدام الملفات التي قمت بتحميلها مسبقاً."
        )
        
        if st.button("📊 بدء المحاكاة", use_container_width=True, type="primary"):
            
            # إذا اختار المستخدم البيانات المحفوظة
            if data_source == "البيانات المحفوظة (GitHub - سريع جداً)":
                with st.spinner(f"جاري قراءة بيانات {symbol} من المخزن المحلي..."):
                    # نستخدم دالة القراءة المباشرة من GitHub
                    df = dp.load_from_github(symbol, interval)
                    
                    if df is None or df.empty:
                        st.error(f"❌ لا توجد بيانات محفوظة للرمز {symbol} في الإطار {interval}. يرجى التوجه للقائمة الجانبية (اليسار) والضغط على 'تحديث وحفظ في GitHub' أولاً.")
                    else:
                        st.success(f"✅ تم تحميل {len(df)} شمعة من الملفات المحفوظة.")
                        _run_backtest(df, start_date, end_date)

            # إذا اختار المستخدم الجلب المباشر
            else:
                with st.spinner(f"جاري جلب بيانات {symbol} من الإنترنت (قد يستغرق بعض الوقت)..."):
                    df = dp.get_data(symbol, interval, force_update=True)
                    
                    if df is None or df.empty:
                        st.error("فشل جلب البيانات من الـ API.")
                    else:
                        st.success(f"✅ تم جلب {len(df)} شمعة من الإنترنت.")
                        _run_backtest(df, start_date, end_date)

# ==========================================
# التبويب الثالث: عرض بيانات الرمز
# ==========================================
with tab3:
    st.subheader("📊 عرض بيانات الرمز")
    
    view_symbol = st.text_input("أدخل الرمز لعرض بياناته المخزنة:", "BTC/USD")
    view_interval = st.selectbox("الإطار الزمني:", ["1h", "4h", "1day"], key="view_tf")
    
    if st.button("عرض البيانات المخزنة"):
        with st.spinner("جاري تحميل البيانات من GitHub..."):
            df_view = dp.load_from_github(view_symbol, view_interval)
            
            if df_view is not None and not df_view.empty:
                st.success(f"تم العثور على البيانات. إجمالي الشمعات: {len(df_view)}")
                st.dataframe(df_view.tail(100), use_container_width=True) 
            else:
                st.warning("⚠️ لا توجد بيانات مخزنة لهذا الرمز. يرجى تحديثه من القائمة الجانبية أولاً.")
