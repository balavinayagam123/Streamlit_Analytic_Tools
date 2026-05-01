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

def load_csv(uploaded_file):
    """Read JiBe CSV and rename unnamed columns."""
    df = pd.read_csv(uploaded_file, header=0, dtype=str)

    # Column 1 (index 1) = Critical flag
    cols = df.columns.tolist()
    cols[1] = "Critical"
    # Column 2 is always empty in JiBe exports — drop it
    df.columns = cols
    if "Unnamed: 2" in df.columns:
        df = df.drop(columns=["Unnamed: 2"])

    # Normalise key text columns (whitespace only — no value changes)
    for col in ["Job Code", "Machinery Location", "Sub Component Location",
                "Frequency", "Job Action", "Title", "Function", "Department"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def compare(df_a, df_b, vessel_a, vessel_b):
    """Return three DataFrames: missing_in_b, missing_in_a, freq_mismatches."""

    # Job Code is the unique identifier in JiBe
    set_a = set(df_a["Job Code"].dropna())
    set_b = set(df_b["Job Code"].dropna())

    # ── Missing jobs ──────────────────────────────────────────────────────────
    cols_show = ["Job Code", "Critical", "Machinery Location", "Sub Component Location",
                 "Frequency", "Job Action", "Title", "Function", "Department"]

    missing_in_b = df_a[df_a["Job Code"].isin(set_a - set_b)][
        [c for c in cols_show if c in df_a.columns]
    ].copy()

    missing_in_a = df_b[df_b["Job Code"].isin(set_b - set_a)][
        [c for c in cols_show if c in df_b.columns]
    ].copy()

    # ── Frequency mismatches (jobs present in both) ──────────────────────────
    # Compare frequency as raw string — no conversion
    common_codes = set_a & set_b
    merged = pd.merge(
        df_a[df_a["Job Code"].isin(common_codes)][
            ["Job Code", "Critical", "Machinery Location", "Sub Component Location",
             "Frequency", "Job Action", "Title", "Function", "Department"]
        ],
        df_b[df_b["Job Code"].isin(common_codes)][
            ["Job Code", "Frequency"]
        ],
        on="Job Code",
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
    """Write multiple DataFrames to an in-memory Excel workbook."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()


# ── Sidebar — file upload ─────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 Upload PMS Exports")
    st.markdown("Export pending jobs from JiBe for each vessel and upload the CSV files below.")

    file_a = st.file_uploader("Vessel A — CSV", type=["csv"], key="vessel_a")
    vessel_a_name = st.text_input("Vessel A Name", value="Vessel A")

    st.divider()

    file_b = st.file_uploader("Vessel B — CSV", type=["csv"], key="vessel_b")
    vessel_b_name = st.text_input("Vessel B Name", value="Vessel B")

    run = st.button("🔍 Run Comparison", type="primary", use_container_width=True)

# ── Main panel ────────────────────────────────────────────────────────────────

if not run:
    st.info("👈  Upload two JiBe PMS CSV exports in the sidebar and click **Run Comparison**.")

    with st.expander("ℹ️  How to export from JiBe"):
        st.markdown("""
1. In JiBe, go to **Planned Maintenance → Jobs**
2. Filter by vessel and status = **Pending**
3. Click **Export to Excel** (saves as CSV)
4. Upload both files in the sidebar
        """)
    st.stop()

if not file_a or not file_b:
    st.warning("Please upload CSV files for **both** vessels before running.")
    st.stop()

# ── Load & compare ────────────────────────────────────────────────────────────

with st.spinner("Comparing PMS data…"):
    df_a = load_csv(file_a)
    df_b = load_csv(file_b)

    missing_b, missing_a, freq_mismatch = compare(df_a, df_b, vessel_a_name, vessel_b_name)

# ── Summary metrics ───────────────────────────────────────────────────────────

st.subheader("📊 Summary")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(f"Total Jobs — {vessel_a_name}", len(df_a))
c2.metric(f"Total Jobs — {vessel_b_name}", len(df_b))
c3.metric(f"Missing in {vessel_b_name}", len(missing_b), delta=f"-{len(missing_b)}", delta_color="inverse")
c4.metric(f"Missing in {vessel_a_name}", len(missing_a), delta=f"-{len(missing_a)}", delta_color="inverse")
c5.metric("Frequency Mismatches", len(freq_mismatch), delta=f"{len(freq_mismatch)}", delta_color="inverse")

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────

with st.expander("🔧 Filter Results", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        dept_filter = st.multiselect(
            "Department",
            options=sorted(set(df_a["Department"].dropna().unique()) |
                           set(df_b["Department"].dropna().unique()))
        )
    with col2:
        fn_options = sorted(set(df_a["Function"].dropna().unique()) |
                            set(df_b["Function"].dropna().unique()))
        fn_filter = st.multiselect("Function", options=fn_options)
    with col3:
        critical_only = st.checkbox("Critical jobs only (C flag)")


def apply_filters(df):
    if dept_filter and "Department" in df.columns:
        df = df[df["Department"].isin(dept_filter)]
    if fn_filter and "Function" in df.columns:
        df = df[df["Function"].isin(fn_filter)]
    if critical_only and "Critical" in df.columns:
        df = df[df["Critical"] == "C"]
    return df


mb = apply_filters(missing_b)
ma = apply_filters(missing_a)
fm = apply_filters(freq_mismatch)

# ── Results tabs ──────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    f"❌ Missing in {vessel_b_name} ({len(mb)})",
    f"❌ Missing in {vessel_a_name} ({len(ma)})",
    f"⚠️ Frequency Mismatches ({len(fm)})"
])

with tab1:
    st.markdown(f"Jobs present in **{vessel_a_name}** but **not found** in **{vessel_b_name}**.")
    if mb.empty:
        st.success("No missing jobs found.")
    else:
        st.dataframe(mb.reset_index(drop=True), use_container_width=True, height=450)

with tab2:
    st.markdown(f"Jobs present in **{vessel_b_name}** but **not found** in **{vessel_a_name}**.")
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
    f"Missing in {vessel_b_name}"[:31]: missing_b,
    f"Missing in {vessel_a_name}"[:31]: missing_a,
    "Frequency Mismatches": freq_mismatch
})

st.download_button(
    label="📥 Download Full Report (.xlsx)",
    data=excel_data,
    file_name=f"PMS_Comparison_{vessel_a_name}_vs_{vessel_b_name}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary"
)
