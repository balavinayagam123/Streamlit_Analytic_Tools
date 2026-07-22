import io
import os
import tempfile
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Fetch PMS Data",
    page_icon="📥",
    layout="wide",
)

st.title("📥 Fetch PMS Data from JiBe")
st.markdown(
    "Connect to your JiBe ERP instance and download job data automatically, "
    "or upload an existing export to analyze."
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state for data storage
# ─────────────────────────────────────────────────────────────────────────────

if "fetched_data" not in st.session_state:
    st.session_state.fetched_data = None
if "data_source" not in st.session_state:
    st.session_state.data_source = None


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 1: Direct File Upload
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("Option 1: Upload PMS Export")
st.caption("Upload a CSV or Excel file exported from JiBe directly.")

uploaded_file = st.file_uploader(
    "Choose a PMS export file (CSV or Excel)",
    type=["csv", "xlsx", "xls"],
    key="upload_option",
)

if uploaded_file is not None:
    try:
        raw = uploaded_file.read()
        name = uploaded_file.name.lower()
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw), dtype=str)
        else:
            df = pd.read_csv(io.BytesIO(raw), dtype=str)

        st.session_state.fetched_data = df
        st.session_state.data_source = f"📄 Uploaded: {uploaded_file.name}"
        st.success(f"✅ Loaded {len(df)} jobs from {uploaded_file.name}")
    except Exception as e:
        st.error(f"Failed to load file: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 2: JiBe URL Input with Playwright
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("Option 2: Fetch via JiBe URL")
st.caption(
    "Paste the URL of your JiBe job status page, and we'll automate the export process."
)

with st.expander("ℹ️ How to get your JiBe URL", expanded=False):
    st.markdown(
        """
1. Log in to JiBe
2. Navigate to **Planned Maintenance → Jobs**
3. Filter by vessel and status as needed
4. Copy the URL from your browser's address bar
5. Paste it below

**Example URL:**
```
https://aesm.jibe.solutions/anglo/account/jibe2App.aspx?enc=...
```
        """
    )

jibe_url = st.text_input(
    "Paste your JiBe job status page URL:",
    placeholder="https://aesm.jibe.solutions/anglo/account/...",
    key="jibe_url_input",
)

if jibe_url:
    col1, col2 = st.columns([3, 1])
    with col2:
        fetch_method = st.selectbox(
            "Fetch method:",
            ["Playwright (Recommended)", "Manual Link"],
            index=0,
            help="Playwright automates login; Manual Link assumes you'll extract the file directly.",
        )

    if st.button("🚀 Fetch PMS Data", key="fetch_button"):
        with st.spinner("Fetching data from JiBe..."):
            try:
                if fetch_method == "Playwright (Recommended)":
                    # Ensure Playwright is installed
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "playwright", "install", "chromium"],
                            capture_output=True,
                            timeout=60
                        )
                    except Exception as install_err:
                        st.warning(f"Could not install Playwright: {install_err}")

                    try:
                        from playwright.sync_api import sync_playwright
                    except ImportError:
                        st.error(
                            "❌ Playwright is not available. Using manual method instead.\n\n"
                            "Go to the link below, export the file, and upload it above."
                        )
                        st.markdown(f"[Open JiBe Job Status]({jibe_url})")
                        st.stop()

                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        context = browser.new_context()
                        page = context.new_page()

                        st.info("📍 Navigating to JiBe job status page...")
                        page.goto(jibe_url, wait_until="networkidle", timeout=30000)
                        page.wait_for_load_state("networkidle")

                        st.info("🔍 Looking for export button...")
                        try:
                            page.click("button:has-text('Export')")
                            page.wait_for_load_state("networkidle")
                        except:
                            st.warning(
                                "Could not automatically click export button. "
                                "Try manual export via the link below."
                            )

                        browser.close()

                        st.success("✅ Playwright automation attempted. Check for downloads.")
                        st.info(
                            "💡 If the automated export didn't work, use the manual method: "
                            "go to the JiBe page, click Export → Excel, and upload the file above."
                        )

                else:  # Manual Link method
                    st.info("📖 Using manual export method:")
                    st.markdown(
                        f"""
1. Click this link to open JiBe: [{jibe_url}]({jibe_url})
2. On the job list, click **Export → Excel**
3. A file will download to your computer
4. Upload it using **Option 1** above
                        """
                    )

            except Exception as e:
                st.error(f"❌ Error during fetch: {e}")
                st.info("💡 Try uploading a file manually using Option 1 instead.")


# ─────────────────────────────────────────────────────────────────────────────
# DATA PREVIEW & VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

st.divider()

if st.session_state.fetched_data is not None:
    st.subheader("📋 Data Preview")
    st.markdown(f"**Source:** {st.session_state.data_source}")
    st.write(f"**Rows:** {len(st.session_state.fetched_data)}")
    st.write(f"**Columns:** {', '.join(st.session_state.fetched_data.columns)}")

    # Validate required columns
    required_cols = ["Frequency", "Performing Rank"]
    missing = [c for c in required_cols if c not in st.session_state.fetched_data.columns]

    if missing:
        st.error(
            f"⚠️ **Missing required columns:** {', '.join(missing)}\n\n"
            "Make sure your PMS export includes 'Frequency' and 'Performing Rank' columns."
        )
    else:
        st.success("✅ Data validation passed. All required columns found.")

        with st.expander("Preview first 10 rows"):
            st.dataframe(
                st.session_state.fetched_data.head(10), use_container_width=True
            )

        st.info(
            "📊 Ready to analyze! Click **Analysis** in the sidebar to proceed with the dashboard."
        )
else:
    st.info("👈 Upload or fetch data using one of the options above to get started.")
