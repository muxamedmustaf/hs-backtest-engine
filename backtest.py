def draw_rectangle_pattern(fig, source, total_len):
    """يرسم مستطيلاً بأربعة حواف مستقيمة باستخدام add_shape (لضمان التطابق التام)."""
    if source is None:
        return

    box = source.get("consolidation_box")
    if not box:
        return

    x_start = int(box["x_start"])
    x_end   = int(box["x_end"])
    box_high = float(box["high"])
    box_low  = float(box["low"])

    # ─── 1. التعبئة الخفيفة (خلف الشموع) ───
    fig.add_shape(
        type="rect",
        x0=x_start, y0=box_low,
        x1=x_end,   y1=box_high,
        line=dict(width=0),
        fillcolor="rgba(156, 39, 176, 0.07)",
        layer="below",
    )

    # ─── 2. الحد العلوي (مقاومة، خط أزرق سميك مستقيم) ───
    fig.add_shape(
        type="line",
        x0=x_start, y0=box_high,
        x1=x_end,   y1=box_high,
        line=dict(color="#2962FF", width=4),
        layer="above",
    )

    # ─── 3. الحد السفلي (دعم، خط أحمر سميك مستقيم) ───
    fig.add_shape(
        type="line",
        x0=x_start, y0=box_low,
        x1=x_end,   y1=box_low,
        line=dict(color="#FF5252", width=4),
        layer="above",
    )

    # ─── 4. الحد الأيسر (عمودي، منقط) ───
    fig.add_shape(
        type="line",
        x0=x_start, y0=box_low,
        x1=x_start, y1=box_high,
        line=dict(color="#9C27B0", width=2, dash="dot"),
        layer="above",
    )

    # ─── 5. الحد الأيمن (عمودي، منقط) ───
    fig.add_shape(
        type="line",
        x0=x_end, y0=box_low,
        x1=x_end, y1=box_high,
        line=dict(color="#9C27B0", width=2, dash="dot"),
        layer="above",
    )

    # ─── 6. علامات اللمسات (قمم زرقاء + قيعان حمراء) ───
    top_nodes = source.get("top_nodes") or []
    bot_nodes = source.get("bot_nodes") or []

    if top_nodes:
        fig.add_trace(go.Scatter(
            x=[n[0] for n in top_nodes],
            y=[n[1] for n in top_nodes],
            mode="markers",
            name="قمم",
            marker=dict(size=13, color="#2962FF", symbol="circle",
                        line=dict(color="white", width=2.5)),
            showlegend=True,
        ))
    if bot_nodes:
        fig.add_trace(go.Scatter(
            x=[n[0] for n in bot_nodes],
            y=[n[1] for n in bot_nodes],
            mode="markers",
            name="قيعان",
            marker=dict(size=13, color="#FF5252", symbol="circle",
                        line=dict(color="white", width=2.5)),
            showlegend=True,
        ))

    # ─── 7. نجمة الدخول ───
    entry_nodes = source.get("nodes") or []
    if entry_nodes:
        fig.add_trace(go.Scatter(
            x=[n[0] for n in entry_nodes],
            y=[n[1] for n in entry_nodes],
            mode="markers",
            name="الدخول",
            marker=dict(size=22, color="#FFC107", symbol="star",
                        line=dict(color="black", width=2)),
            showlegend=True,
        ))

    # ─── 8. سهم الهدف ───
    arrow = source.get("arrow")
    if isinstance(arrow, dict):
        col = "#00C853" if arrow.get("direction") == "BUY" else "#D50000"
        fig.add_annotation(
            x=arrow["x1"], y=arrow["y1"],
            ax=arrow["x0"], ay=arrow["y0"],
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=3, arrowsize=2.5, arrowwidth=4,
            arrowcolor=col, opacity=0.95,
            text="TP", font=dict(color=col, size=13),
        )
