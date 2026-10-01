# ═══════════════════════════════════════════════════════════════════════
# 🔬 التقرير التشخيصي الذكي — نجاح/فشل/لا مفر منه
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
with st.expander("🔬 التقرير التشخيصي الذكي — تحليل النجاح والفشل", expanded=True):
    try:
        from engine import diagnose_filters

        df_for_diag = dfs_dict.get(active_sym)
        if df_for_diag is None or df_for_diag.empty:
            st.warning("⚠️ لا توجد بيانات خام لهذا الرمز")
        else:
            with st.spinner("جاري التشخيص الذكي..."):
                diag = diagnose_filters(
                    df_for_diag,
                    interval=selected_interval,
                    symbol=active_sym,
                )

            if diag.get("error"):
                st.error(f"❌ {diag['error']}")
            else:
                # ─── 1. ملخص المراحل ───
                col1, col2, col3 = st.columns(3)
                col1.metric("أنماط خام", diag["total_raw_candidates"])
                col2.metric("بعد الفلاتر", diag["final_count"])
                col3.metric(
                    "نسبة القبول",
                    f"{round(diag['final_count'] / max(diag['total_raw_candidates'], 1) * 100, 1)}%"
                )

                # ─── 2. الحكم النهائي ───
                smart = diag.get("smart_diagnosis", {})
                if smart.get("verdict"):
                    st.markdown(f"### 🎯 الحكم النهائي: {smart['verdict']}")

                # ─── 3. تفصيل النجاح ───
                wb = smart.get("win_breakdown", {})
                if wb.get("total_wins", 0) > 0:
                    st.markdown("#### ✅ تفصيل الصفقات الناجحة")
                    w1, w2 = st.columns(2)
                    w1.metric("عدد الصفقات الناجحة", wb["total_wins"])
                    w2.metric("متوسط الوصول للهدف", f"{wb['avg_max_reach']}%")

                # ─── 4. تفصيل الفشل ───
                lb = smart.get("loss_breakdown", {})
                if any(v > 0 for v in lb.values()):
                    st.markdown("#### ❌ تفصيل الصفقات الخاسرة")
                    f1, f2, f3, f4 = st.columns(4)
                    f1.metric("رفض فوري", lb.get("immediate_rejection", 0))
                    f2.metric("انعكاس مبكر", lb.get("early_reversal", 0))
                    f3.metric("انعكاس متوسط", lb.get("mid_reversal", 0))
                    f4.metric("انعكاس متأخر", lb.get("late_reversal", 0))

                    u1, u2 = st.columns(2)
                    u1.metric("⚪ لا مفر منها", lb.get("unavoidable", 0),
                              help="خسائر إحصائية طبيعية — لا تحاول تجنبها")
                    u2.metric("🔴 قابلة للتجنب", lb.get("avoidable", 0),
                              help="خسائر يمكن تقليلها بتحسين الفلاتر")

                # ─── 5. خطة العمل ───
                if smart.get("action_plan"):
                    st.markdown("#### 🎯 خطة العمل الذكية")
                    for item in smart["action_plan"]:
                        if item.startswith("🔴"):
                            st.error(item)
                        elif item.startswith("🟡"):
                            st.warning(item)
                        elif item.startswith("🟢"):
                            st.success(item)
                        else:
                            st.info(item)

                # ─── 6. جدول تحليل كل صفقة ───
                trades = diag.get("trade_analysis", [])
                if trades:
                    st.markdown("#### 📋 تحليل كل صفقة على حدة")
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
                        "لا مفر منها": "نعم" if t["is_unavoidable"] else "لا",
                        "السبب": t["reason"][:80] + "..." if len(t["reason"]) > 80 else t["reason"],
                    } for t in trades])

                    st.dataframe(trade_table, use_container_width=True)

                    # ─── 7. التوصيات الفردية ───
                    with st.expander("💡 توصيات لكل صفقة"):
                        for t in trades:
                            if t.get("recommendation"):
                                badge = "✅" if t["result"] == "WIN" else (
                                    "⚪" if t["is_unavoidable"] else "🔴"
                                )
                                st.markdown(
                                    f"**{badge} صفقة #{t['trade_num']}** — "
                                    f"{t['result']} | الوصول: {t['max_reach_%']}%\n\n"
                                    f"- السبب: {t['reason']}\n"
                                    f"- التوصية: {t['recommendation']}"
                                )

                # ─── 8. جدول الفلاتر ───
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

                # ─── 9. توصيات عامة ───
                if diag["recommendations"]:
                    st.markdown("#### 🎯 توصيات عامة")
                    for r in diag["recommendations"]:
                        if "حرج" in r["severity"]:
                            st.error(f"🔴 {r['message']}")
                        elif "متوسط" in r["severity"]:
                            st.warning(f"🟡 {r['message']}")
                        else:
                            st.info(f"ℹ️ {r['message']}")

                # ─── 10. عينات مرفوضة ───
                if diag["rejection_samples"]:
                    st.markdown("#### 🔍 عينات من الأنماط المرفوضة")
                    for filter_name, samples in diag["rejection_samples"].items():
                        with st.expander(f"{filter_name} ({len(samples)} عينة)"):
                            st.dataframe(pd.DataFrame(samples), use_container_width=True)

    except Exception as e:
        import traceback
        st.error(f"⚠️ خطأ في التقرير التشخيصي: {type(e).__name__}: {e}")
        st.code(traceback.format_exc())
