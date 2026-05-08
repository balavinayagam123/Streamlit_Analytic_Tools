import streamlit as st
import pandas as pd
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Machinery Report | PMS Checker", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #F8F9FB; }
[data-testid="stSidebar"] { background: #003963; }
[data-testid="stSidebar"] * { color: #E8EDF2 !important; }
.section-header { font-size: 11px; font-weight: 700; color: #6B7280;
  text-transform: uppercase; letter-spacing: .06em; margin: 18px 0 6px; }
div[data-testid="metric-container"] { background: white; border: 0.5px solid #E0E5EC;
  border-radius: 8px; padding: 10px 14px; }
.col-legend { background: white; border: 0.5px solid #E0E5EC; border-radius: 8px;
  padding: 8px 14px; margin-bottom: 12px; font-size: 12px; }
.anom-banner { background: #FAEEDA; border: 1px solid #EF9F27; border-radius: 6px;
  padding: 8px 12px; font-size: 12px; color: #633806; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙ PMS Checker")
    st.markdown("---")
    st.page_link("pages/1_Upload.py", label="📤 Upload & Configure")
    st.page_link("pages/2_Report.py", label="📊 Machinery Report")
    st.page_link("pages/3_Admin.py",  label="⚙ Admin — Registry")
    st.markdown("---")
    if "vessel_name" in st.session_state:
        st.caption("CURRENT SESSION")
        st.markdown(f"**{st.session_state.vessel_name}**")

# ── Guard ─────────────────────────────────────────────────────────────────────
if "analysis_results" not in st.session_state:
    st.warning("No analysis results yet. Go to **Upload & Configure** and run the check first.")
    st.stop()

results      = st.session_state["analysis_results"]
vessel_name  = st.session_state.get("vessel_name", "Vessel")
vessel_prof  = st.session_state.get("vessel_profile", {})
report_date  = datetime.date.today().strftime("%d %b %Y")

sc   = results["scorecard"]
me   = results["me_unit_completeness"]
ae   = results["ae_subcomponent_completeness"]
crit = results["critical_machinery_jobs"]
vs   = results["vessel_specific_jobs"]
rank = results["rank_violations"]
lf   = results["low_freq_distribution"]
dups = results["duplicate_jobs"]
mf   = results["motors_fans"]
miss = results["missing_machineries"]
src  = results["job_source_breakdown"]
sys_cov = results["system_coverage"]

# ── Title + export buttons ────────────────────────────────────────────────────
title_col, exp_col1, exp_col2 = st.columns([5, 1, 1])
title_col.title(f"Machinery Report  ·  {vessel_name}")
title_col.caption(f"Report date: {report_date}  ·  Total jobs analysed: {sc['total_jobs']:,}")

# PDF export
with exp_col1:
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if st.button("⬇ Export PDF", type="primary", use_container_width=True):
        with st.spinner("Generating PDF..."):
            try:
                from engine.pdf_export import build_pdf
                inc_raw  = st.session_state.get("pdf_inc_raw", True)
                inc_anom = st.session_state.get("pdf_inc_anom", True)
                pdf_bytes = build_pdf(results, vessel_name, report_date, inc_raw, inc_anom)
                st.download_button(
                    "📄 Download PDF",
                    data=pdf_bytes,
                    file_name=f"PMS_Sufficiency_{vessel_name.replace(' ','_')}_{report_date.replace(' ','')}.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"PDF generation failed: {e}")

with exp_col2:
    st.markdown("&nbsp;", unsafe_allow_html=True)
    # Excel export — build a multi-sheet xlsx in memory
    if st.button("⬇ Export Excel", use_container_width=True):
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame(crit).to_excel(writer, sheet_name="Critical Jobs", index=False)
            pd.DataFrame(dups).to_excel(writer, sheet_name="Duplicates",    index=False)
            pd.DataFrame(miss, columns=["Missing Machinery"]).to_excel(writer, sheet_name="Missing Machineries", index=False)
            if not isinstance(lf, pd.DataFrame) or lf.empty:
                lf_df = pd.DataFrame()
            else:
                lf_df = lf
            lf_df.to_excel(writer, sheet_name="Rank Load")
        st.download_button(
            "📊 Download Excel",
            data=buf.getvalue(),
            file_name=f"PMS_Sufficiency_{vessel_name.replace(' ','_')}_{report_date.replace(' ','')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ── PDF options expander ──────────────────────────────────────────────────────
with st.expander("PDF export options", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    st.session_state["pdf_inc_raw"]  = c1.checkbox("Include raw job tables", value=True)
    st.session_state["pdf_inc_anom"] = c2.checkbox("Include anomaly callouts", value=True)
    c3.checkbox("Anglo-Eastern header/footer", value=True)
    c4.checkbox("Executive summary only", value=False)

# ── Column colour legend ──────────────────────────────────────────────────────
st.markdown("""
<div class="col-legend">
  <strong>Column key:</strong>&nbsp;&nbsp;
  <span style="background:#E6F1FB;color:#185FA5;padding:2px 8px;border-radius:99px;font-weight:600;font-size:11px">Generic</span>
  &nbsp;Generic library jobs&nbsp;&nbsp;&nbsp;
  <span style="background:#EAF3DE;color:#3B6D11;padding:2px 8px;border-radius:99px;font-weight:600;font-size:11px">SMS</span>
  &nbsp;Company SMS-referenced&nbsp;&nbsp;&nbsp;
  <span style="background:#EEEDFE;color:#534AB7;padding:2px 8px;border-radius:99px;font-weight:600;font-size:11px">Maker / IM</span>
  &nbsp;Instruction manual jobs&nbsp;&nbsp;&nbsp;
  <span style="background:#FAEEDA;color:#854F0B;padding:2px 8px;border-radius:99px;font-weight:600;font-size:11px">⚠ Anomaly</span>
  &nbsp;Count differs across units — investigate
</div>
""", unsafe_allow_html=True)

# ── Scorecard ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Go-live readiness scorecard</div>', unsafe_allow_html=True)

def score_color(v, good=90, warn=75):
    if v >= good: return "normal"
    if v >= warn: return "off"
    return "inverse"

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Overall readiness",       f"{sc['overall']}%",              delta="Needs attention" if sc['overall'] < 90 else "On track", delta_color=score_color(sc['overall']))
m2.metric("Equipment completeness",  f"{sc['equipment_completeness']}%", delta=f"{len(miss)} missing", delta_color="inverse" if miss else "normal")
m3.metric("SMS job coverage",        f"{sc['sms_coverage']}%",          delta_color=score_color(sc['sms_coverage']))
m4.metric("Rank compliance",         f"{sc['rank_compliance']}%",        delta=f"{rank['total']} violations", delta_color="inverse" if rank['total'] else "normal")
m5.metric("Duplicate ratio",         f"{sc['duplicate_ratio']}%",        delta=f"{sum(r['duplicates'] for r in dups)} instances", delta_color="inverse" if dups else "normal")
m6.metric("Critical jobs configured",f"{sc['critical_jobs_configured']:,}", delta_color="normal")

# ── System coverage + Top gaps + Job sources ──────────────────────────────────
st.markdown('<div class="section-header">System coverage overview</div>', unsafe_allow_html=True)
col_sys, col_gaps_src = st.columns([1.1, 1])

with col_sys:
    status_icon = {"Good": "🟢", "Review": "🟠", "Action needed": "🔴"}
    sys_rows = [{"System": r["system"], "Coverage": f"{r['coverage_pct']}%",
                 "Missing": r["missing"], "Status": status_icon.get(r["status"],"") + " " + r["status"]}
                for r in sys_cov]
    st.dataframe(pd.DataFrame(sys_rows), use_container_width=True, hide_index=True)

with col_gaps_src:
    st.markdown("**Top 5 gaps by criticality**")
    top5 = sorted(crit, key=lambda x: x["total"])[:5]
    for r in reversed(top5):
        cols = st.columns([3, 1, 1])
        cols[0].markdown(r["machinery"])
        cols[1].markdown(f"`{r['total']} missing`")
        cols[2].markdown("🔴 Critical" if r["total"] > 40 else "🟠 High" if r["total"] > 20 else "🟡 Medium")

    st.markdown("**Job source breakdown**")
    for r in src:
        pct = r["pct"]
        color = "#185FA5" if r["source"] == "Maker / IM" else "#3B6D11" if r["source"] == "SMS" else "#BA7517"
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px">
          <span>{r['source']}</span>
          <span style="color:{color};font-weight:600">{r['count']:,} &nbsp;<span style="color:#9CA3AF;font-weight:400">{pct}%</span></span>
        </div>
        <div style="background:#E5E7EB;border-radius:4px;height:5px;margin-bottom:6px">
          <div style="width:{pct}%;height:5px;border-radius:4px;background:{color}"></div>
        </div>""", unsafe_allow_html=True)

# ── Critical machinery jobs table ─────────────────────────────────────────────
st.markdown('<div class="section-header">Critical machinery jobs</div>', unsafe_allow_html=True)

def style_crit(df):
    def color_col(s, col_color):
        return [f"color:{col_color};font-weight:600" for _ in s]
    styled = df.style
    if "Generic" in df.columns:
        styled = styled.apply(color_col, col_color="#185FA5", subset=["Generic"])
    if "SMS" in df.columns:
        styled = styled.apply(color_col, col_color="#3B6D11", subset=["SMS"])
    if "Maker" in df.columns:
        styled = styled.apply(color_col, col_color="#534AB7", subset=["Maker"])
    return styled

crit_df = pd.DataFrame(crit).rename(columns={"machinery":"Machinery","generic":"Generic","sms":"SMS","maker":"Maker","total":"Total"})
crit_df["Generic"] = crit_df["Generic"].replace(0, "—")
crit_df["SMS"]     = crit_df["SMS"].replace(0, "—")
crit_df["Maker"]   = crit_df["Maker"].replace(0, "—")

# Add totals row
totals_row = pd.DataFrame([{"Machinery": "**TOTAL**",
    "Generic": crit_df[crit_df["Generic"] != "—"]["Generic"].astype(int).sum(),
    "SMS":     crit_df[crit_df["SMS"] != "—"]["SMS"].astype(int).sum(),
    "Maker":   crit_df[crit_df["Maker"] != "—"]["Maker"].astype(int).sum(),
    "Total":   crit_df["Total"].sum()}])
crit_display = pd.concat([crit_df, totals_row], ignore_index=True)
st.dataframe(style_crit(crit_display), use_container_width=True, hide_index=True)

# ── ME & AE completeness ──────────────────────────────────────────────────────
st.markdown('<div class="section-header">Engine unit completeness</div>', unsafe_allow_html=True)
col_me, col_ae = st.columns(2)

def highlight_anomalies(df, anomaly_cols_map: dict):
    """anomaly_cols_map = {col_name: [row_labels_with_anomaly]}"""
    def styler(v):
        return ""
    styled = df.style
    for col, bad_rows in anomaly_cols_map.items():
        if col not in df.columns:
            continue
        def highlight(val, col=col, bad_rows=bad_rows, df=df):
            return [
                "background-color:#FAEEDA;color:#854F0B;font-weight:bold"
                if (df.index[i] in bad_rows or str(df.index[i]) in [str(r) for r in bad_rows]) else ""
                for i, val_ in enumerate(val)
            ]
        styled = styled.apply(highlight, subset=[col])
    return styled

def style_unit_table(df: pd.DataFrame, anom_cells: set) -> pd.DataFrame:
    """
    Build a same-shape DataFrame of CSS strings.
    anom_cells = set of (row_label, col_name) tuples that should be highlighted.
    """
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for row_label, col_name in anom_cells:
        if row_label in styles.index and col_name in styles.columns:
            styles.loc[row_label, col_name] = "background-color:#FAEEDA;color:#854F0B;font-weight:bold"
    # Green for Total column
    if "Total" in styles.columns:
        for row_label in styles.index:
            if styles.loc[row_label, "Total"] == "":
                styles.loc[row_label, "Total"] = "color:#3B6D11;font-weight:bold"
    return styles

with col_me:
    n_cyl = len(me.get("units", []))
    st.markdown(f"**ME cylinder unit completeness** · {n_cyl} × 8 = {n_cyl * 8} jobs")
    if me.get("units"):
        # Build display DataFrame — keep full column names (no truncation)
        me_rows = {}
        for unit in me["units"]:
            label = unit.replace("Cylinder Unit#", "#")
            me_rows[label] = {sc: me["table"][unit].get(sc, 0) for sc in me["sub_components"]}
            me_rows[label]["Total"] = me["table"][unit].get("Total", 0)

        me_totals = {sc: me["totals"].get(sc, 0) for sc in me["sub_components"]}
        me_totals["Total"] = me.get("grand_total", 0)
        me_rows["Total"] = me_totals

        me_df = pd.DataFrame(me_rows).T

        # Build anomaly cell set using exact column names (no truncation)
        me_anom_cells = set()
        for sc, bad_units in me.get("anomalies", {}).items():
            for unit in bad_units:
                row_label = unit.replace("Cylinder Unit#", "#")
                if sc in me_df.columns:
                    me_anom_cells.add((row_label, sc))
            # Also flag the Total column for that row
            if bad_units:
                me_anom_cells.add(("Total", "Total"))

        me_styles = style_unit_table(me_df, me_anom_cells)
        st.dataframe(
            me_df.style.apply(lambda _: me_styles, axis=None),
            use_container_width=True,
        )

        for sc, bad_units in me.get("anomalies", {}).items():
            if bad_units:
                labels = ", ".join(u.replace("Cylinder Unit#", "#") for u in bad_units)
                st.markdown(
                    f'<div class="anom-banner">⚠ <strong>{sc}</strong>: '
                    f'inconsistent job count across {labels}. Investigate missing jobs.</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("ME sub-component data not available — check Machinery Location and Sub Component columns.")

with col_ae:
    n_ae = len(ae.get("engines", []))
    st.markdown(f"**AE sub-component completeness** · {n_ae} engines")
    if ae.get("engines"):
        ae_rows = {}
        for eng in ae["engines"]:
            label = eng.replace("Auxiliary Engine#", "AE #")
            ae_rows[label] = {sc: ae["table"][eng].get(sc, 0) for sc in ae["sub_components"]}
            ae_rows[label]["Total"] = ae["table"][eng].get("Total", 0)

        ae_totals = {sc: ae["totals"].get(sc, 0) for sc in ae["sub_components"]}
        ae_totals["Total"] = ae.get("grand_total", 0)
        ae_rows["Total"] = ae_totals

        ae_df = pd.DataFrame(ae_rows).T

        # Build anomaly cell set
        ae_anom_cells = set()
        for sc, bad_engs in ae.get("anomalies", {}).items():
            for eng in bad_engs:
                row_label = eng.replace("Auxiliary Engine#", "AE #")
                if sc in ae_df.columns:
                    ae_anom_cells.add((row_label, sc))
            if bad_engs:
                ae_anom_cells.add(("Total", "Total"))

        ae_styles = style_unit_table(ae_df, ae_anom_cells)
        st.dataframe(
            ae_df.style.apply(lambda _: ae_styles, axis=None),
            use_container_width=True,
        )

        for sc, bad_engs in ae.get("anomalies", {}).items():
            if bad_engs:
                labels = ", ".join(e.replace("Auxiliary Engine#", "AE #") for e in bad_engs)
                st.markdown(
                    f'<div class="anom-banner">⚠ <strong>{sc}</strong>: '
                    f'inconsistent job count across {labels}.</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("AE sub-component data not available.")

# ── Vessel-specific machinery ─────────────────────────────────────────────────
if vs:
    st.markdown('<div class="section-header">Vessel-specific machinery</div>', unsafe_allow_html=True)
    vs_df = pd.DataFrame(vs).rename(columns={"machinery":"Machinery","generic":"Generic","sms":"SMS","maker":"Maker","total":"Total"})
    vs_df["Generic"] = vs_df["Generic"].replace(0, "—")
    vs_df["SMS"]     = vs_df["SMS"].replace(0, "—")
    vs_df["Maker"]   = vs_df["Maker"].replace(0, "—")
    st.dataframe(style_crit(vs_df), use_container_width=True, hide_index=True)

# ── Rank violations + Low-frequency load ─────────────────────────────────────
st.markdown('<div class="section-header">Rank analysis</div>', unsafe_allow_html=True)
col_rank, col_lf = st.columns(2)

with col_rank:
    st.markdown("**Performing rank violations**")
    rank_data = {
        "Violation": ["Engine dept → Chief Officer","Engine dept → Master","Engine dept → 3rd Officer","Electrical → Deck Officers"],
        "Count": [rank["engine_to_co"], rank["engine_to_master"], rank["engine_to_3o"], rank["electrical_to_deck"]],
    }
    rank_df = pd.DataFrame(rank_data)
    rank_df.loc[len(rank_df)] = ["Total", rank["total"]]
    st.dataframe(rank_df, use_container_width=True, hide_index=True)

with col_lf:
    st.markdown("**Low-frequency job load by rank (≤4 months)**")
    if isinstance(lf, pd.DataFrame) and not lf.empty:
        st.dataframe(lf, use_container_width=True)
    else:
        st.info("Frequency data not available in vessel export.")

# ── Duplicates + Motors/fans ──────────────────────────────────────────────────
st.markdown('<div class="section-header">Duplicate jobs &amp; motors/fans</div>', unsafe_allow_html=True)
col_dup, col_mf = st.columns(2)

with col_dup:
    st.markdown("**Duplicate job analysis**")
    if dups:
        dup_df = pd.DataFrame(dups).rename(columns={"machinery":"Machinery","duplicates":"Duplicates","severity":"Severity"})
        dup_df.loc[len(dup_df)] = ["Grand Total", sum(r["duplicates"] for r in dups), ""]
        def color_severity(val):
            m = {"Critical":"background-color:#FCEBEB;color:#A32D2D",
                 "High":"background-color:#FAEEDA;color:#854F0B",
                 "Medium":"background-color:#E6F1FB;color:#185FA5"}
            return m.get(val, "")
        st.dataframe(
            dup_df.style.applymap(color_severity, subset=["Severity"]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("No duplicates detected.")

with col_mf:
    st.markdown("**Motors & fans with > 3 jobs**")
    if mf:
        color_map = {"danger":"#FCEBEB", "warning":"#FAEEDA", "info":"#E6F1FB"}
        text_map  = {"danger":"#A32D2D", "warning":"#854F0B", "info":"#185FA5"}
        for item in mf[:15]:
            bg = color_map.get(item["color"], "#F3F4F6")
            tc = text_map.get(item["color"],  "#374151")
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:4px 8px;'
                f'background:{bg};border-radius:4px;margin-bottom:3px;font-size:12px">'
                f'<span style="color:{tc}">{item["sub_component"]}</span>'
                f'<span style="color:{tc};font-weight:600">{item["job_count"]}</span></div>',
                unsafe_allow_html=True,
            )
        if len(mf) > 15:
            st.caption(f"+ {len(mf)-15} more items")
    else:
        st.success("No motor/fan items with > 3 jobs.")

# ── Missing machineries ───────────────────────────────────────────────────────
st.markdown('<div class="section-header">Missing machineries ({} items)</div>'.format(len(miss)), unsafe_allow_html=True)
if miss:
    html_chips = "".join(
        f'<span style="display:inline-block;background:#FCEBEB;color:#A32D2D;'
        f'padding:3px 9px;border-radius:4px;margin:2px;font-size:11px;font-weight:500">{m}</span>'
        for m in miss
    )
    st.markdown(html_chips, unsafe_allow_html=True)
else:
    st.success("No missing machineries — all canonical machinery items are present in the vessel PMS.")
