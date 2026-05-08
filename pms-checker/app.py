import streamlit as st

st.set_page_config(
    page_title="PMS Data Sufficiency Check",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #F8F9FB; }
[data-testid="stSidebar"] { background: #003963; }
[data-testid="stSidebar"] * { color: #E8EDF2 !important; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙ PMS Checker")
    st.markdown("**Anglo-Eastern Ship Management**")
    st.markdown("---")
    st.page_link("pages/1_Upload.py", label="📤 Upload & Configure")
    st.page_link("pages/2_Report.py", label="📊 Machinery Report")
    st.page_link("pages/3_Admin.py",  label="⚙ Admin — Registry")
    st.markdown("---")
    st.caption("v1.0  ·  Digital Solutions")

st.title("PMS Data Sufficiency Check")
st.markdown("""
Welcome to the PMS Data Sufficiency Check tool — an Anglo-Eastern Digital Solutions tool
for verifying PMS vessel data quality before system go-live.

**Get started:**
1. Go to **📤 Upload & Configure** — upload your PMS vessel export and reference sheet
2. Select the vessel profile and confirm column mappings
3. Click **Run Sufficiency Check**
4. View the full **📊 Machinery Report** with all gap analysis, anomaly highlights, and coverage scores
5. Export to PDF or Excel for superintendent / vendor handoff

Use **⚙ Admin — Registry** to manage transform maps, vessel profiles, and reference library versions.
""")

col1, col2, col3 = st.columns(3)
col1.metric("Canonical machineries tracked", "200+")
col2.metric("Critical machineries monitored", "34")
col3.metric("SMS job library size", "1,236")

st.divider()
st.page_link("pages/1_Upload.py", label="→ Start: Upload & Configure", use_container_width=False)
