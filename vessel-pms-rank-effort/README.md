# Vessel PMS – Rank Reporting Effort

A Streamlit tool that estimates how many planned-maintenance job reports each
onboard rank must submit over a chosen period, based on the job's reporting
frequency in a JiBe (or similar) PMS export.

## Quick start (local)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## What it does

1. Upload a PMS job export (`.csv` or `.xlsx`) — e.g. JiBe "Export to Excel"
   from **Planned Maintenance → Jobs**.
2. Pick a reporting period in the sidebar: **1 Week, 1 Month, 3 Months, 6 Months**.
3. Optional filters: Department, Function, Job Status, Critical-only, and
   which ranks to include.

### Rank Reporting Effort

For every job, the app converts its `Frequency` (e.g. `7 Days`, `3 Months`)
into a days-per-occurrence value, then computes:

- **Est. Reports in period** = `period length ÷ job frequency`, summed per
  rank — the statistical average number of job reports that rank must submit
  in the selected window.
- **Jobs Due ≥1x in period** — jobs whose frequency is short enough to come
  due at least once in the period.

Jobs with an `Hours`-based frequency (e.g. `8000 Hours`) depend on machinery
running hours, not the calendar, so they're excluded from the period effort
by default. Enable **"Include an estimate for running-hour jobs"** in the
sidebar and set an assumed average running-hours/day to fold them in as an
approximation.

Combined rank strings (e.g. `2nd Engineer,3rd Engineer,4th Engineer
(Senior)`) list a primary rank plus backup/alternate ranks that can also
cover the job. Only the **first-listed rank** is used for effort
attribution — the rest are ignored — so the rank list stays manageable and
effort isn't double-counted across alternates.

### Verifying effort

Two extra KPIs estimate the sign-off workload for supervisors, using the
same period and filters as everything else:

- **CE verifying effort** — sum of estimated reports for all engineer and
  electrical ranks' jobs, including the Chief Engineer's own.
- **Master verifying effort** — sum of estimated reports for Master, Chief
  Officer, 2nd Officer and 3rd Officer jobs.

All five KPIs are shown as a single row of boxed cards. The bar chart below
breaks each rank's jobs into **critical vs non-critical** counts, stacked in
two pastel colours with the counts labelled on each bar.

### Job Frequency Matrix by Rank

A Rank × Frequency pivot (with Grand Total row/column) showing job counts for
every frequency within the selected period (and running-hour threshold, if
enabled), heat-mapped on a blue sequential scale (light = low, dark = high) —
mirrors the classic "Low-Frequency Jobs by Performing Rank" Excel pivot used
for manning/workload reviews.

Both the summary table and the matrix can be exported to Excel.
