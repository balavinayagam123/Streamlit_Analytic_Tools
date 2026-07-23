import io
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="PMS Jobs Reporting & Verification Effort",
    page_icon="🧭",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* KPI cards — full-width labels, wrapping, no ellipsis truncation */
    [data-testid="stMetric"] { padding: 0.25rem 0.25rem; }
    [data-testid="stMetricLabel"] { white-space: normal !important; }
    [data-testid="stMetricLabel"] p {
        white-space: normal !important;
        font-size: 0.82rem;
        line-height: 1.2;
        font-weight: 600;
        color: #52514e;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.55rem;
        line-height: 1.15;
    }
    [data-testid="stMetricValue"] div,
    [data-testid="stMetricValue"] p {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        overflow-wrap: anywhere;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧭 PMS Jobs Reporting & Verification Effort Dashboard")
st.markdown(
    "Upload a JiBe (or similar) PMS job export to see how many job reports "
    "each rank must submit — and each supervisor must verify — over a selected "
    "period, based on job frequency."
)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

PERIODS = {"1 Week": 7, "1 Month": 30, "3 Months": 90, "6 Months": 180}
FREQ_RE = re.compile(r"^\s*([\d.]+)\s+(Days|Months|Hours)\s*$", re.IGNORECASE)
UNIT_ORDER = {"Days": 0, "Months": 1, "Hours": 2}

BLUE = "#2a78d6"
AQUA = "#1baf7a"
PASTEL_CRITICAL = "#f5b0a8"      # soft coral — critical jobs
PASTEL_NONCRIT = "#a9cce8"       # soft blue — non-critical jobs

# Distinct per-rank colours for the effort-by-period chart
RANK_PALETTE = [
    "#2a78d6", "#1baf7a", "#eda100", "#e34948", "#9085e9",
    "#e87ba4", "#eb6834", "#009aa6", "#6b7280", "#b5179e",
]

# Short-cycle frequency bands (short → long) with upper bound in days, blue ramp
FREQ_BANDS = [
    ("≤ 7 Days", 7),
    ("8 Days – 1 Month", 30),
    ("1 – 3 Months", 90),
    ("3 – 6 Months", 180),
    ("6 – 12 Months", 360),
    ("> 12 Months", float("inf")),
]
BAND_COLORS = {
    "≤ 7 Days": "#1c4e80",
    "8 Days – 1 Month": "#2a78d6",
    "1 – 3 Months": "#5598e7",
    "3 – 6 Months": "#9ec5f4",
    "6 – 12 Months": "#d4e6f9",
    "> 12 Months": "#eef3fa",
}
FREQ_THRESHOLDS = {
    "≤ 7 Days": 7, "≤ 1 Month": 30, "≤ 3 Months": 90,
    "≤ 6 Months": 180, "≤ 12 Months": 360, "All frequencies": float("inf"),
}


def band_of(days):
    for name, hi in FREQ_BANDS:
        if days <= hi:
            return name
    return FREQ_BANDS[-1][0]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_file(uploaded_file):
    raw = uploaded_file.read()
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(raw), dtype=str)
    else:
        df = pd.read_csv(io.BytesIO(raw), dtype=str)

    cols = df.columns.tolist()
    if len(cols) > 1 and str(cols[1]).startswith("Unnamed"):
        cols[1] = "Critical"
    df.columns = cols
    df = df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")], errors="ignore")

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()
    return df


def parse_frequency(freq):
    if pd.isna(freq):
        return np.nan, None, np.nan
    m = FREQ_RE.match(str(freq).strip())
    if not m:
        return np.nan, None, np.nan
    value = float(m.group(1))
    unit = m.group(2).capitalize()
    days = value if unit == "Days" else (value * 30 if unit == "Months" else np.nan)
    return value, unit, days


def freq_sort_key(label):
    value, unit, _ = parse_frequency(label)
    return (UNIT_ORDER.get(unit, 9), value if not np.isnan(value) else 0)


def primary_rank(df):
    df = df.copy()
    df["Performing Rank"] = df["Performing Rank"].fillna("Unassigned").astype(str).str.strip()
    # Jobs list alternate/backup ranks after the first comma (e.g.
    # "2nd Engineer,3rd Engineer,4th Engineer (Senior)") — only the first-listed
    # rank is the one normally accountable for reporting the job.
    df["Rank"] = df["Performing Rank"].str.split(",").str[0].str.strip()
    return df


def clean_opts(series):
    return sorted({str(v).strip() for v in series.dropna() if str(v).strip() not in ("", "nan")})


def verifier_of(rank):
    """Who signs off the job report done by this rank.
    Chief Engineer verifies all engine-side ranks (engineers + electrical),
    including his own jobs. Master verifies the deck watch officers plus his own.
    """
    r = str(rank).lower()
    if "electr" in r:                    # electrical officer/electrician/electro-technical
        return "Chief Engineer"
    if "engineer" in r:                  # 2nd/3rd/4th/junior/chief engineers (self-verified)
        return "Chief Engineer"
    if rank in ("Master", "Chief Officer", "2nd Officer", "3rd Officer"):
        return "Master"
    return None


def to_excel(dfs: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, d in dfs.items():
            d.to_excel(writer, sheet_name=sheet_name[:31])
    return buf.getvalue()


# Blue sequential scale: light (low) -> dark (high)
HEAT_LIGHT, HEAT_DARK = (234, 243, 251), (33, 102, 172)   # #eaf3fb -> #2166ac


def _mix(c1, c2, t):
    return tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def heat_color(v, vmin, vmax):
    t = 0.0 if vmax == vmin else (v - vmin) / (vmax - vmin)
    rgb = _mix(HEAT_LIGHT, HEAT_DARK, t)
    text = "#ffffff" if t > 0.55 else "#0b0b0b"    # keep contrast on dark cells
    return f"background-color: rgb{rgb}; color: {text}"


def heatmap_column(col):
    return [heat_color(v, col.min(), col.max()) for v in col]


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 Upload PMS Export")
    uploaded_file = st.file_uploader("JiBe export (CSV or Excel)", type=["csv", "xlsx", "xls"])

    st.divider()
    st.header("⏱ Reporting Period")
    period_label = st.radio("Show effort for the next:", list(PERIODS.keys()), index=1)
    period_days = PERIODS[period_label]

    st.divider()
    st.header("⚙ Options")
    st.caption(
        "For jobs assignable to more than one rank (e.g. "
        "'2nd Engineer,3rd Engineer,4th Engineer (Senior)'), only the "
        "first-listed rank is used — the rest are treated as backups and ignored."
    )

    with st.expander("Running-hour based jobs"):
        st.caption(
            "Jobs due by running hours (e.g. '8000 Hours') can't be placed on a calendar without "
            "knowing how fast the machinery actually runs. They're excluded from the period effort "
            "by default."
        )
        include_hours = st.checkbox("Include an estimate for running-hour jobs", value=False)
        avg_hours_per_day = st.slider(
            "Assumed average running hours / day", min_value=1, max_value=24, value=24,
            disabled=not include_hours,
        )
        hours_threshold = st.number_input(
            "Matrix: include running-hour jobs due within (hours)", min_value=0, value=500, step=50,
            disabled=not include_hours,
        )

if uploaded_file is None:
    st.info("👈 Upload a PMS job export (CSV or Excel) in the sidebar to get started.")
    with st.expander("ℹ️ How to export from JiBe"):
        st.markdown(
            """
1. Go to **Planned Maintenance → Jobs**
2. Filter by vessel, status = **Pending**
3. Click **Export to Excel**
4. Upload the resulting file here
            """
        )
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# LOAD & PREP
# ─────────────────────────────────────────────────────────────────────────────

df = load_file(uploaded_file)
required = ["Frequency", "Performing Rank"]
missing_cols = [c for c in required if c not in df.columns]
if missing_cols:
    st.error(f"Uploaded file is missing required column(s): {', '.join(missing_cols)}")
    st.stop()

freq_parsed = df["Frequency"].apply(parse_frequency)
df["Freq Value"] = freq_parsed.apply(lambda t: t[0])
df["Freq Unit"] = freq_parsed.apply(lambda t: t[1])
df["Freq Days"] = freq_parsed.apply(lambda t: t[2])
df["Is Time Based"] = df["Freq Unit"].isin(["Days", "Months"])
df = primary_rank(df)
rank_opts = clean_opts(df["Rank"])
rank_colors = {r: RANK_PALETTE[i % len(RANK_PALETTE)] for i, r in enumerate(rank_opts)}

with st.sidebar:
    st.divider()
    st.header("🧰 More Filters")
    mach_f = st.multiselect("Machinery Location", options=clean_opts(df.get("Machinery Location", pd.Series(dtype=str))))
    src_f = st.multiselect("Job Source", options=clean_opts(df.get("Job Source", pd.Series(dtype=str))))

# ─────────────────────────────────────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("🔧 Filter Jobs", expanded=False):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        dept_f = st.multiselect("Department", options=clean_opts(df.get("Department", pd.Series(dtype=str))))
    with fc2:
        fn_f = st.multiselect("Function", options=clean_opts(df.get("Function", pd.Series(dtype=str))))
    with fc3:
        status_f = st.multiselect("Job Status", options=clean_opts(df.get("Job Status", pd.Series(dtype=str))))
    with fc4:
        rank_f = st.multiselect("Rank(s) to include", options=rank_opts, default=rank_opts)
    crit_only = st.checkbox("Critical jobs only (C flag)")

df_f = df.copy()
if dept_f and "Department" in df_f.columns:
    df_f = df_f[df_f["Department"].isin(dept_f)]
if fn_f and "Function" in df_f.columns:
    df_f = df_f[df_f["Function"].isin(fn_f)]
if status_f and "Job Status" in df_f.columns:
    df_f = df_f[df_f["Job Status"].isin(status_f)]
if crit_only and "Critical" in df_f.columns:
    df_f = df_f[df_f["Critical"] == "C"]
if mach_f and "Machinery Location" in df_f.columns:
    df_f = df_f[df_f["Machinery Location"].isin(mach_f)]
if src_f and "Job Source" in df_f.columns:
    df_f = df_f[df_f["Job Source"].isin(src_f)]
if rank_f:
    df_f = df_f[df_f["Rank"].isin(rank_f)]

# ─────────────────────────────────────────────────────────────────────────────
# RANK EFFORT SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader(f"📊 Rank Reporting Effort — next {period_label}")

if df_f.empty:
    st.warning("No jobs match the current filters.")
    st.stop()

kpi_slots = st.columns(5)
chart_col, effort_col = st.columns([3, 2])

# Daily occurrence rate per job — occurrences per day (scales linearly with period)
df_f["Daily Rate"] = np.where(df_f["Is Time Based"], 1.0 / df_f["Freq Days"], 0.0)
if include_hours:
    hrs_mask = df_f["Freq Unit"] == "Hours"
    df_f.loc[hrs_mask, "Daily Rate"] = avg_hours_per_day / df_f.loc[hrs_mask, "Freq Value"]

# Expected occurrences within the selected period
df_f["Expected Occurrences"] = np.where(
    df_f["Is Time Based"], period_days / df_f["Freq Days"], np.nan
)
if include_hours:
    df_f.loc[hrs_mask, "Expected Occurrences"] = period_days * df_f.loc[hrs_mask, "Daily Rate"]

df_f["Due At Least Once"] = df_f["Expected Occurrences"].fillna(0) >= 1
df_f["Verifier"] = df_f["Rank"].map(verifier_of)

summary = (
    df_f.groupby("Rank")
    .agg(
        Total_Jobs=("Rank", "size"),
        Time_Based_Jobs=("Is Time Based", "sum"),
        Jobs_Due_At_Least_Once=("Due At Least Once", "sum"),
        Expected_Reports=("Expected Occurrences", "sum"),
    )
    .rename(
        columns={
            "Total_Jobs": "Total Jobs",
            "Time_Based_Jobs": "Time-Based Jobs",
            "Jobs_Due_At_Least_Once": f"Jobs Due ≥1x in {period_label}",
            "Expected_Reports": f"Est. Reports in {period_label}",
        }
    )
)
summary["Running-Hour Jobs"] = summary["Total Jobs"] - summary["Time-Based Jobs"]
summary = summary.sort_values(f"Est. Reports in {period_label}", ascending=False)
summary_display = summary.round(1)

# Verifying effort — reports a supervisor must sign off in the period
ce_verify = df_f.loc[df_f["Verifier"] == "Chief Engineer", "Expected Occurrences"].sum()
master_verify = df_f.loc[df_f["Verifier"] == "Master", "Expected Occurrences"].sum()
top_rank = summary.index[0] if len(summary) else "—"

kpis = [
    ("Ranks in scope", str(len(summary)),
     "Number of performing ranks after all filters."),
    ("Total est. reports",
     f"{summary['Est. Reports in ' + period_label].sum():,.0f}",
     f"Total estimated job reports across all ranks in the next {period_label}."),
    ("Highest-effort rank", top_rank,
     "Rank with the most estimated job reports in the period."),
    ("⚙ CE verifying effort", f"{ce_verify:,.0f}",
     "Estimated job reports the Chief Engineer must verify — all engineer and "
     "electrical ranks' jobs (including the Chief Engineer's own)."),
    ("🎖 Master verifying effort", f"{master_verify:,.0f}",
     "Estimated job reports the Master must verify — Master, Chief Officer, "
     "2nd Officer and 3rd Officer jobs."),
]
for slot, (label, value, help_txt) in zip(kpi_slots, kpis):
    with slot, st.container(border=True):
        st.metric(label, value, help=help_txt)

# Bar chart — critical vs non-critical job counts per rank (dual pastel, stacked)
if "Critical" in df_f.columns:
    df_f["_is_crit"] = df_f["Critical"].astype(str).str.strip() == "C"
else:
    df_f["_is_crit"] = False
counts = df_f.groupby("Rank")["_is_crit"].agg(Critical="sum", Total="size")
counts["Non-Critical"] = counts["Total"] - counts["Critical"]
counts = counts.reindex(summary.index[::-1])   # highest-effort rank on top

def seg_text(series):
    # only label a segment when it is wide enough to hold the number cleanly
    cutoff = max(counts["Total"].max() * 0.04, 1)
    return [f"{v:,.0f}" if v >= cutoff else "" for v in series]

fig = go.Figure()
fig.add_bar(
    y=counts.index, x=counts["Non-Critical"], name="Non-Critical", orientation="h",
    marker=dict(color=PASTEL_NONCRIT, line=dict(color="#ffffff", width=1)),
    text=seg_text(counts["Non-Critical"]), textposition="inside", insidetextanchor="middle",
    textfont=dict(color="#1b4a73", size=13),
    hovertemplate="%{y}<br>Non-Critical: %{x:,.0f}<extra></extra>",
)
fig.add_bar(
    y=counts.index, x=counts["Critical"], name="Critical", orientation="h",
    marker=dict(color=PASTEL_CRITICAL, line=dict(color="#ffffff", width=1)),
    text=[f"{v:,.0f}" if v > 0 else "" for v in counts["Critical"]],
    textposition="outside", textfont=dict(color="#b0413a", size=13), cliponaxis=False,
    hovertemplate="%{y}<br>Critical: %{x:,.0f}<extra></extra>",
)
fig.update_layout(
    barmode="stack",
    bargap=0.32,
    height=max(340, 44 * len(counts)),
    plot_bgcolor="#fcfcfb",
    paper_bgcolor="#fcfcfb",
    xaxis_title="Number of jobs",
    yaxis_title=None,
    font=dict(color="#0b0b0b", size=13),
    margin=dict(l=10, r=60, t=30, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title_text=""),
)
fig.update_xaxes(gridcolor="#eef1f5", zerolinecolor="#c3c2b7", showline=False)
fig.update_yaxes(showgrid=False, ticksuffix="  ")
with chart_col:
    st.markdown("**Jobs by rank — critical vs non-critical**")
    st.plotly_chart(fig, use_container_width=True)

# ── Short-cycle reporting load — reports by frequency band per period ─────
st.markdown("**Short-cycle reporting load** — reports by frequency band per period")
st.caption(
    "How many job reports the high-churn (short-frequency) items generate over each "
    "period. Calendar-frequency jobs only."
)
thr_label = st.radio(
    "Focus on jobs with frequency:", list(FREQ_THRESHOLDS.keys()),
    index=1, horizontal=True, key="short_cycle_threshold",
)
thr_days = FREQ_THRESHOLDS[thr_label]
sc_names = list(PERIODS.keys())
sc_days = list(PERIODS.values())

tb_all = df_f[df_f["Is Time Based"]].copy()
tb_all["Band"] = tb_all["Freq Days"].apply(band_of)
included_bands = [n for n, hi in FREQ_BANDS if hi <= thr_days] or [FREQ_BANDS[0][0]]
tb = tb_all[tb_all["Band"].isin(included_bands)]

if tb.empty:
    st.info("No calendar-frequency jobs match the current filters and threshold.")
else:
    rate_by_band = tb.groupby("Band")["Daily Rate"].sum()
    fig_sc = go.Figure()
    for name in included_bands:            # short at bottom of the stack
        r = rate_by_band.get(name, 0.0)
        fig_sc.add_bar(
            x=sc_names, y=[r * d for d in sc_days],
            name=name, marker_color=BAND_COLORS[name],
            hovertemplate=f"<b>{name}</b><br>%{{x}} · %{{y:,.0f}} reports<extra></extra>",
        )
    fig_sc.update_layout(
        barmode="stack", bargap=0.45,
        height=360, plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
        yaxis_title="Estimated job reports", xaxis_title=None,
        font=dict(color="#0b0b0b", size=13),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
    )
    fig_sc.update_xaxes(categoryorder="array", categoryarray=sc_names, showgrid=False)
    fig_sc.update_yaxes(gridcolor="#eef1f5", zerolinecolor="#c3c2b7")

    # Create matrix table for breakdown — all frequency bands (FULL WIDTH)
    sc_col, matrix_col = st.columns([1, 1])

    with sc_col:
        st.plotly_chart(fig_sc, use_container_width=True)

    with matrix_col:
        st.markdown("**Breakdown by Frequency Band**")
        matrix_data = {}
        # Base the breakdown on ALL jobs that feed the Reporting-effort table
        # (df_f), not just the calendar jobs. Running-hour jobs are counted in
        # the reporting effort when the sidebar option is enabled; if we left
        # them out here the two Grand Totals would never reconcile. They get
        # their own "Running Hours" row so the totals match exactly.
        bd = df_f.copy()
        bd["_Band"] = np.where(
            bd["Is Time Based"],
            bd["Freq Days"].apply(band_of),
            "Running Hours",
        )
        rate_by_band_all = bd.groupby("_Band")["Daily Rate"].sum()

        band_rows = [name for name, _ in FREQ_BANDS]
        if rate_by_band_all.get("Running Hours", 0.0) > 0:
            band_rows.append("Running Hours")

        # Keep the raw (unrounded) product so the Grand Total sums cleanly, then
        # round only at display time — same approach as the effort matrices.
        for band_name in band_rows:
            r = rate_by_band_all.get(band_name, 0.0)
            matrix_data[band_name] = {p: r * d for p, d in zip(sc_names, sc_days)}

        # Create DataFrame for the matrix
        sc_matrix = pd.DataFrame(matrix_data).T
        sc_matrix["Total"] = sc_matrix.sum(axis=1)
        sc_matrix.loc["Grand Total"] = sc_matrix.sum()

        # Style the matrix
        def style_sc_matrix(row):
            styles = []
            for col in row.index:
                if row.name == "Grand Total":
                    styles.append("background-color:#c6d9ec;font-weight:bold;text-align:right")
                else:
                    val = row[col]
                    styles.append("background-color:#e8f1f8;text-align:right" if col != "Total"
                                 else "background-color:#dce6f1;font-weight:bold;text-align:right")
            return styles

        styled_sc = sc_matrix.style.apply(style_sc_matrix, axis=1).format("{:,.0f}")
        st.dataframe(styled_sc, use_container_width=True, height=360)

    short_reports = tb["Daily Rate"].sum() * period_days
    total_reports = tb_all["Daily Rate"].sum() * period_days
    pct = (short_reports / total_reports * 100) if total_reports else 0
    st.caption(
        f"In the next **{period_label}**, jobs **{thr_label}** account for "
        f"**{short_reports:,.0f}** reports — **{pct:.0f}%** of all "
        f"{total_reports:,.0f} calendar-job reports in that period."
    )

# ── Effort-by-period matrices — reporting & verifying across all periods ──────
period_names = list(PERIODS.keys())
period_days_list = list(PERIODS.values())
rate_by_rank = df_f.groupby("Rank")["Daily Rate"].sum()
rate_by_verifier = df_f.groupby("Verifier")["Daily Rate"].sum()


def effort_matrix(rate_series, row_order):
    # keep unrounded so the Grand Total matches the KPI figures exactly;
    # rounding happens only at display time via the styler format
    mat = pd.DataFrame(
        {p: rate_series.reindex(row_order).fillna(0) * d
         for p, d in zip(period_names, period_days_list)},
        index=row_order,
    )
    mat.index.name = "Rank"
    total = mat.sum(axis=0)
    total.name = "Grand Total"
    return pd.concat([mat, total.to_frame().T])


def style_effort(mat):
    data_idx = [i for i in mat.index if i != "Grand Total"]

    def col_style(col):
        sub = col.loc[data_idx]
        vmin, vmax = (sub.min(), sub.max()) if len(sub) else (0, 1)
        return [
            "background-color:#c6d9ec;font-weight:bold" if idx == "Grand Total"
            else heat_color(v, vmin, vmax)
            for idx, v in col.items()
        ]

    return mat.style.apply(col_style, axis=0).format("{:,.0f}")


ranks_ordered = list(rate_by_rank.sort_values(ascending=False).index)
report_matrix = effort_matrix(rate_by_rank, ranks_ordered)

verifiers_present = [v for v in ("Master", "Chief Engineer") if v in rate_by_verifier.index]
verify_matrix = effort_matrix(rate_by_verifier, verifiers_present)

with effort_col:
    st.markdown("**Reporting effort** — estimated job reports per period")
    st.dataframe(style_effort(report_matrix), use_container_width=True)
    st.markdown("**Verifying effort** — reports to sign off per period")
    st.dataframe(style_effort(verify_matrix), use_container_width=True)
    st.download_button(
        "⬇ Download effort matrices (Excel)",
        data=to_excel({"Reporting Effort": report_matrix, "Verifying Effort": verify_matrix}),
        file_name="reporting_verifying_effort_by_period.xlsx",
    )

summary_cols = ["Total Jobs", "Time-Based Jobs", "Running-Hour Jobs",
                f"Jobs Due ≥1x in {period_label}", f"Est. Reports in {period_label}"]
summary_fmt = {c: "{:,.0f}" for c in summary_cols}
summary_fmt[f"Est. Reports in {period_label}"] = "{:,.1f}"

styled_summary = (
    summary_display[summary_cols].style
    .apply(heatmap_column, axis=0)
    .format(summary_fmt)
)
st.dataframe(styled_summary, use_container_width=True)
st.caption(
    "**Est. Reports** = period length ÷ job frequency, summed per rank — the statistical average "
    "number of times each rank must submit a job report in the selected period. **Jobs Due ≥1x** "
    "counts jobs whose frequency is short enough to fall due at least once in the period."
    + ("" if include_hours else " Running-hour based jobs are excluded from these figures — enable "
                                  "the sidebar option to include an estimate.")
)

st.download_button(
    "⬇ Download rank effort summary (Excel)",
    data=to_excel({"Rank Effort Summary": summary_display}),
    file_name=f"rank_reporting_effort_{period_label.replace(' ', '_')}.xlsx",
)

# ─────────────────────────────────────────────────────────────────────────────
# MATRIX — RANK x FREQUENCY
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("📋 Job Frequency Matrix by Rank")

matrix_mask = (df_f["Is Time Based"]) & (df_f["Freq Days"] <= period_days)
subtitle = f"≤ {period_label}"
if include_hours:
    hrs_mask = (df_f["Freq Unit"] == "Hours") & (df_f["Freq Value"] <= hours_threshold)
    matrix_mask = matrix_mask | hrs_mask
    subtitle += f" / < {hours_threshold:,.0f} Hrs"

matrix_src = df_f[matrix_mask]

if matrix_src.empty:
    st.info("No jobs fall within the selected period/threshold for the matrix view.")
else:
    st.markdown(f"**Low-frequency jobs by performing rank**  \n*{subtitle}*")

    pivot = pd.pivot_table(
        matrix_src, index="Rank", columns="Frequency", values="Job Code",
        aggfunc="count", fill_value=0,
    )
    ordered_cols = sorted(pivot.columns, key=freq_sort_key)
    pivot = pivot[ordered_cols]
    pivot["Grand Total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Grand Total", ascending=False)
    total_row = pivot.sum(axis=0)
    total_row.name = "Grand Total"
    pivot = pd.concat([pivot, total_row.to_frame().T])

    data_cols = [c for c in pivot.columns if c != "Grand Total"]
    body = pivot.loc[pivot.index != "Grand Total", data_cols]
    vmin, vmax = (body.values.min(), body.values.max()) if body.size else (0, 1)

    def style_matrix(row):
        if row.name == "Grand Total":
            return ["background-color:#c6d9ec;font-weight:bold"] * len(row)
        styles = []
        for col in row.index:
            if col == "Grand Total":
                styles.append("background-color:#dce6f1;font-weight:bold")
            else:
                styles.append(heat_color(row[col], vmin, vmax))
        return styles

    styled = pivot.style.apply(style_matrix, axis=1).format("{:,.0f}")
    st.dataframe(styled, use_container_width=True)

    st.download_button(
        "⬇ Download matrix (Excel)",
        data=to_excel({"Rank x Frequency": pivot}),
        file_name=f"rank_frequency_matrix_{period_label.replace(' ', '_')}.xlsx",
    )
