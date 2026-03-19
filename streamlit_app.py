"""
Cognitive Accessibility Assistant — Streamlit App
==================================================
Analyses web pages for cognitive accessibility barriers across five dimensions,
maps findings to WCAG 2.2 and ISO 9241-11, and includes a NASA-TLX evaluation module.

Run: streamlit run app.py
"""

import streamlit as st
import anthropic
import json
import re
import math
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CogAccess — Cognitive Accessibility Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Global */
    .main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    
    /* Metric cards */
    div[data-testid="metric-container"] {
        background: #f8f7ff;
        border: 1px solid #e2e0f9;
        border-radius: 12px;
        padding: 1rem;
    }
    
    /* Score colour bands */
    .score-good  { color: #0f6e56; font-weight: 600; }
    .score-warn  { color: #854f0b; font-weight: 600; }
    .score-bad   { color: #a32d2d; font-weight: 600; }
    
    /* Finding cards */
    .finding-high { border-left: 4px solid #e24b4a; background:#fff5f5;
                    border-radius:10px; padding:1rem 1.2rem; margin-bottom:.8rem; }
    .finding-med  { border-left: 4px solid #ba7517; background:#fffbf0;
                    border-radius:10px; padding:1rem 1.2rem; margin-bottom:.8rem; }
    .finding-low  { border-left: 4px solid #1d9e75; background:#f0faf6;
                    border-radius:10px; padding:1rem 1.2rem; margin-bottom:.8rem; }

    /* Tag pills */
    .tag-wcag  { background:#eeedfe; color:#3c3489; border-radius:100px;
                 padding:2px 10px; font-size:12px; font-weight:500; }
    .tag-iso   { background:#e1f5ee; color:#085041; border-radius:100px;
                 padding:2px 10px; font-size:12px; font-weight:500; }
    .tag-dim   { background:#f1efe8; color:#444441; border-radius:100px;
                 padding:2px 10px; font-size:12px; }

    /* Adaptation cards */
    .adapt-card { background:#fafafa; border:1px solid #e8e8e8;
                  border-radius:12px; padding:1rem 1.2rem; margin-bottom:.8rem; }
    .tradeoff   { background:#fff9ec; border-radius:8px; padding:.6rem .9rem;
                  font-size:13px; color:#854f0b; margin-top:.5rem; }

    /* NASA-TLX */
    .nasa-score-display { text-align:center; padding:1.5rem;
                          background:#f8f7ff; border-radius:16px; }
    .nasa-big  { font-size:52px; font-weight:700; line-height:1; }
    .nasa-sub  { font-size:14px; color:#666; margin-top:.4rem; }
    
    /* Sidebar */
    .sidebar-section { background:#f8f7ff; border-radius:10px;
                        padding:1rem; margin-bottom:1rem; }
    
    /* Summary box */
    .summary-box { background: linear-gradient(135deg,#f8f7ff,#e1f5ee);
                   border-radius:12px; padding:1.2rem 1.5rem;
                   border:1px solid #e2e0f9; margin-bottom:1.5rem; }
</style>
""", unsafe_allow_html=True)


# ── Constants ────────────────────────────────────────────────────────────────
DIMENSIONS = [
    {"key": "language",   "label": "Language complexity",    "wcag": "3.1.5", "iso": "Effectiveness"},
    {"key": "layout",     "label": "Layout density",         "wcag": "1.4.8", "iso": "Efficiency"},
    {"key": "hierarchy",  "label": "Visual hierarchy",       "wcag": "1.3.1", "iso": "Satisfaction"},
    {"key": "animation",  "label": "Animation & motion",     "wcag": "2.2.2", "iso": "Efficiency"},
    {"key": "navigation", "label": "Navigation consistency",  "wcag": "3.2.3", "iso": "Effectiveness"},
]

NASA_DIMS = [
    {"key": "md", "label": "Mental demand",   "desc": "How mentally demanding was the task?"},
    {"key": "pd", "label": "Physical demand",  "desc": "How physically demanding?"},
    {"key": "td", "label": "Temporal demand",  "desc": "How hurried or rushed?"},
    {"key": "pe", "label": "Performance",      "desc": "How successful were you (0 = perfect, 100 = failure)?"},
    {"key": "ef", "label": "Effort",           "desc": "How hard did you work to accomplish this?"},
    {"key": "fr", "label": "Frustration",      "desc": "How irritated, stressed, or annoyed?"},
]

DIM_ICONS = {
    "Language":   "📝",
    "Layout":     "🗂️",
    "Motion":     "⏸️",
    "Navigation": "🧭",
    "Hierarchy":  "🔤",
}


# ── Helpers ──────────────────────────────────────────────────────────────────
def score_colour(s: int) -> str:
    if s >= 75: return "#1d9e75"
    if s >= 50: return "#ba7517"
    return "#e24b4a"

def score_label(s: int) -> str:
    if s >= 75: return "✅ Good"
    if s >= 50: return "⚠️ Needs attention"
    return "🔴 Barrier"

def severity_class(sev: str) -> str:
    return {"High": "finding-high", "Medium": "finding-med", "Low": "finding-low"}.get(sev, "finding-low")

def nasa_interpret(avg: int) -> tuple[str, str]:
    if avg <= 25:
        return "#1d9e75", "Low cognitive load — strong alignment with ISO 9241-11 efficiency and satisfaction goals."
    if avg <= 50:
        return "#ba7517", "Moderate load — users may experience mental strain. Consider reducing information density."
    if avg <= 75:
        return "#ba7517", "High load — significant barriers likely for neurodivergent users. Review language, layout, and navigation."
    return "#e24b4a", "Very high load — serious accessibility barriers. Urgent review recommended against WCAG Cognitive Accessibility Guidance."


# ── Anthropic analysis ───────────────────────────────────────────────────────
def build_prompt(url: str) -> str:
    return f"""You are a cognitive accessibility expert specialising in WCAG 2.2 and ISO 9241-11.
Analyse the web page at: {url}

Return ONLY a valid JSON object (no markdown fences, no preamble) with this exact structure:
{{
  "scores": {{
    "language": <0-100>,
    "layout": <0-100>,
    "hierarchy": <0-100>,
    "animation": <0-100>,
    "navigation": <0-100>
  }},
  "findings": [
    {{
      "title": "<short issue title>",
      "dimension": "<Language|Layout|Hierarchy|Animation|Navigation>",
      "severity": "<High|Medium|Low>",
      "explanation": "<2-3 sentences explaining why this creates cognitive load, with specific reference to neurodivergent users and the impact on comprehension or navigation>",
      "wcag": "<WCAG criterion e.g. 3.1.5>",
      "iso": "<ISO 9241-11 quality e.g. Effectiveness>"
    }}
  ],
  "adaptations": [
    {{
      "category": "<Language|Layout|Motion|Navigation|Hierarchy>",
      "title": "<actionable title>",
      "suggestion": "<specific, concrete suggestion — what to do and how>",
      "tradeoff": "<honest note on what simplifying this might cost in expressiveness or functionality, or null if no real tradeoff>"
    }}
  ],
  "summary": "<4-5 sentence narrative summary of the page's overall cognitive accessibility profile, explicitly referencing ISO 9241-11 effectiveness, efficiency and satisfaction, and mentioning specific user groups likely to be impacted>"
}}

Scoring guide: 100 = fully accessible, 0 = severe barrier.
Generate at least 5 findings and 5 adaptations. Be specific, nuanced, and reference real WCAG 2.2 Cognitive Accessibility guidance criteria.
If you cannot directly fetch the URL, reason from known characteristics of the site."""


def run_analysis(url: str, api_key: str) -> dict | None:
    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": build_prompt(url)}],
        )
        raw = message.content[0].text
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except json.JSONDecodeError as e:
        st.error(f"Could not parse analysis JSON: {e}\n\nRaw response:\n{raw[:500]}")
        return None
    except anthropic.AuthenticationError:
        st.error("Invalid API key. Please check your Anthropic API key in the sidebar.")
        return None
    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


# ── Plotly charts ────────────────────────────────────────────────────────────
def radar_chart(scores: dict) -> go.Figure:
    labels = [d["label"] for d in DIMENSIONS]
    values = [scores.get(d["key"], 0) for d in DIMENSIONS]
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed, theta=labels_closed,
        fill="toself", name="Score",
        fillcolor="rgba(83,74,183,0.15)",
        line=dict(color="#534AB7", width=2),
        marker=dict(size=6, color="#534AB7"),
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10)),
            angularaxis=dict(tickfont=dict(size=12)),
        ),
        showlegend=False,
        margin=dict(t=20, b=20, l=40, r=40),
        height=340,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def bar_chart(scores: dict) -> go.Figure:
    labels = [d["label"] for d in DIMENSIONS]
    values = [scores.get(d["key"], 0) for d in DIMENSIONS]
    colors = [score_colour(v) for v in values]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors,
        text=[f"{v}/100" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        xaxis=dict(range=[0, 110], showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(autorange="reversed"),
        margin=dict(t=10, b=10, l=10, r=60),
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def gauge_chart(score: int) -> go.Figure:
    colour = score_colour(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "/100", "font": {"size": 32, "color": colour}},
        gauge=dict(
            axis=dict(range=[0, 100], tickfont=dict(size=11)),
            bar=dict(color=colour, thickness=0.25),
            bgcolor="white",
            borderwidth=0,
            steps=[
                dict(range=[0, 50],  color="#fff0f0"),
                dict(range=[50, 75], color="#fffbf0"),
                dict(range=[75, 100],color="#f0faf6"),
            ],
            threshold=dict(line=dict(color=colour, width=3), thickness=0.75, value=score),
        ),
    ))
    fig.update_layout(
        height=220,
        margin=dict(t=20, b=10, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def nasa_gauge(avg: int) -> go.Figure:
    colour, _ = nasa_interpret(avg)
    # Invert: lower TLX = better accessibility
    acc_score = 100 - avg
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=avg,
        title={"text": "TLX Composite", "font": {"size": 14}},
        delta={"reference": 50, "decreasing": {"color": "#1d9e75"}, "increasing": {"color": "#e24b4a"}},
        number={"font": {"size": 36, "color": colour}},
        gauge=dict(
            axis=dict(range=[0, 100]),
            bar=dict(color=colour, thickness=0.3),
            steps=[
                dict(range=[0, 25],  color="#f0faf6"),
                dict(range=[25, 50], color="#fffbf0"),
                dict(range=[50, 75], color="#fff5f0"),
                dict(range=[75, 100],color="#fff0f0"),
            ],
        ),
    ))
    fig.update_layout(height=240, margin=dict(t=40, b=10, l=30, r=30), paper_bgcolor="rgba(0,0,0,0)")
    return fig


# ── Export helpers ────────────────────────────────────────────────────────────
def build_report_markdown(url: str, data: dict, nasa_scores: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    overall = round(sum(data["scores"].values()) / len(data["scores"]))
    lines = [
        f"# Cognitive Accessibility Report",
        f"**URL:** {url}  ",
        f"**Generated:** {now}  ",
        f"**Overall Score:** {overall}/100  ",
        "",
        "## Summary",
        data.get("summary", ""),
        "",
        "## Dimension Scores",
        "| Dimension | Score | WCAG | ISO 9241-11 |",
        "|-----------|-------|------|-------------|",
    ]
    for d in DIMENSIONS:
        s = data["scores"].get(d["key"], 0)
        lines.append(f"| {d['label']} | {s}/100 | {d['wcag']} | {d['iso']} |")

    lines += ["", "## Findings", ""]
    for f in data.get("findings", []):
        lines += [
            f"### [{f['severity']}] {f['title']}",
            f"**Dimension:** {f['dimension']} | **WCAG:** {f['wcag']} | **ISO 9241-11:** {f['iso']}  ",
            f"{f['explanation']}",
            "",
        ]

    lines += ["## Adaptations", ""]
    for a in data.get("adaptations", []):
        icon = DIM_ICONS.get(a["category"], "🔧")
        lines += [
            f"### {icon} {a['title']}",
            f"**Category:** {a['category']}  ",
            a["suggestion"],
        ]
        if a.get("tradeoff"):
            lines.append(f"\n> ⚖️ **Trade-off:** {a['tradeoff']}")
        lines.append("")

    if nasa_scores:
        avg = round(sum(nasa_scores.values()) / len(nasa_scores))
        _, interp = nasa_interpret(avg)
        lines += [
            "## NASA-TLX Evaluation",
            f"**Composite TLX Score:** {avg}/100  ",
            f"**Interpretation:** {interp}",
            "",
            "| Subscale | Score |",
            "|----------|-------|",
        ]
        for d in NASA_DIMS:
            lines.append(f"| {d['label']} | {nasa_scores.get(d['key'], 50)}/100 |")

    return "\n".join(lines)


# ── Session state init ───────────────────────────────────────────────────────
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "url" not in st.session_state:
    st.session_state.url = ""
if "nasa_scores" not in st.session_state:
    st.session_state.nasa_scores = {d["key"]: 50 for d in NASA_DIMS}


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 CogAccess")
    st.caption("Cognitive Accessibility Assistant")
    st.divider()

    api_key = st.text_input(
        "Anthropic API key",
        type="password",
        placeholder="sk-ant-...",
        help="Your key is used only for this session and never stored.",
    )

    st.divider()
    st.markdown("**About this tool**")
    st.caption(
        "Analyses web pages for cognitive accessibility barriers across five dimensions, "
        "maps findings to WCAG 2.2 Cognitive Accessibility Guidance and ISO 9241-11 "
        "(effectiveness, efficiency, satisfaction), and supports NASA-TLX cognitive load measurement."
    )
    st.divider()

    st.markdown("**Frameworks referenced**")
    st.caption("• WCAG 2.2 — Success Criteria 1.3.1, 1.4.8, 2.2.2, 3.1.5, 3.2.3")
    st.caption("• ISO 9241-11 — Usability: effectiveness, efficiency, satisfaction")
    st.caption("• NASA-TLX — Cognitive load subscale measurement")

    if st.session_state.analysis and st.session_state.url:
        st.divider()
        report_md = build_report_markdown(
            st.session_state.url,
            st.session_state.analysis,
            st.session_state.nasa_scores,
        )
        st.download_button(
            label="⬇️ Download report (.md)",
            data=report_md,
            file_name=f"cogaccess_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )


# ── Header ───────────────────────────────────────────────────────────────────
st.title("🧠 Cognitive Accessibility Assistant")
st.caption(
    "Enter any URL to analyse cognitive accessibility barriers — language complexity, "
    "layout density, visual hierarchy, animation usage, and navigation consistency."
)

# ── URL input ─────────────────────────────────────────────────────────────────
col_url, col_btn = st.columns([5, 1])
with col_url:
    url_input = st.text_input(
        "URL to analyse",
        placeholder="https://www.example.gov",
        label_visibility="collapsed",
    )
with col_btn:
    analyse_clicked = st.button("Analyse", type="primary", use_container_width=True)

if analyse_clicked:
    if not url_input:
        st.warning("Please enter a URL.")
    elif not api_key:
        st.warning("Please enter your Anthropic API key in the sidebar.")
    else:
        with st.spinner("Analysing cognitive accessibility…"):
            result = run_analysis(url_input, api_key)
        if result:
            st.session_state.analysis = result
            st.session_state.url = url_input
            st.success("Analysis complete!")

# ── Main content ──────────────────────────────────────────────────────────────
if st.session_state.analysis is None:
    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("**📊 Five dimensions**\n\nLanguage complexity, layout density, visual hierarchy, animation usage, and navigation consistency — all mapped to WCAG and ISO 9241-11.")
    with c2:
        st.info("**🔍 Detailed findings**\n\nEvery finding includes severity, a neurodivergent-specific explanation, and dual WCAG/ISO citations.")
    with c3:
        st.info("**🎛️ NASA-TLX evaluation**\n\nMeasure cognitive load with the NASA Task Load Index — six subscales matched to ISO 9241-11 usability qualities.")
    st.stop()

data = st.session_state.analysis
scores = data.get("scores", {})
findings = data.get("findings", [])
adaptations = data.get("adaptations", [])
summary = data.get("summary", "")
overall = round(sum(scores.values()) / max(len(scores), 1))

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_dash, tab_findings, tab_adapt, tab_nasa = st.tabs(
    ["📊 Dashboard", "🔍 Findings", "💡 Adaptations", "🎛️ NASA-TLX Evaluation"]
)

# ── TAB 1: Dashboard ──────────────────────────────────────────────────────────
with tab_dash:
    if summary:
        st.markdown(f'<div class="summary-box"><strong>Summary</strong><br><br>{summary}</div>', unsafe_allow_html=True)

    # Overall score + gauge
    g_col, m_col = st.columns([1, 2])
    with g_col:
        st.plotly_chart(gauge_chart(overall), use_container_width=True, config={"displayModeBar": False})
        st.markdown(f"<div style='text-align:center;font-size:14px;color:#555'>{score_label(overall)}</div>", unsafe_allow_html=True)
    with m_col:
        st.markdown("**Dimension scores**")
        st.plotly_chart(bar_chart(scores), use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # Individual metric cards
    cols = st.columns(5)
    for i, dim in enumerate(DIMENSIONS):
        s = scores.get(dim["key"], 0)
        colour = score_colour(s)
        with cols[i]:
            st.metric(label=dim["label"], value=f"{s}/100", delta=None)
            st.caption(f"WCAG {dim['wcag']} · ISO {dim['iso']}")

    st.divider()

    # Radar chart
    st.markdown("**Accessibility profile radar**")
    st.plotly_chart(radar_chart(scores), use_container_width=True, config={"displayModeBar": False})


# ── TAB 2: Findings ───────────────────────────────────────────────────────────
with tab_findings:
    if not findings:
        st.info("No findings in this analysis.")
    else:
        # Filter controls
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            sev_filter = st.multiselect(
                "Severity", ["High", "Medium", "Low"],
                default=["High", "Medium", "Low"],
            )
        with f_col2:
            dim_filter = st.multiselect(
                "Dimension",
                list({f["dimension"] for f in findings}),
                default=list({f["dimension"] for f in findings}),
            )

        filtered = [
            f for f in findings
            if f.get("severity") in sev_filter and f.get("dimension") in dim_filter
        ]

        st.caption(f"Showing {len(filtered)} of {len(findings)} findings")
        st.divider()

        # Severity summary
        high = sum(1 for f in findings if f.get("severity") == "High")
        med  = sum(1 for f in findings if f.get("severity") == "Medium")
        low  = sum(1 for f in findings if f.get("severity") == "Low")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("🔴 High severity",   high)
        sc2.metric("⚠️ Medium severity",  med)
        sc3.metric("✅ Low severity",     low)
        st.divider()

        for finding in filtered:
            sev = finding.get("severity", "Low")
            css = severity_class(sev)
            dim_tag = finding.get("dimension", "")
            wcag_tag = finding.get("wcag", "")
            iso_tag  = finding.get("iso", "")

            st.markdown(f"""
<div class="{css}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:.5rem">
    <strong style="font-size:15px">{finding.get('title','')}</strong>
    <span style="margin-left:auto;font-size:12px;font-weight:600;
      color:{'#a32d2d' if sev=='High' else '#854f0b' if sev=='Medium' else '#0f6e56'}">{sev}</span>
  </div>
  <p style="font-size:13px;color:#444;margin:.4rem 0 .8rem;line-height:1.7">{finding.get('explanation','')}</p>
  <div style="display:flex;gap:6px;flex-wrap:wrap">
    <span class="tag-wcag">WCAG {wcag_tag}</span>
    <span class="tag-iso">ISO 9241-11 · {iso_tag}</span>
    <span class="tag-dim">{dim_tag}</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ── TAB 3: Adaptations ────────────────────────────────────────────────────────
with tab_adapt:
    if not adaptations:
        st.info("No adaptations in this analysis.")
    else:
        cat_filter = st.multiselect(
            "Category",
            list({a["category"] for a in adaptations}),
            default=list({a["category"] for a in adaptations}),
        )
        filtered_adapt = [a for a in adaptations if a.get("category") in cat_filter]
        st.caption(f"{len(filtered_adapt)} suggestions")
        st.divider()

        for adapt in filtered_adapt:
            icon = DIM_ICONS.get(adapt.get("category", ""), "🔧")
            tradeoff = adapt.get("tradeoff")
            tradeoff_html = ""
            if tradeoff:
                tradeoff_html = f'<div class="tradeoff">⚖️ <strong>Trade-off:</strong> {tradeoff}</div>'

            st.markdown(f"""
<div class="adapt-card">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:.5rem">
    <span style="font-size:20px">{icon}</span>
    <strong style="font-size:14px">{adapt.get('title','')}</strong>
    <span class="tag-dim" style="margin-left:auto">{adapt.get('category','')}</span>
  </div>
  <p style="font-size:13px;color:#444;line-height:1.7;margin:.3rem 0">{adapt.get('suggestion','')}</p>
  {tradeoff_html}
</div>
""", unsafe_allow_html=True)


# ── TAB 4: NASA-TLX ───────────────────────────────────────────────────────────
with tab_nasa:
    st.markdown("### NASA Task Load Index — Cognitive Load Evaluation")
    st.caption(
        "Rate the cognitive demands you experienced while interacting with the analysed page. "
        "These six subscales map directly to ISO 9241-11 effectiveness, efficiency, and satisfaction dimensions."
    )
    st.divider()

    iso_mapping = {
        "md": "ISO Efficiency",
        "pd": "ISO Efficiency",
        "td": "ISO Efficiency",
        "pe": "ISO Effectiveness",
        "ef": "ISO Efficiency",
        "fr": "ISO Satisfaction",
    }

    slider_cols = st.columns(2)
    for i, dim in enumerate(NASA_DIMS):
        col = slider_cols[i % 2]
        with col:
            val = st.slider(
                f"{dim['label']} · *{iso_mapping[dim['key']]}*",
                min_value=0, max_value=100, step=5,
                value=st.session_state.nasa_scores[dim["key"]],
                help=dim["desc"],
                key=f"nasa_{dim['key']}",
            )
            st.session_state.nasa_scores[dim["key"]] = val

    st.divider()

    avg = round(sum(st.session_state.nasa_scores.values()) / len(NASA_DIMS))
    colour, interp = nasa_interpret(avg)

    res_col, gauge_col = st.columns([2, 1])
    with res_col:
        st.markdown(f"""
<div class="nasa-score-display">
  <div class="nasa-big" style="color:{colour}">{avg}</div>
  <div class="nasa-sub">/ 100 &nbsp;·&nbsp; Weighted TLX composite</div>
  <div style="margin-top:.8rem;font-size:13px;color:#555;line-height:1.7">{interp}</div>
</div>
""", unsafe_allow_html=True)

    with gauge_col:
        st.plotly_chart(nasa_gauge(avg), use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # Subscale breakdown chart
    st.markdown("**Subscale breakdown**")
    nasa_labels = [d["label"] for d in NASA_DIMS]
    nasa_vals   = [st.session_state.nasa_scores[d["key"]] for d in NASA_DIMS]
    nasa_colors = [score_colour(100 - v) for v in nasa_vals]

    fig_nasa = go.Figure(go.Bar(
        x=nasa_vals, y=nasa_labels, orientation="h",
        marker_color=nasa_colors,
        text=[f"{v}" for v in nasa_vals],
        textposition="outside",
    ))
    fig_nasa.update_layout(
        xaxis=dict(range=[0, 115], showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(autorange="reversed"),
        margin=dict(t=10, b=10, l=10, r=50),
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_nasa, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # Compare with analysis scores
    if st.button("🔄 Cross-reference with page analysis scores"):
        st.markdown("**TLX subscales vs cognitive accessibility dimension scores**")
        st.caption(
            "NASA-TLX captures the user-side experience of cognitive load; "
            "the analysis scores capture the page-side accessibility profile. "
            "High TLX + low analysis scores = the tool correctly identified real barriers."
        )
        acc_overall = overall
        tlx_acc     = 100 - avg

        comparison_fig = go.Figure()
        comparison_fig.add_trace(go.Bar(
            name="Page accessibility (analysis)",
            x=["Overall"], y=[acc_overall],
            marker_color="#534AB7",
            text=[f"{acc_overall}"], textposition="outside",
        ))
        comparison_fig.add_trace(go.Bar(
            name="Perceived accessibility (100 − TLX)",
            x=["Overall"], y=[tlx_acc],
            marker_color="#1d9e75",
            text=[f"{tlx_acc}"], textposition="outside",
        ))
        comparison_fig.update_layout(
            barmode="group",
            height=280,
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(range=[0, 120]),
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(comparison_fig, use_container_width=True, config={"displayModeBar": False})

        gap = abs(acc_overall - tlx_acc)
        if gap <= 15:
            st.success(f"Good alignment (gap: {gap} pts) — the analysis scores closely match your lived experience of the page.")
        elif gap <= 30:
            st.warning(f"Moderate gap ({gap} pts) — some cognitive barriers may not be fully captured by automated analysis. Consider supplementing with user testing.")
        else:
            st.error(f"Large gap ({gap} pts) — significant divergence between analysis and lived experience. This may indicate barriers the automated analysis cannot detect (e.g. cultural familiarity, prior knowledge demands).")