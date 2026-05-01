import streamlit as st
import pandas as pd
import io

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

# ── Gate: show landing if no data yet ────────────────────────────────────────

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

# ── Parse CSVs from stored bytes (always fresh, no pickle issues) ─────────────

df_a = load_csv(st.session_state["bytes_a"])
df_b = load_csv(st.session_state["bytes_b"])

vessel_a = get_vessel_name(df_a)
vessel_b = get_vessel_name(df_b)

missing_b, missing_a, freq_mismatch = compare(df_a, df_b, vessel_a, vessel_b)

# ── Summary metrics ───────────────────────────────────────────────────────────

st.subheader("📊 Summary")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(f"Total Jobs — {vessel_a}", len(df_a))
c2.metric(f"Total Jobs — {vessel_b}", len(df_b))
c3.metric(f"Missing in {vessel_b}", len(missing_b), delta=f"-{len(missing_b)}", delta_color="inverse")
c4.metric(f"Missing in {vessel_a}", len(missing_a), delta=f"-{len(missing_a)}", delta_color="inverse")
c5.metric("Frequency Mismatches", len(freq_mismatch), delta=f"{len(freq_mismatch)}", delta_color="inverse")

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────

with st.expander("🔧 Filter Results", expanded=False):
    col1, col2, col3, col4 = st.columns(4)

    all_dept = sorted({v for v in df_a["Department"].tolist() + df_b["Department"].tolist()
                       if v not in ("", "nan", "None")})
    all_fn = sorted({v for v in df_a["Function"].tolist() + df_b["Function"].tolist()
                     if v not in ("", "nan", "None")})
    all_machinery = sorted({v for v in df_a["Machinery Location"].tolist() + df_b["Machinery Location"].tolist()
                            if v not in ("", "nan", "None")})

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

# ── Results tabs ──────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    f"❌ Missing in {vessel_b} ({len(mb)})",
    f"❌ Missing in {vessel_a} ({len(ma)})",
    f"⚠️ Frequency Mismatches ({len(fm)})"
])

with tab1:
    st.markdown(f"Jobs present in **{vessel_a}** but **not found** in **{vessel_b}**.")
    if mb.empty:
        st.success("No missing jobs found.")
    else:
        st.dataframe(mb.reset_index(drop=True), use_container_width=True, height=450)

with tab2:
    st.markdown(f"Jobs present in **{vessel_b}** but **not found** in **{vessel_a}**.")
    if ma.empty:
        st.success("No missing jobs found.")
    else:
        st.dataframe(ma.reset_index(drop=True), use_container_width=True, height=450)

with tab3:
    st.markdown(f"Jobs that exist in **both** vessels but have **different maintenance frequencies**.")
    if fm.empty:
        st.success("No frequency mismatches found.")
    else:
        st.dataframe(fm.reset_index(drop=True), use_container_width=True, height=450)

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
