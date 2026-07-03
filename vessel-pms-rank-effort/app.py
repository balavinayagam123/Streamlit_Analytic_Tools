import io
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Vessel PMS – Rank Reporting Effort",
    page_icon="🧭",
    layout="wide",
)

st.title("🧭 Vessel PMS – Rank Reporting Effort")
st.markdown(
    "Upload a JiBe (or similar) PMS job export to see how many job reports "
    "each rank must submit over a selected period, based on job frequency."
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


# Excel-style 3-color scale: green (low) -> yellow (mid) -> red (high)
HEAT_GREEN, HEAT_YELLOW, HEAT_RED = (99, 190, 123), (255, 235, 132), (248, 105, 107)


def _mix(c1, c2, t):
    return tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def heat_color(v, vmin, vmax):
    t = 0.5 if vmax == vmin else (v - vmin) / (vmax - vmin)
    rgb = _mix(HEAT_GREEN, HEAT_YELLOW, t / 0.5) if t <= 0.5 else _mix(HEAT_YELLOW, HEAT_RED, (t - 0.5) / 0.5)
    return f"background-color: rgb{rgb}"


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

df_f = primary_rank(df_f)
rank_opts = clean_opts(df_f["Rank"])

# ─────────────────────────────────────────────────────────────────────────────
# RANK EFFORT SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader(f"📊 Rank Reporting Effort — next {period_label}")

kpi_slots = st.columns(5)
chart_col, filter_col = st.columns([3, 1])

with filter_col:
    st.markdown("**Rank(s) to include**")
    rank_f = st.multiselect(
        "Rank(s) to include", options=rank_opts, default=rank_opts, label_visibility="collapsed"
    )

df_f = df_f[df_f["Rank"].isin(rank_f)]

if df_f.empty:
    st.warning("No jobs match the current filters.")
    st.stop()

# Expected occurrences within the selected period
df_f["Expected Occurrences"] = np.where(
    df_f["Is Time Based"], period_days / df_f["Freq Days"], np.nan
)
if include_hours:
    hrs_mask = df_f["Freq Unit"] == "Hours"
    equiv_days = df_f["Freq Value"] / avg_hours_per_day
    df_f.loc[hrs_mask, "Expected Occurrences"] = period_days / equiv_days[hrs_mask]

df_f["Due At Least Once"] = df_f["Expected Occurrences"].fillna(0) >= 1

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
df_f["Verifier"] = df_f["Rank"].map(verifier_of)
ce_verify = df_f.loc[df_f["Verifier"] == "Chief Engineer", "Expected Occurrences"].sum()
master_verify = df_f.loc[df_f["Verifier"] == "Master", "Expected Occurrences"].sum()
top_rank = summary.index[0] if len(summary) else "—"

kpis = [
    ("Ranks in scope", str(len(summary)), None),
    (f"Total est. reports / {period_label}",
     f"{summary['Est. Reports in ' + period_label].sum():,.0f}", None),
    ("Highest-effort rank", top_rank, None),
    (f"⚙ CE verifying effort / {period_label}", f"{ce_verify:,.0f}",
     "Estimated job reports the Chief Engineer must verify — all engineer and "
     "electrical ranks' jobs (including the Chief Engineer's own)."),
    (f"🎖 Master verifying effort / {period_label}", f"{master_verify:,.0f}",
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

fig = go.Figure()
fig.add_bar(
    y=counts.index, x=counts["Non-Critical"], name="Non-Critical", orientation="h",
    marker_color=PASTEL_NONCRIT, text=counts["Non-Critical"], textposition="inside",
    insidetextanchor="middle",
)
fig.add_bar(
    y=counts.index, x=counts["Critical"], name="Critical", orientation="h",
    marker_color=PASTEL_CRITICAL, text=counts["Critical"], textposition="inside",
    insidetextanchor="middle",
)
fig.update_layout(
    barmode="stack",
    height=max(320, 34 * len(counts)),
    plot_bgcolor="#fcfcfb",
    paper_bgcolor="#fcfcfb",
    xaxis_title="Number of jobs",
    yaxis_title=None,
    font_color="#0b0b0b",
    margin=dict(l=10, r=20, t=10, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
fig.update_xaxes(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7")
with chart_col:
    st.plotly_chart(fig, use_container_width=True)

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
