# ═══════════════════════════════════════════════════════════════════════
# 🧮 حاسبة حسابية (جمع / طرح / ضرب / قسمة)
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### 🧮 حاسبة حسابية")
st.caption("أدخل رقمين ثم اختر العملية")

# حفظ نتيجة العملية السابقة في session_state
calc_key = f"{unique_id}_calc_result"
if calc_key not in st.session_state:
    st.session_state[calc_key] = 0.0

c_a, c_b = st.columns(2)
with c_a:
    num_a = st.number_input(
        "🔢 الرقم الأول:",
        value=float(st.session_state.get(f"{unique_id}_calc_a", 0.0)),
        step=1.0, format="%.4f",
        key=f"{unique_id}_calc_a"
    )
with c_b:
    num_b = st.number_input(
        "🔢 الرقم الثاني:",
        value=float(st.session_state.get(f"{unique_id}_calc_b", 0.0)),
        step=1.0, format="%.4f",
        key=f"{unique_id}_calc_b"
    )

# أزرار العمليات
op1, op2, op3, op4 = st.columns(4)
result_val = None
op_symbol = ""

with op1:
    if st.button("➕ جمع", use_container_width=True, key=f"{unique_id}_calc_add"):
        result_val = num_a + num_b
        op_symbol = "+"
with op2:
    if st.button("➖ طرح", use_container_width=True, key=f"{unique_id}_calc_sub"):
        result_val = num_a - num_b
        op_symbol = "−"
with op3:
    if st.button("✖️ ضرب", use_container_width=True, key=f"{unique_id}_calc_mul"):
        result_val = num_a * num_b
        op_symbol = "×"
with op4:
    if st.button("➗ قسمة", use_container_width=True, key=f"{unique_id}_calc_div"):
        if num_b != 0:
            result_val = num_a / num_b
            op_symbol = "÷"
        else:
            st.error("⚠️ لا يمكن القسمة على صفر")

if result_val is not None:
    st.session_state[calc_key] = result_val
    st.session_state[f"{unique_id}_calc_last_op"] = op_symbol
    st.session_state[f"{unique_id}_calc_last_a"] = num_a
    st.session_state[f"{unique_id}_calc_last_b"] = num_b

# عرض النتيجة
last_op = st.session_state.get(f"{unique_id}_calc_last_op", "")
last_a = st.session_state.get(f"{unique_id}_calc_last_a", 0)
last_b = st.session_state.get(f"{unique_id}_calc_last_b", 0)
current_result = st.session_state.get(calc_key, 0.0)

if last_op:
    st.success(f"### = `{current_result:.4f}`  ({last_a:.4f} {last_op} {last_b:.4f})")
else:
    st.info(f"### النتيجة: `{current_result:.4f}`")

# أزرار إضافية
ax1, ax2, ax3 = st.columns(3)
with ax1:
    if st.button("↩️ مسح النتيجة", use_container_width=True, key=f"{unique_id}_calc_clear"):
        st.session_state[calc_key] = 0.0
        st.session_state[f"{unique_id}_calc_last_op"] = ""
        st.session_state[f"{unique_id}_calc_a"] = 0.0
        st.session_state[f"{unique_id}_calc_b"] = 0.0
        st.rerun()
with ax2:
    if st.button("📋 نسخ النتيجة للدخول", use_container_width=True, key=f"{unique_id}_calc_copy_entry"):
        # نضعها كسعر دخول
        if sel in st.session_state:
            st.session_state[f"{unique_id}_e_{sel}"] = float(current_result)
            st.rerun()
with ax3:
    if st.button("📋 نسخ النتيجة للوت", use_container_width=True, key=f"{unique_id}_calc_copy_lot"):
        if sel in st.session_state:
            st.session_state[f"{unique_id}_lot_{sel}"] = max(0.0001, float(current_result))
            st.rerun()

# العمليات السريعة
st.markdown("##### ⚡ عمليات سريعة")
q1, q2, q3, q4, q5, q6 = st.columns(6)
with q1:
    if st.button("×2", use_container_width=True, key=f"{unique_id}_calc_x2"):
        st.session_state[calc_key] = current_result * 2
        st.session_state[f"{unique_id}_calc_last_op"] = "×2"
        st.session_state[f"{unique_id}_calc_last_a"] = current_result
        st.session_state[f"{unique_id}_calc_last_b"] = 2
        st.rerun()
with q2:
    if st.button("÷2", use_container_width=True, key=f"{unique_id}_calc_/2"):
        st.session_state[calc_key] = current_result / 2
        st.session_state[f"{unique_id}_calc_last_op"] = "÷2"
        st.session_state[f"{unique_id}_calc_last_a"] = current_result
        st.session_state[f"{unique_id}_calc_last_b"] = 2
        st.rerun()
with q3:
    if st.button("×3", use_container_width=True, key=f"{unique_id}_calc_x3"):
        st.session_state[calc_key] = current_result * 3
        st.session_state[f"{unique_id}_calc_last_op"] = "×3"
        st.session_state[f"{unique_id}_calc_last_a"] = current_result
        st.session_state[f"{unique_id}_calc_last_b"] = 3
        st.rerun()
with q4:
    if st.button("÷3", use_container_width=True, key=f"{unique_id}_calc_/3"):
        st.session_state[calc_key] = current_result / 3
        st.session_state[f"{unique_id}_calc_last_op"] = "÷3"
        st.session_state[f"{unique_id}_calc_last_a"] = current_result
        st.session_state[f"{unique_id}_calc_last_b"] = 3
        st.rerun()
with q5:
    if st.button("+10%", use_container_width=True, key=f"{unique_id}_calc_+10"):
        st.session_state[calc_key] = current_result * 1.10
        st.session_state[f"{unique_id}_calc_last_op"] = "+10%"
        st.session_state[f"{unique_id}_calc_last_a"] = current_result
        st.session_state[f"{unique_id}_calc_last_b"] = 1.10
        st.rerun()
with q6:
    if st.button("-10%", use_container_width=True, key=f"{unique_id}_calc_-10"):
        st.session_state[calc_key] = current_result * 0.90
        st.session_state[f"{unique_id}_calc_last_op"] = "-10%"
        st.session_state[f"{unique_id}_calc_last_a"] = current_result
        st.session_state[f"{unique_id}_calc_last_b"] = 0.90
        st.rerun()
