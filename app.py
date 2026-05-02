"""
app.py — Streamlit frontend for the Healthcare NL to SQL Agent

Run from your project folder:
    streamlit run app.py

Make sure agent.py and cms_texas.db are in the same folder.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from agent import run_agent

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Healthcare Analytics Copilot",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .app-header {
        background: linear-gradient(135deg, #1a4f8a 0%, #2d7dd2 100%);
        padding: 2rem 2.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .app-title {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .app-subtitle {
        font-size: 0.95rem;
        opacity: 0.85;
        margin-top: 0.3rem;
    }
    .narrative-box {
        background: #ffffff;
        border-left: 4px solid #2d7dd2;
        padding: 1.2rem 1.5rem;
        border-radius: 0 10px 10px 0;
        margin: 1rem 0;
        font-size: 1rem;
        line-height: 1.75;
        color: #1e293b;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .sql-box {
        background: #1e293b;
        color: #e2e8f0;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        white-space: pre-wrap;
        line-height: 1.6;
    }
    .sidebar-title {
        font-size: 0.8rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.5rem;
    }
    .stButton > button {
        width: 100%;
        text-align: left;
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.5rem 0.8rem;
        font-size: 0.82rem;
        color: #334155;
        margin-bottom: 4px;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background: #f0f7ff;
        border-color: #2d7dd2;
        color: #1a4f8a;
    }
    hr { border-color: #e2e8f0; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

if "history" not in st.session_state:
    st.session_state.history = []

if "current_question" not in st.session_state:
    st.session_state.current_question = ""

# ── Column hint lists ─────────────────────────────────────────────────────────

DATE_HINTS  = ["date", "month", "year", "quarter", "week", "period", "time"]
MONEY_HINTS = ["leakage", "billed", "chrg", "revenue", "total", "pymt",
               "paid", "amt", "charge"]
RATE_HINTS  = ["rate", "pct", "percent", "avg", "average"]
DESC_HINTS  = ["desc", "name", "type", "city", "spec", "prvdr", "zip"]


# ── Smart chart type detector ─────────────────────────────────────────────────

def detect_chart_type(df: pd.DataFrame, label_col: str, value_col: str) -> str:
    """
    Determine best chart type from actual data characteristics.
    """
    label_lower = label_col.lower()
    value_lower = value_col.lower()

    # Rule 1 — time series by column name
    if any(hint in label_lower for hint in DATE_HINTS):
        return "line"

    # Rule 1b — time series by parsing values as dates
    try:
        parsed = pd.to_datetime(df[label_col], errors="coerce")
        if parsed.notna().sum() > len(df) * 0.7:
            return "line"
    except Exception:
        pass

    # Rule 2 — never use pie for rate/percentage columns
    # Rates don't add up to 100% so pie chart is misleading
    if any(hint in value_lower for hint in RATE_HINTS):
        return "bar"

    # Rule 3 — part of whole only for true proportions
    if df[label_col].nunique() <= 6:
        return "pie"

    # Rule 4 — default
    return "bar"

# ── Best column picker ────────────────────────────────────────────────────────

def pick_best_columns(df: pd.DataFrame, all_cols: list) -> tuple:
    """
    Pick one label column and one value column for charting.
    Never plots multiple numeric series on the same chart.
    """
    text_cols = [
        c for c in all_cols
        if not pd.api.types.is_numeric_dtype(df[c])
    ]
    numeric_cols = [
        c for c in all_cols
        if pd.api.types.is_numeric_dtype(df[c])
    ]

    # Best label — prefer human-readable description columns
    label_col = next(
        (c for c in text_cols
         if any(h in c.lower() for h in DESC_HINTS)),
        text_cols[0] if text_cols else all_cols[0]
    )

    # Check if ALL numeric columns are rate/percentage columns
    all_rates = all(
        any(h in c.lower() for h in RATE_HINTS)
        for c in numeric_cols
    )

    # Check if any numeric column is explicitly a rate
    has_rate_col = any(
        any(h in c.lower() for h in RATE_HINTS)
        for c in numeric_cols
    )

    # Check if any numeric column is explicitly money
    has_money_col = any(
        any(h in c.lower() for h in MONEY_HINTS)
        for c in numeric_cols
    )

    if all_rates or (has_rate_col and not has_money_col):
        # Only rate columns exist — use the first rate column
        value_col = next(
            (c for c in numeric_cols
             if any(h in c.lower() for h in RATE_HINTS)),
            numeric_cols[0] if numeric_cols else all_cols[1]
        )

    elif has_rate_col and has_money_col:
        # Both exist — decide based on row count
        # 2 rows = binary comparison → prefer rate
        # More rows = ranking → prefer money
        if df[label_col].nunique() <= 2:
            value_col = next(
                (c for c in numeric_cols
                 if any(h in c.lower() for h in RATE_HINTS)),
                numeric_cols[0] if numeric_cols else all_cols[1]
            )
        else:
            # Check column order — if rate comes before money, use rate
            # This respects what Claude put first in the SELECT
            first_rate_idx = next(
                (i for i, c in enumerate(numeric_cols)
                 if any(h in c.lower() for h in RATE_HINTS)),
                999
            )
            first_money_idx = next(
                (i for i, c in enumerate(numeric_cols)
                 if any(h in c.lower() for h in MONEY_HINTS)),
                999
            )
            if first_rate_idx < first_money_idx:
                value_col = numeric_cols[first_rate_idx]
            else:
                value_col = numeric_cols[first_money_idx]

    else:
        # No rate columns — use first money column
        value_col = next(
            (c for c in numeric_cols
             if any(h in c.lower() for h in MONEY_HINTS)),
            numeric_cols[0] if numeric_cols else all_cols[1]
        )

    return label_col, value_col


# ── Number formatter ──────────────────────────────────────────────────────────

def format_dollar(val: float) -> str:
    """Format a number as $XB, $XM, $XK — never uses G."""
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.1f}B"
    elif val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    elif val >= 1_000:
        return f"${val / 1_000:.1f}K"
    else:
        return f"${val:.0f}"


def make_ticks(max_val: float) -> tuple:
    """
    Generate custom tick values and labels for money axes.
    Always uses B/M/K — never G.
    Returns (tick_vals, tick_text) or (None, None) if not needed.
    """
    if max_val <= 0:
        return None, None

    if max_val >= 1_000_000_000:
        raw_step  = max_val / 5
        step      = max(round(raw_step / 500_000_000) * 500_000_000, 500_000_000)
        tick_vals = list(range(0, int(max_val * 1.2), int(step)))
        tick_text = [format_dollar(v) for v in tick_vals]
        return tick_vals, tick_text

    elif max_val >= 1_000_000:
        raw_step  = max_val / 5
        step      = max(round(raw_step / 100_000_000) * 100_000_000, 50_000_000)
        tick_vals = list(range(0, int(max_val * 1.2), int(step)))
        tick_text = [format_dollar(v) for v in tick_vals]
        return tick_vals, tick_text

    return None, None


# ── Chart builder ─────────────────────────────────────────────────────────────

def build_chart(
    chart_df  : pd.DataFrame,
    label_col : str,    
    value_col : str,
    chart_type: str
):
    """Build and return a Plotly figure."""
    val_lower   = value_col.lower()
    is_money    = any(h in val_lower for h in MONEY_HINTS)
    is_rate     = any(h in val_lower for h in RATE_HINTS)
    value_label = value_col.replace("_", " ").title()
    label_label = label_col.replace("_", " ").title()

    # ── Line chart ────────────────────────────────────────────────
    if chart_type == "line":
        fig = px.line(
            chart_df,
            x=label_col,
            y=value_col,
            markers=True,
            color_discrete_sequence=["#2d7dd2"],
            labels={value_col: value_label, label_col: label_label}
        )
        if is_money:
            tick_vals, tick_text = make_ticks(chart_df[value_col].max())
            if tick_vals:
                fig.update_yaxes(tickvals=tick_vals, ticktext=tick_text)
        elif is_rate:
            fig.update_yaxes(ticksuffix="%")

    # ── Pie chart ─────────────────────────────────────────────────
    elif chart_type == "pie":
        fig = px.pie(
            chart_df,
            names=label_col,
            values=value_col,
            color_discrete_sequence=px.colors.qualitative.Set2,
            labels={value_col: value_label}
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label"
        )

    # ── Horizontal bar chart (default) ────────────────────────────
    else:
        # Sort ascending so largest bar appears at top
        chart_df = chart_df.sort_values(
            by=value_col, ascending=True
        ).reset_index(drop=True)

        # Add formatted value labels for end of each bar
        if is_money:
            chart_df["bar_label"] = chart_df[value_col].apply(format_dollar)
        elif is_rate:
            chart_df["bar_label"] = chart_df[value_col].apply(
                lambda v: f"{v:.1f}%"
            )
        else:
            chart_df["bar_label"] = chart_df[value_col].apply(
                lambda v: f"{v:,.1f}"
            )

        fig = px.bar(
            chart_df,
            x=value_col,
            y=label_col,
            orientation="h",
            color_discrete_sequence=["#2d7dd2"],
            text="bar_label",
            labels={value_col: value_label, label_col: label_label}
        )

        fig.update_traces(
            textposition="outside",
            textfont=dict(size=11, color="#1e293b"),
            cliponaxis=False,
            width=0.55
        )

        # Apply custom money tick labels — B/M/K not G
        if is_money:
            tick_vals, tick_text = make_ticks(chart_df[value_col].max())
            if tick_vals:
                fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text)
        elif is_rate:
            fig.update_xaxes(ticksuffix="%")

    # ── Shared layout ─────────────────────────────────────────────
    fig.update_layout(
        margin        = dict(l=0, r=130, t=40, b=40),
        plot_bgcolor  = "white",
        paper_bgcolor = "white",
        font          = dict(size=12, color="#1e293b"),
        height        = 480,
        xaxis_title   = value_label,
        yaxis_title   = "",
        bargap        = 0.3,
        bargroupgap   = 0.0,
    )

    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🏥 Healthcare Analytics Copilot")
    st.markdown(
        "Ask any question about **Texas Medicare billing data (2023)** "
        "in plain English. The AI agent converts your question into SQL, "
        "queries 671,400 provider records, and generates an executive insight."
    )

    st.divider()

    st.markdown(
        '<div class="sidebar-title">Example Questions</div>',
        unsafe_allow_html=True
    )
    st.markdown("*Click any question to run it instantly*")

    examples = [
        "Which specialties have the worst reimbursement rates in Texas?",
        "Top 10 Houston providers by total revenue leakage",
        "Compare reimbursement rates between facility and office settings",
        "Which cities in Texas have the highest average revenue leakage?",
        "Top 10 Cardiology providers in Texas by total billed amount",
        "What is the average reimbursement rate for Diagnostic Radiology?",
    ]

    for q in examples:
        if st.button(q, key=f"ex_{q[:30]}"):
            st.session_state.current_question = q
            st.session_state.run_now = True

    st.divider()

    st.markdown(
        '<div class="sidebar-title">About the Data</div>',
        unsafe_allow_html=True
    )
    st.markdown("""
    - **Source:** CMS Medicare 2023
    - **Scope:** Texas providers only
    - **Rows:** 671,400 records
    - **AI Model:** Claude Sonnet 4.6
    """)

    show_sql  = st.toggle("Show generated SQL",  value=True)
    show_data = st.toggle("Show raw data table", value=False)


# ── Main header ───────────────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
    <div class="app-title">🏥 Healthcare Analytics Copilot</div>
    <div class="app-subtitle">
        Querying Texas Medicare Billing Data (CMS 2023) with Plain English
        — Powered by Claude AI
    </div>
</div>
""", unsafe_allow_html=True)

# ── Question input ────────────────────────────────────────────────────────────

col1, col2 = st.columns([5, 1])

with col1:
    user_question = st.text_input(
        "Ask a question",
        value=st.session_state.current_question,
        placeholder="e.g. Which specialties have the worst reimbursement rates in Texas?",
        label_visibility="collapsed",
        key="question_input"
    )

with col2:
    run_btn = st.button("Analyze →", type="primary", use_container_width=True)

# ── Run logic ─────────────────────────────────────────────────────────────────

should_run = run_btn or st.session_state.get("run_now", False)

if st.session_state.get("run_now", False):
    st.session_state.run_now = False
    active_question = st.session_state.current_question
else:
    active_question = user_question
    if run_btn:
        st.session_state.current_question = user_question

if should_run and active_question.strip():
    with st.spinner("Generating SQL and querying database..."):
        try:
            result = run_agent(active_question.strip())
            st.session_state.history.insert(0, result)
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.stop()

# ── Empty state ───────────────────────────────────────────────────────────────

if not st.session_state.history:
    st.info(
        "👈 Click an example question in the sidebar "
        "or type your own above to get started."
    )

# ── Display results ───────────────────────────────────────────────────────────

for idx, result in enumerate(st.session_state.history[:3]):
    is_latest = (idx == 0)

    if not is_latest:
        st.divider()
        st.caption(f"Previous query: {result['question']}")

    # ── AI Narrative ──────────────────────────────────────────────
    st.markdown(
        f'<div class="narrative-box">💡 {result["narrative"]}</div>',
        unsafe_allow_html=True
    )

    # ── Smart Chart ───────────────────────────────────────────────
    if result["rows"] and len(result["columns"]) >= 2:
        try:
            df = pd.DataFrame(result["rows"], columns=result["columns"])

            # ── Step 1: Classify each column BEFORE any conversion ────
            ZIP_ID_HINTS     = ["zip", "npi", "cd", "code", "id"]
            protected_cols   = []
            convertible_cols = []

            for col in result["columns"]:
                col_lower = col.lower()
                if any(hint in col_lower for hint in ZIP_ID_HINTS):
                    protected_cols.append(col)
                else:
                    convertible_cols.append(col)

            # ── Step 2: Convert numeric columns (skip protected) ──────
            for col in convertible_cols:
                converted = pd.to_numeric(df[col], errors="coerce")
                if converted.notna().sum() > len(df) * 0.5:
                    df[col] = converted

            # ── Step 3: Clean protected columns as strings ────────────
            for col in protected_cols:
                col_lower = col.lower()
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].str.replace(r"\.0$", "", regex=True)
                if "zip" in col_lower:
                    df[col] = df[col].str.zfill(5)

            # ── Step 4: Pick best label and value columns ─────────────
            label_col, value_col = pick_best_columns(df, result["columns"])

            # ── Step 5: Build chart dataframe ─────────────────────────
            chart_df = df[[label_col, value_col]].copy()
            chart_df = chart_df.dropna(subset=[value_col])

            # Aggregate duplicates
            if pd.api.types.is_numeric_dtype(chart_df[value_col]):
                chart_df = (
                    chart_df
                    .groupby(label_col, as_index=False)[value_col]
                    .sum()
                )

            # Sort descending and take top 10
            chart_df = (
                chart_df
                .sort_values(by=value_col, ascending=False)
                .head(10)
                .reset_index(drop=True)
            )

            # Truncate long labels
            chart_df[label_col] = (
                chart_df[label_col].astype(str).str[:45]
            )

            # ── Step 6: Detect chart type and build ───────────────────
            chart_type = detect_chart_type(chart_df, label_col, value_col)
            fig        = build_chart(chart_df, label_col, value_col, chart_type)

            if fig:
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.warning(f"Chart could not be rendered: {e}")

    # ── SQL expander ──────────────────────────────────────────────
    if show_sql:
        with st.expander("Generated SQL", expanded=is_latest):
            st.markdown(
                f'<div class="sql-box">{result["sql"]}</div>',
                unsafe_allow_html=True
            )
            st.caption(f"💬 {result['explanation']}")

    # ── Raw data table ────────────────────────────────────────────
    if show_data:
        with st.expander("Raw data table"):
            raw_df = pd.DataFrame(
                result["rows"], columns=result["columns"]
            )
            st.dataframe(raw_df, use_container_width=True)