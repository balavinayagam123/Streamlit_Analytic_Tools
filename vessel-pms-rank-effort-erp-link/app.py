import subprocess
import sys

# Auto-install Playwright browsers if missing (for Streamlit Cloud)
def ensure_playwright_browsers():
    try:
        from playwright.sync_api import sync_playwright
        sync_playwright().__enter__()
    except Exception:
        print("Installing Playwright browsers...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)

ensure_playwright_browsers()

# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st

st.set_page_config(
    page_title="PMS Reporting Effort Dashboard",
    page_icon="🧭",
    layout="wide",
)

st.title("🧭 PMS Jobs Reporting & Verification Effort")
st.markdown(
    """
Welcome to the **PMS Jobs Reporting & Verification Effort Dashboard**.

This tool helps you estimate how many planned-maintenance job reports each rank must
submit — and how many each supervisor must verify — over a selected period, based on
the job's reporting frequency in your JiBe PMS export.

## 🚀 Quick Start

**Step 1:** Go to **📥 Fetch Data** (in the sidebar) to either:
- Upload a PMS export file (CSV or Excel)
- Fetch data directly from your JiBe ERP using an automated browser session

**Step 2:** Once data is loaded, click **📊 Analysis** to see:
- Rank-by-rank reporting effort over 1 week, 1 month, 3 months, 6 months
- Supervisor verification workload (Chief Engineer, Master)
- Critical vs non-critical job breakdown
- Short-cycle reporting load analysis
- Job frequency matrix by rank

## 📋 What You Need

Your PMS export must include these columns:
- **Frequency** (e.g., "7 Days", "3 Months", "8000 Hours")
- **Performing Rank** (e.g., "2nd Engineer,3rd Engineer" → only first rank used)

Optional columns for filtering:
- Department, Function, Job Status, Machinery Location, Job Source, Critical (C/blank)

## 💡 How It Works

1. **Frequency Parsing:** The app converts job frequencies into a daily reporting rate
2. **Period Calculation:** Multiplies daily rate × period length = expected reports in the period
3. **Rank Attribution:** Extracts the primary rank from combined strings (e.g., "2nd Engineer" from "2nd Engineer,3rd Engineer")
4. **Verification Logic:**
   - Chief Engineer verifies all engineer and electrical ranks' jobs
   - Master verifies deck officer jobs
   - Both supervisors verify their own jobs

## 🔧 Features

- **Period Selection:** Analyze over 1 week, 1 month, 3 months, or 6 months
- **Flexible Filters:** Department, function, job status, machinery, rank, critical jobs only
- **Running-Hour Jobs:** Optional estimation with assumed avg hours/day
- **Excel Export:** Download effort matrices and frequency pivot tables
- **Visual Analytics:**
  - Heatmaps for effort distribution
  - Stacked bar charts for critical/non-critical breakdown
  - Frequency band analysis to identify high-churn jobs

---

👈 Click **Fetch Data** in the sidebar to get started!
    """
)

col1, col2 = st.columns(2)
with col1:
    st.markdown("### 📥 Fetch Data")
    st.markdown(
        """
Upload a PMS export or fetch from JiBe using Playwright automation.
        """
    )
with col2:
    st.markdown("### 📊 Analysis")
    st.markdown(
        """
View effort matrices, charts, and detailed breakdowns by rank.
        """
    )
