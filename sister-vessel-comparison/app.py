import streamlit as st
import pandas as pd
import io
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Sister Vessel PMS Comparison",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Sister Vessel PMS Comparison")
st.markdown("Upload JiBe PMS exports for two sister vessels to identify missing jobs and frequency mismatches.")

# ── helpers ──────────────────────────────────────────────────────────────────

def load_csv(bytes_data):
    df = pd.read_csv(io.BytesIO(bytes_data), header=0, dtype=str)
    cols = df.columns.tolist()
    cols[1] = "Critical"
    df.columns = cols
    if "Unnamed: 2" in df.columns:
        df = df.drop(columns=["Unnamed: 2"])
    for col in ["Job Code", "Machinery Location", "Sub Component Location",
                "Frequency", "Job Action", "Title", "Function", "Department", "Vessel"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def get_vessel_name(df):
    if "Vessel" in df.columns:
        names = [n for n in df["Vessel"].dropna().unique() if n not in ("", "nan")]
        if names:
            return names[0]
    return "Vessel"


def compare(df_a, df_b, vessel_a, vessel_b):
    KEY = ["Job Code", "Machinery Location", "Sub Component Location", "Title"]

    def make_key(df):
        return df[KEY].fillna("").apply(lambda r: "|||".join(r.values), axis=1)

    df_a = df_a.copy()
    df_b = df_b.copy()
    df_a["_key"] = make_key(df_a)
    df_b["_key"] = make_key(df_b)

    set_a = set(df_a["_key"])
    set_b = set(df_b["_key"])

    cols_show = ["Job Code", "Critical", "Machinery Location", "Sub Component Location",
                 "Frequency", "Job Action", "Title", "Function", "Department"]

    missing_in_b = df_a[df_a["_key"].isin(set_a - set_b)][
        [c for c in cols_show if c in df_a.columns]
    ].copy()

    missing_in_a = df_b[df_b["_key"].isin(set_b - set_a)][
        [c for c in cols_show if c in df_b.columns]
    ].copy()

    common_keys = set_a & set_b
    merged = pd.merge(
        df_a[df_a["_key"].isin(common_keys)][
            ["_key", "Job Code", "Critical", "Machinery Location",
             "Sub Component Location", "Frequency", "Job Action",
             "Title", "Function", "Department"]
        ],
        df_b[df_b["_key"].isin(common_keys)][["_key", "Frequency"]],
        on="_key",
        suffixes=(f" ({vessel_a})", f" ({vessel_b})")
    )

    freq_col_a = f"Frequency ({vessel_a})"
    freq_col_b = f"Frequency ({vessel_b})"

    freq_mismatch = merged[
        merged[freq_col_a] != merged[freq_col_b]
    ][[
        "Job Code", "Critical", "Machinery Location", "Sub Component Location",
        freq_col_a, freq_col_b, "Job Action", "Title", "Function", "Department"
    ]].copy()

    return missing_in_b, missing_in_a, freq_mismatch


def to_excel(dfs: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()


def apply_filters(df, dept_filter, fn_filter, machinery_filter, critical_only):
    if dept_filter and "Department" in df.columns:
        df = df[df["Department"].isin(dept_filter)]
    if fn_filter and "Function" in df.columns:
        df = df[df["Function"].isin(fn_filter)]
    if machinery_filter and "Machinery Location" in df.columns:
        df = df[df["Machinery Location"].isin(machinery_filter)]
    if critical_only and "Critical" in df.columns:
        df = df[df["Critical"] == "C"]
    return df


def style_missing(df):
    """Highlight Critical rows in red, others in default."""
    def row_style(row):
        if str(row.get("Critical", "")).strip() == "C":
            return ["background-color: #ffe0e0; color: #900"] * len(row)
        return [""] * len(row)
    return df.style.apply(row_style, axis=1)


def style_freq_mismatch(df, vessel_a, vessel_b):
    """
    - Critical rows: red background
    - Frequency columns: amber background to draw eye
    """
    freq_col_a = f"Frequency ({vessel_a})"
    freq_col_b = f"Frequency ({vessel_b})"

    def row_style(row):
        is_critical = str(row.get("Critical", "")).strip() == "C"
        base = "background-color: #ffe0e0; color: #900" if is_critical else ""
        styles = []
        for col in row.index:
            if col in (freq_col_a, freq_col_b):
                if is_critical:
                    styles.append("background-color: #ff9900; color: #000; font-weight: bold")
                else:
                    styles.append("background-color: #fff3cd; color: #7a5900; font-weight: bold")
            else:
                styles.append(base)
        return styles

    return df.style.apply(row_style, axis=1)


def freq_sort_key(freq_str):
    """Convert frequency string to days for sorting in charts."""
    try:
        num, unit = str(freq_str).strip().split(" ", 1)
        num = float(num)
        unit = unit.lower()
        if "day" in unit:   return num
        if "month" in unit: return num * 30
        if "hour" in unit:  return num / 24
        if "year" in unit:  return num * 365
    except Exception:
        pass
    return 99999


def clean_opts(series_a, series_b):
    raw = series_a.tolist() + series_b.tolist()
    return sorted({str(v).strip() for v in raw
                   if v is not None and str(v).strip() not in ("", "nan", "None", "NaN")})


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 Upload PMS Exports")
    st.markdown("Export pending jobs from JiBe for each vessel and upload the CSV files below.")
    file_a = st.file_uploader("Vessel A — CSV", type=["csv"], key="file_a")
    st.divider()
    file_b = st.file_uploader("Vessel B — CSV", type=["csv"], key="file_b")
    st.divider()
    run = st.button("🔍 Run Comparison", type="primary", use_container_width=True)

# ── Store raw bytes on Run ────────────────────────────────────────────────────

if run:
    if not file_a or not file_b:
        st.warning("Please upload CSV files for **both** vessels before running.")
        st.stop()
    st.session_state["bytes_a"] = file_a.read()
    st.session_state["bytes_b"] = file_b.read()

# ── Gate ─────────────────────────────────────────────────────────────────────

if "bytes_a" not in st.session_state or "bytes_b" not in st.session_state:
    st.info("👈  Upload two JiBe PMS CSV exports in the sidebar and click **Run Comparison**.")
    with st.expander("ℹ️  How to export from JiBe"):
        st.markdown("""
1. In JiBe, go to **Planned Maintenance → Jobs**
2. Filter by vessel and status = **Pending**
3. Click **Export to Excel** (saves as CSV)
4. Upload both files in the sidebar
        """)
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────────────

df_a = load_csv(st.session_state["bytes_a"])
df_b = load_csv(st.session_state["bytes_b"])

vessel_a = get_vessel_name(df_a)
vessel_b = get_vessel_name(df_b)

missing_b, missing_a, freq_mismatch = compare(df_a, df_b, vessel_a, vessel_b)

# ── Summary metrics ───────────────────────────────────────────────────────────

st.subheader("📊 Summary")
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric(f"Total Jobs — {vessel_a}", len(df_a))
c2.metric(f"Total Jobs — {vessel_b}", len(df_b))
c3.metric(f"Missing in {vessel_b}", len(missing_b), delta=f"-{len(missing_b)}", delta_color="inverse")
c4.metric(f"Missing in {vessel_a}", len(missing_a), delta=f"-{len(missing_a)}", delta_color="inverse")
c5.metric("Freq Mismatches", len(freq_mismatch), delta=f"{len(freq_mismatch)}", delta_color="inverse")

# Critical gap metrics
crit_b = int((missing_b["Critical"] == "C").sum()) if "Critical" in missing_b.columns else 0
crit_a = int((missing_a["Critical"] == "C").sum()) if "Critical" in missing_a.columns else 0
c6.metric(f"Critical Missing in {vessel_b}", crit_b, delta=f"-{crit_b}" if crit_b else "0", delta_color="inverse")
c7.metric(f"Critical Missing in {vessel_a}", crit_a, delta=f"-{crit_a}" if crit_a else "0", delta_color="inverse")

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────

with st.expander("🔧 Filter Results", expanded=False):
    col1, col2, col3, col4 = st.columns(4)
    all_dept      = clean_opts(df_a["Department"],         df_b["Department"])
    all_fn        = clean_opts(df_a["Function"],           df_b["Function"])
    all_machinery = clean_opts(df_a["Machinery Location"], df_b["Machinery Location"])
    with col1:
        dept_filter = st.multiselect("Department", options=all_dept)
    with col2:
        fn_filter = st.multiselect("Function", options=all_fn)
    with col3:
        machinery_filter = st.multiselect("Machinery Location", options=all_machinery)
    with col4:
        critical_only = st.checkbox("Critical jobs only (C flag)")

mb = apply_filters(missing_b,     dept_filter, fn_filter, machinery_filter, critical_only)
ma = apply_filters(missing_a,     dept_filter, fn_filter, machinery_filter, critical_only)
fm = apply_filters(freq_mismatch, dept_filter, fn_filter, machinery_filter, critical_only)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    f"❌ Missing in {vessel_b} ({len(mb)})",
    f"❌ Missing in {vessel_a} ({len(ma)})",
    f"⚠️ Frequency Mismatches ({len(fm)})",
    "📊 Department Gap Analysis",
    "📈 Frequency Distribution",
])

# ── Tab 1: Missing in Vessel B ────────────────────────────────────────────────

with tab1:
    st.markdown(f"Jobs present in **{vessel_a}** but **not found** in **{vessel_b}**.")
    st.caption("🔴 Red rows = Critical jobs (C flag)")
    if mb.empty:
        st.success("No missing jobs found.")
    else:
        st.dataframe(style_missing(mb.reset_index(drop=True)), use_container_width=True, height=450)

# ── Tab 2: Missing in Vessel A ────────────────────────────────────────────────

with tab2:
    st.markdown(f"Jobs present in **{vessel_b}** but **not found** in **{vessel_a}**.")
    st.caption("🔴 Red rows = Critical jobs (C flag)")
    if ma.empty:
        st.success("No missing jobs found.")
    else:
        st.dataframe(style_missing(ma.reset_index(drop=True)), use_container_width=True, height=450)

# ── Tab 3: Frequency Mismatches ───────────────────────────────────────────────

with tab3:
    st.markdown(f"Jobs in **both** vessels with **different maintenance frequencies**.")
    st.caption("🟡 Amber cells = frequency columns  |  🔴 Red rows = Critical jobs")
    if fm.empty:
        st.success("No frequency mismatches found.")
    else:
        st.dataframe(
            style_freq_mismatch(fm.reset_index(drop=True), vessel_a, vessel_b),
            use_container_width=True,
            height=450
        )

# ── Tab 4: Department Gap Analysis ───────────────────────────────────────────

with tab4:
    st.markdown("### Department-wise Gap Summary")
    st.markdown("How gaps and critical missing jobs are distributed across Engine and Deck departments.")

    def dept_summary(df_missing, vessel_missing_from, label):
        if "Department" not in df_missing.columns or df_missing.empty:
            return pd.DataFrame()
        grp = df_missing.groupby("Department").agg(
            Total=("Job Code", "count"),
            Critical=("Critical", lambda x: (x == "C").sum())
        ).reset_index()
        grp["Non-Critical"] = grp["Total"] - grp["Critical"]
        grp["Missing From"] = vessel_missing_from
        grp["Label"] = label
        return grp

    dept_b = dept_summary(mb, vessel_b, f"Missing in {vessel_b}")
    dept_a = dept_summary(ma, vessel_a, f"Missing in {vessel_a}")
    dept_all = pd.concat([dept_b, dept_a], ignore_index=True)

    if dept_all.empty:
        st.success("No gaps to display after filters.")
    else:
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown(f"#### Missing in {vessel_b}")
            if dept_b.empty:
                st.success("No missing jobs.")
            else:
                fig = go.Figure()
                fig.add_bar(
                    x=dept_b["Department"], y=dept_b["Critical"],
                    name="Critical", marker_color="#d9534f"
                )
                fig.add_bar(
                    x=dept_b["Department"], y=dept_b["Non-Critical"],
                    name="Non-Critical", marker_color="#5bc0de"
                )
                fig.update_layout(
                    barmode="stack", height=350,
                    xaxis_title="Department", yaxis_title="Number of Jobs",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(t=30, b=40)
                )
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(dept_b[["Department","Critical","Non-Critical","Total"]].reset_index(drop=True),
                             use_container_width=True, hide_index=True)

        with col_right:
            st.markdown(f"#### Missing in {vessel_a}")
            if dept_a.empty:
                st.success("No missing jobs.")
            else:
                fig2 = go.Figure()
                fig2.add_bar(
                    x=dept_a["Department"], y=dept_a["Critical"],
                    name="Critical", marker_color="#d9534f"
                )
                fig2.add_bar(
                    x=dept_a["Department"], y=dept_a["Non-Critical"],
                    name="Non-Critical", marker_color="#5bc0de"
                )
                fig2.update_layout(
                    barmode="stack", height=350,
                    xaxis_title="Department", yaxis_title="Number of Jobs",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(t=30, b=40)
                )
                st.plotly_chart(fig2, use_container_width=True)
                st.dataframe(dept_a[["Department","Critical","Non-Critical","Total"]].reset_index(drop=True),
                             use_container_width=True, hide_index=True)

# ── Tab 5: Frequency Distribution ────────────────────────────────────────────

with tab5:
    st.markdown("### Frequency Distribution Comparison")
    st.markdown("How maintenance intervals are spread across both vessels. Differences highlight workload imbalance.")

    def freq_dist(df, vessel_name):
        if "Frequency" not in df.columns:
            return pd.DataFrame()
        counts = df["Frequency"].value_counts().reset_index()
        counts.columns = ["Frequency", "Count"]
        counts["Vessel"] = vessel_name
        counts["_sort"] = counts["Frequency"].apply(freq_sort_key)
        counts = counts.sort_values("_sort").drop(columns="_sort")
        return counts

    dist_a = freq_dist(df_a, vessel_a)
    dist_b = freq_dist(df_b, vessel_b)
    dist_all = pd.concat([dist_a, dist_b], ignore_index=True)

    if dist_all.empty:
        st.info("No frequency data available.")
    else:
        # Sort x-axis by frequency value
        freq_order = (
            dist_all.assign(_s=dist_all["Frequency"].apply(freq_sort_key))
            .drop_duplicates("Frequency")
            .sort_values("_s")["Frequency"]
            .tolist()
        )

        fig3 = px.bar(
            dist_all, x="Frequency", y="Count", color="Vessel",
            barmode="group",
            category_orders={"Frequency": freq_order},
            color_discrete_map={vessel_a: "#0066cc", vessel_b: "#ff7700"},
            labels={"Count": "Number of Jobs", "Frequency": "Maintenance Interval"},
            height=450
        )
        fig3.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis_tickangle=-45,
            margin=dict(t=40, b=100)
        )
        st.plotly_chart(fig3, use_container_width=True)

        st.markdown("#### Intervals present in one vessel but not the other")
        freqs_a = set(dist_a["Frequency"].tolist())
        freqs_b = set(dist_b["Frequency"].tolist())
        only_a = freqs_a - freqs_b
        only_b = freqs_b - freqs_a

        ca, cb = st.columns(2)
        with ca:
            st.markdown(f"**Only in {vessel_a}**")
            if only_a:
                st.dataframe(
                    dist_a[dist_a["Frequency"].isin(only_a)][["Frequency","Count"]].reset_index(drop=True),
                    use_container_width=True, hide_index=True
                )
            else:
                st.success("None")
        with cb:
            st.markdown(f"**Only in {vessel_b}**")
            if only_b:
                st.dataframe(
                    dist_b[dist_b["Frequency"].isin(only_b)][["Frequency","Count"]].reset_index(drop=True),
                    use_container_width=True, hide_index=True
                )
            else:
                st.success("None")

# ── Download ──────────────────────────────────────────────────────────────────

st.divider()
st.subheader("⬇️ Download Gap Report")

excel_data = to_excel({
    f"Missing in {vessel_b}"[:31]: missing_b,
    f"Missing in {vessel_a}"[:31]: missing_a,
    "Frequency Mismatches": freq_mismatch
})

st.download_button(
    label="📥 Download Full Report (.xlsx)",
    data=excel_data,
    file_name=f"PMS_Comparison_{vessel_a}_vs_{vessel_b}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary"
)
