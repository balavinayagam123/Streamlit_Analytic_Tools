import streamlit as st
import pandas as pd
import io
import itertools
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Sister Vessel PMS Comparison",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Sister Vessel PMS Comparison")
st.markdown("Upload JiBe PMS exports for up to **4 sister vessels** to identify missing jobs, frequency mismatches, and fleet-wide gaps.")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

VESSEL_COLORS = ["#0066cc", "#ff7700", "#27a060", "#9b59b6"]
MAX_VESSELS   = 4

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

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


def make_key(df):
    KEY = ["Job Code", "Machinery Location", "Sub Component Location", "Title"]
    return df[KEY].fillna("").apply(lambda r: "|||".join(r.values), axis=1)


def compare_pair(df_x, df_y, name_x, name_y):
    """Compare two vessels. Returns (missing_in_y, missing_in_x, freq_mismatch)."""
    df_x = df_x.copy(); df_x["_key"] = make_key(df_x)
    df_y = df_y.copy(); df_y["_key"] = make_key(df_y)

    set_x, set_y = set(df_x["_key"]), set(df_y["_key"])
    cols_show = ["Job Code", "Critical", "Machinery Location", "Sub Component Location",
                 "Frequency", "Job Action", "Title", "Function", "Department"]

    miss_y = df_x[df_x["_key"].isin(set_x - set_y)][[c for c in cols_show if c in df_x.columns]].copy()
    miss_x = df_y[df_y["_key"].isin(set_y - set_x)][[c for c in cols_show if c in df_y.columns]].copy()

    common  = set_x & set_y
    merged  = pd.merge(
        df_x[df_x["_key"].isin(common)][["_key","Job Code","Critical","Machinery Location",
                                          "Sub Component Location","Frequency","Job Action",
                                          "Title","Function","Department"]],
        df_y[df_y["_key"].isin(common)][["_key","Frequency"]],
        on="_key", suffixes=(f" ({name_x})", f" ({name_y})")
    )
    fa, fb = f"Frequency ({name_x})", f"Frequency ({name_y})"
    freq_mm = merged[merged[fa] != merged[fb]][[
        "Job Code","Critical","Machinery Location","Sub Component Location",
        fa, fb, "Job Action","Title","Function","Department"
    ]].copy()

    return miss_y, miss_x, freq_mm


def apply_filters(df, dept_f, fn_f, mach_f, crit_only):
    if dept_f    and "Department"       in df.columns: df = df[df["Department"].isin(dept_f)]
    if fn_f      and "Function"         in df.columns: df = df[df["Function"].isin(fn_f)]
    if mach_f    and "Machinery Location" in df.columns: df = df[df["Machinery Location"].isin(mach_f)]
    if crit_only and "Critical"         in df.columns: df = df[df["Critical"] == "C"]
    return df


def style_missing(df):
    def row_style(row):
        if str(row.get("Critical","")).strip() == "C":
            return ["background-color:#ffe0e0;color:#900"] * len(row)
        return [""] * len(row)
    return df.style.apply(row_style, axis=1)


def style_freq(df, col_a, col_b):
    def row_style(row):
        is_crit = str(row.get("Critical","")).strip() == "C"
        base    = "background-color:#ffe0e0;color:#900" if is_crit else ""
        styles  = []
        for col in row.index:
            if col in (col_a, col_b):
                styles.append("background-color:#ff9900;color:#000;font-weight:bold" if is_crit
                               else "background-color:#fff3cd;color:#7a5900;font-weight:bold")
            else:
                styles.append(base)
        return styles
    return df.style.apply(row_style, axis=1)


def freq_sort_key(f):
    try:
        num, unit = str(f).strip().split(" ", 1)
        num = float(num); unit = unit.lower()
        if "day"   in unit: return num
        if "month" in unit: return num * 30
        if "hour"  in unit: return num / 24
        if "year"  in unit: return num * 365
    except Exception:
        pass
    return 99999


def clean_opts(*series_list):
    raw = []
    for s in series_list:
        raw += s.tolist()
    return sorted({str(v).strip() for v in raw
                   if v is not None and str(v).strip() not in ("", "nan", "None", "NaN")})


def to_excel(dfs: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — upload up to 4 vessels
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 Upload PMS Exports")
    st.markdown("Upload 2–4 JiBe CSV exports. Vessel names are auto-detected.")
    st.divider()

    uploaded = []
    for i in range(1, MAX_VESSELS + 1):
        f = st.file_uploader(f"Vessel {i} — CSV", type=["csv"], key=f"file_{i}")
        uploaded.append(f)
        if i < MAX_VESSELS:
            st.divider()

    st.divider()
    run = st.button("🔍 Run Comparison", type="primary", use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# STORE RAW BYTES ON RUN
# ─────────────────────────────────────────────────────────────────────────────

if run:
    active = [f for f in uploaded if f is not None]
    if len(active) < 2:
        st.warning("Please upload at least **2** vessel CSV files before running.")
        st.stop()
    st.session_state["vessel_bytes"] = [f.read() for f in active]

# ─────────────────────────────────────────────────────────────────────────────
# GATE
# ─────────────────────────────────────────────────────────────────────────────

if "vessel_bytes" not in st.session_state:
    st.info("👈  Upload 2–4 JiBe PMS CSV exports in the sidebar and click **Run Comparison**.")
    with st.expander("ℹ️  How to export from JiBe"):
        st.markdown("""
1. Go to **Planned Maintenance → Jobs**
2. Filter by vessel, status = **Pending**
3. Click **Export to Excel** (saves as CSV)
4. Upload files for each vessel in the sidebar
        """)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PARSE ALL VESSELS
# ─────────────────────────────────────────────────────────────────────────────

vessels_df   = [load_csv(b) for b in st.session_state["vessel_bytes"]]
vessel_names = [get_vessel_name(df) for df in vessels_df]
n_vessels    = len(vessels_df)
color_map    = {vessel_names[i]: VESSEL_COLORS[i] for i in range(n_vessels)}

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY METRICS — one card per vessel
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("📊 Fleet Summary")
cols_metric = st.columns(n_vessels)
for i, (df, name) in enumerate(zip(vessels_df, vessel_names)):
    crit_count = int((df["Critical"] == "C").sum()) if "Critical" in df.columns else 0
    with cols_metric[i]:
        with st.container(border=True):
            st.markdown(f"**🚢 {name}**")
            st.metric("Total Jobs", len(df))
            st.metric("Critical Jobs", crit_count)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# PAIRWISE COMPARISON — compute all pairs
# ─────────────────────────────────────────────────────────────────────────────

pairs = list(itertools.combinations(range(n_vessels), 2))

# Build all pair results: {(i,j): (miss_j, miss_i, freq_mm)}
pair_results = {}
for i, j in pairs:
    pair_results[(i, j)] = compare_pair(
        vessels_df[i], vessels_df[j], vessel_names[i], vessel_names[j]
    )

# ─────────────────────────────────────────────────────────────────────────────
# FILTERS — built from all vessels combined
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("🔧 Filter Results", expanded=False):
    fc1, fc2, fc3, fc4 = st.columns(4)

    all_dept = clean_opts(*[df["Department"] for df in vessels_df])
    all_fn   = clean_opts(*[df["Function"]   for df in vessels_df])
    all_mach = clean_opts(*[df["Machinery Location"] for df in vessels_df])

    with fc1: dept_f    = st.multiselect("Department",        options=all_dept)
    with fc2: fn_f      = st.multiselect("Function",          options=all_fn)
    with fc3: mach_f    = st.multiselect("Machinery Location", options=all_mach)
    with fc4: crit_only = st.checkbox("Critical jobs only (C flag)")

# ─────────────────────────────────────────────────────────────────────────────
# PAIR SELECTOR — choose which pair to drill into
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("🔍 Pairwise Comparison")

pair_labels = [f"{vessel_names[i]}  ↔  {vessel_names[j]}" for i, j in pairs]
selected_pair_label = st.selectbox("Select vessel pair to compare:", options=pair_labels)
sel_idx = pair_labels.index(selected_pair_label)
si, sj  = pairs[sel_idx]
sel_name_i = vessel_names[si]
sel_name_j = vessel_names[sj]

miss_j_raw, miss_i_raw, freq_mm_raw = pair_results[(si, sj)]

miss_j = apply_filters(miss_j_raw, dept_f, fn_f, mach_f, crit_only)
miss_i = apply_filters(miss_i_raw, dept_f, fn_f, mach_f, crit_only)
freq_mm = apply_filters(freq_mm_raw, dept_f, fn_f, mach_f, crit_only)

fa = f"Frequency ({sel_name_i})"
fb = f"Frequency ({sel_name_j})"

# ─────────────────────────────────────────────────────────────────────────────
# PAIRWISE METRIC ROW
# ─────────────────────────────────────────────────────────────────────────────

pm1, pm2, pm3, pm4, pm5 = st.columns(5)
crit_mj = int((miss_j["Critical"] == "C").sum()) if "Critical" in miss_j.columns else 0
crit_mi = int((miss_i["Critical"] == "C").sum()) if "Critical" in miss_i.columns else 0
pm1.metric(f"Missing in {sel_name_j}", len(miss_j), delta=f"-{len(miss_j)}", delta_color="inverse")
pm2.metric(f"Missing in {sel_name_i}", len(miss_i), delta=f"-{len(miss_i)}", delta_color="inverse")
pm3.metric("Freq Mismatches", len(freq_mm), delta=f"{len(freq_mm)}", delta_color="inverse")
pm4.metric(f"Critical Missing in {sel_name_j}", crit_mj, delta=f"-{crit_mj}" if crit_mj else "0", delta_color="inverse")
pm5.metric(f"Critical Missing in {sel_name_i}", crit_mi, delta=f"-{crit_mi}" if crit_mi else "0", delta_color="inverse")

# ─────────────────────────────────────────────────────────────────────────────
# PAIRWISE TABS
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    f"❌ Missing in {sel_name_j} ({len(miss_j)})",
    f"❌ Missing in {sel_name_i} ({len(miss_i)})",
    f"⚠️ Freq Mismatches ({len(freq_mm)})",
])

with tab1:
    st.caption(f"Jobs in **{sel_name_i}** not found in **{sel_name_j}**.  🔴 Red = Critical")
    if miss_j.empty:
        st.success("No missing jobs.")
    else:
        st.dataframe(style_missing(miss_j.reset_index(drop=True)), use_container_width=True, height=420)

with tab2:
    st.caption(f"Jobs in **{sel_name_j}** not found in **{sel_name_i}**.  🔴 Red = Critical")
    if miss_i.empty:
        st.success("No missing jobs.")
    else:
        st.dataframe(style_missing(miss_i.reset_index(drop=True)), use_container_width=True, height=420)

with tab3:
    st.caption("🟡 Amber = frequency columns  |  🔴 Red = Critical")
    if freq_mm.empty:
        st.success("No frequency mismatches.")
    else:
        st.dataframe(style_freq(freq_mm.reset_index(drop=True), fa, fb),
                     use_container_width=True, height=420)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# FLEET-WIDE ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("📊 Fleet-Wide Analytics")

atab1, atab2, atab3, atab4 = st.tabs([
    "📋 Gap Matrix",
    "📊 Department Gap Analysis",
    "📈 Frequency Distribution",
    "🔩 Machinery Job Count",
])

# ── Gap Matrix ────────────────────────────────────────────────────────────────

with atab1:
    st.markdown("### Pairwise Gap Matrix")
    st.markdown("Total missing jobs between every vessel pair. Higher numbers indicate greater PMS divergence.")

    matrix_data = []
    for i in range(n_vessels):
        row = []
        for j in range(n_vessels):
            if i == j:
                row.append("—")
            elif i < j:
                mj, mi, _ = pair_results[(i, j)]
                row.append(f"{len(mj)} / {len(mi)}")
            else:
                mj, mi, _ = pair_results[(j, i)]
                row.append(f"{len(mi)} / {len(mj)}")
        matrix_data.append(row)

    matrix_df = pd.DataFrame(matrix_data, index=vessel_names, columns=vessel_names)
    st.markdown("*Format: Missing in column vessel / Missing in row vessel*")
    st.dataframe(matrix_df, use_container_width=True)

    st.markdown("### Frequency Mismatch Count per Pair")
    mismatch_rows = []
    for i, j in pairs:
        _, _, fm = pair_results[(i, j)]
        mismatch_rows.append({
            "Vessel Pair": f"{vessel_names[i]}  ↔  {vessel_names[j]}",
            "Freq Mismatches": len(fm),
            "Critical Mismatches": int((fm["Critical"] == "C").sum()) if "Critical" in fm.columns else 0
        })
    mismatch_summary = pd.DataFrame(mismatch_rows)
    st.dataframe(mismatch_summary, use_container_width=True, hide_index=True)

# ── Department Gap Analysis ───────────────────────────────────────────────────

with atab2:
    st.markdown("### Department-wise Gap Summary — All Pairs")
    st.markdown("Missing jobs broken down by Engine / Deck for each vessel pair.")

    for i, j in pairs:
        mj, mi, _ = pair_results[(i, j)]
        mj_f = apply_filters(mj, dept_f, fn_f, mach_f, crit_only)
        mi_f = apply_filters(mi, dept_f, fn_f, mach_f, crit_only)

        with st.container(border=True):
            st.markdown(f"#### {vessel_names[i]}  ↔  {vessel_names[j]}")
            col_l, col_r = st.columns(2)

            for col_side, df_miss, missing_from in [
                (col_l, mj_f, vessel_names[j]),
                (col_r, mi_f, vessel_names[i])
            ]:
                with col_side:
                    st.markdown(f"**Missing in {missing_from}**")
                    if df_miss.empty or "Department" not in df_miss.columns:
                        st.success("No missing jobs.")
                        continue
                    grp = df_miss.groupby("Department").agg(
                        Critical=("Critical", lambda x: (x == "C").sum()),
                        Total=("Job Code", "count")
                    ).reset_index()
                    grp["Non-Critical"] = grp["Total"] - grp["Critical"]

                    fig = go.Figure()
                    fig.add_bar(x=grp["Department"], y=grp["Critical"],
                                name="Critical", marker_color="#d9534f")
                    fig.add_bar(x=grp["Department"], y=grp["Non-Critical"],
                                name="Non-Critical", marker_color="#5bc0de")
                    fig.update_layout(barmode="stack", height=280,
                                      margin=dict(t=20, b=30),
                                      legend=dict(orientation="h", y=1.1))
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(grp[["Department","Critical","Non-Critical","Total"]],
                                 use_container_width=True, hide_index=True)

# ── Frequency Distribution ────────────────────────────────────────────────────

with atab3:
    st.markdown("### Frequency Distribution — All Vessels")
    st.markdown("Maintenance interval spread across the fleet. Side-by-side for direct comparison.")

    dist_frames = []
    for df, name in zip(vessels_df, vessel_names):
        if "Frequency" not in df.columns:
            continue
        counts = df["Frequency"].value_counts().reset_index()
        counts.columns = ["Frequency", "Count"]
        counts["Vessel"] = name
        dist_frames.append(counts)

    if dist_frames:
        dist_all = pd.concat(dist_frames, ignore_index=True)
        freq_order = (
            dist_all.assign(_s=dist_all["Frequency"].apply(freq_sort_key))
            .drop_duplicates("Frequency").sort_values("_s")["Frequency"].tolist()
        )
        fig_dist = px.bar(
            dist_all, x="Frequency", y="Count", color="Vessel",
            barmode="group",
            category_orders={"Frequency": freq_order},
            color_discrete_map=color_map,
            labels={"Count": "Number of Jobs", "Frequency": "Maintenance Interval"},
            height=480
        )
        fig_dist.update_layout(
            legend=dict(orientation="h", y=1.02),
            xaxis_tickangle=-45,
            margin=dict(t=40, b=110)
        )
        st.plotly_chart(fig_dist, use_container_width=True)

        st.markdown("#### Unique intervals per vessel (not shared across all vessels)")
        all_freqs = [set(df["Frequency"].dropna().unique()) for df in vessels_df]
        common_all = set.intersection(*all_freqs)

        uniq_cols = st.columns(n_vessels)
        for i, (name, freqs) in enumerate(zip(vessel_names, all_freqs)):
            unique_to = freqs - common_all
            with uniq_cols[i]:
                st.markdown(f"**{name}**")
                if unique_to:
                    udf = dist_frames[i][dist_frames[i]["Frequency"].isin(unique_to)][["Frequency","Count"]]
                    st.dataframe(udf.reset_index(drop=True), use_container_width=True, hide_index=True)
                else:
                    st.success("No unique intervals")


# ── Machinery Job Count Pivot ─────────────────────────────────────────────────

with atab4:
    st.markdown("### Machinery Job Count per Vessel")
    st.markdown(
        "Total number of PMS jobs assigned to each machinery across all uploaded vessels. "
        "Blank cells indicate the machinery is not present in that vessel's PMS."
    )

    # Build one long dataframe with vessel + machinery + job count
    mach_frames = []
    for df, name in zip(vessels_df, vessel_names):
        if "Machinery Location" not in df.columns:
            continue
        counts = (
            df.groupby("Machinery Location")
            .size()
            .reset_index(name=name)
        )
        mach_frames.append(counts.set_index("Machinery Location"))

    if mach_frames:
        # Outer join so all machinery from all vessels appear
        pivot = mach_frames[0]
        for frame in mach_frames[1:]:
            pivot = pivot.join(frame, how="outer")

        pivot = pivot.reset_index().rename(columns={"Machinery Location": "Machinery Location"})
        pivot = pivot.sort_values("Machinery Location").reset_index(drop=True)

        # Convert to int where possible (NaN stays as blank via styler)
        for col in vessel_names:
            if col in pivot.columns:
                pivot[col] = pd.to_numeric(pivot[col], errors="coerce")

        # Total column — sum across vessels
        pivot["Total (All Vessels)"] = pivot[vessel_names].sum(axis=1, skipna=True).astype(int)

        # Highlight cells where a vessel has NO jobs (missing machinery)
        def highlight_pivot(df):
            styles = pd.DataFrame("", index=df.index, columns=df.columns)
            for col in vessel_names:
                if col in df.columns:
                    styles[col] = df[col].apply(
                        lambda v: "background-color:#ffe0e0;color:#900" if pd.isna(v)
                        else "background-color:#e8f5e9" if v > 0
                        else ""
                    )
            styles["Total (All Vessels)"] = "font-weight:bold"
            return styles

        # Summary metrics
        total_machinery = len(pivot)
        all_cols = [c for c in vessel_names if c in pivot.columns]
        missing_counts = {name: int(pivot[name].isna().sum()) for name in all_cols}

        mc1, mc2 = st.columns([1, 3])
        with mc1:
            st.metric("Total Unique Machineries", total_machinery)
        with mc2:
            miss_cols = st.columns(len(all_cols))
            for idx, name in enumerate(all_cols):
                miss_cols[idx].metric(f"Not in {name}", missing_counts[name],
                                      delta=f"-{missing_counts[name]}" if missing_counts[name] else "0",
                                      delta_color="inverse")

        st.caption("🟢 Green = jobs exist  |  🔴 Red/blank = machinery absent from that vessel's PMS")

        # Optional filter
        mach_search = st.text_input("🔍 Search machinery name", placeholder="e.g. Main Engine, Pump, Boiler")
        display_pivot = pivot.copy()
        if mach_search:
            display_pivot = display_pivot[
                display_pivot["Machinery Location"].str.contains(mach_search, case=False, na=False)
            ]

        st.dataframe(
            display_pivot.reset_index(drop=True).style.apply(highlight_pivot, axis=None).format(
                {name: lambda v: "" if pd.isna(v) else str(int(v)) for name in vessel_names}
            ),
            use_container_width=True,
            height=520
        )

        # Add pivot to download
        st.session_state["machinery_pivot"] = pivot


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("⬇️ Download Full Gap Report")

export_sheets = {}
for i, j in pairs:
    mj, mi, fm = pair_results[(i, j)]
    ni, nj = vessel_names[i], vessel_names[j]
    export_sheets[f"Missing in {nj}"[:31]]    = mj
    export_sheets[f"Missing in {ni}"[:31]]    = mi
    export_sheets[f"FreqMM {ni[:8]}-{nj[:8]}"[:31]] = fm

if "machinery_pivot" in st.session_state:
    export_sheets["Machinery Job Count"] = st.session_state["machinery_pivot"]

excel_data = to_excel(export_sheets)
pair_str   = "_".join(vessel_names)

st.download_button(
    label="📥 Download Full Report (.xlsx)",
    data=excel_data,
    file_name=f"PMS_Comparison_{pair_str[:60]}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary"
)
