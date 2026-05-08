# PMS Data Sufficiency Check
**Anglo-Eastern Ship Management Ltd — Digital Solutions**

A Streamlit app for verifying PMS vessel data quality before system go-live.
Deployed via Streamlit Community Cloud from this GitHub repo.

---

## Quick start (local)

```bash
pip install -r requirements.txt --break-system-packages
streamlit run app.py
```

## Streamlit Community Cloud deployment

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Select repo, branch `main`, main file `app.py`
4. Under **Settings → Secrets**, add:

```toml
GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"
GITHUB_REPO  = "your-org/pms-checker"
```

The token needs `repo` scope (read + write contents).

---

## Project structure

```
pms_checker/
├── app.py                      # Home / landing page
├── pages/
│   ├── 1_Upload.py             # Upload & Configure
│   ├── 2_Report.py             # Machinery Report dashboard
│   └── 3_Admin.py              # Admin — Registry
├── engine/
│   ├── loader.py               # File reading, JSON reference data
│   ├── matcher.py              # rapidfuzz name resolution
│   ├── gap_analysis.py         # Core analysis engine
│   ├── github_writer.py        # GitHub API persistence
│   └── pdf_export.py           # WeasyPrint PDF generation
├── data/
│   ├── transform_map.json      # Machinery name variant → canonical
│   ├── matching_titles.json    # Job code alias map
│   └── vessel_profiles.json    # Per-vessel configuration
├── .streamlit/
│   └── config.toml             # Theme (Anglo-Eastern brand colours)
└── requirements.txt
```

---

## Usage workflow

### Each session

1. **Upload & Configure** — upload:
   - Vessel data export (`.xlsx` or `.csv`) — PMS export from JiBe/Amos/DANAOS etc.
   - Reference Sheet (`Reference_Sheet.xlsx`) — AESM SMS library
2. Select vessel profile (drives which reference sheet tabs are used)
3. Review column mapping validation — remap if headers differ
4. Accept any unresolved machinery name variants (rapidfuzz suggestions shown)
5. Click **Run Sufficiency Check**

### Machinery Report

All sections computed from the uploaded data:
- Go-live readiness scorecard (6 KPIs)
- System coverage overview (Good / Review / Action needed)
- Critical machinery jobs (Generic / SMS / Maker colour-coded)
- ME cylinder unit completeness with anomaly highlighting
- AE sub-component completeness with anomaly highlighting
- Vessel-specific machinery coverage
- Rank violations and low-frequency job distribution
- Duplicate job analysis
- Motors & fans overloaded items
- Missing machineries list
- PDF export (Anglo-Eastern branded) and Excel export

### Admin — Registry

Persistent reference data editable in-place:
- **Transform Map** — machinery name variant → canonical mappings (grow over time)
- **Job Code Aliases** — from Reference Sheet 'Matching Titles' tab
- **Vessel Profiles** — per-vessel engine type, BWTS maker, SCR, cylinder count
- **Reference Library** — version audit of loaded sheets

All Admin changes save to local `data/*.json` AND push to GitHub
(if `GITHUB_TOKEN` and `GITHUB_REPO` are configured in secrets).

---

## Data persistence model

```
GitHub repo (data/*.json)     ← persistent, survives container restarts
Streamlit session_state       ← current session only (uploaded files, results)
Streamlit Community Cloud     ← ephemeral container, no local file writes
```

Reference Sheet xlsx is NOT stored — it is uploaded fresh each session (Option A).
This keeps the library version explicit and avoids stale data.

---

## Anomaly detection logic

**ME cylinder unit completeness:**
For each sub-component column, the modal value across all units is computed.
Any cell that deviates from the modal is highlighted amber with a callout banner below.

**AE sub-component completeness:**
Same logic — modal across AE #1, #2, #3. Any engine with a different count is highlighted.

---

*Anglo-Eastern Digital Solutions · Built May 2026*
