import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.loader import (
    load_vessel_data, load_reference_sheet, load_transform_map,
    load_vessel_profiles, get_aesm_library, save_transform_map,
)
from engine.matcher import resolve_names, apply_resolutions
from engine.gap_analysis import run_analysis

st.set_page_config(page_title="Upload & Configure | PMS Checker", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #F8F9FB; }
[data-testid="stSidebar"] { background: #003963; }
[data-testid="stSidebar"] * { color: #E8EDF2 !important; }
div[data-testid="metric-container"] { background: white; border: 0.5px solid #E0E5EC;
  border-radius: 8px; padding: 12px 16px; }
.section-header { font-size: 11px; font-weight: 700; color: #6B7280;
  text-transform: uppercase; letter-spacing: .06em; margin: 16px 0 6px; }
.session-bar { background: #EAF3DE; border: 0.5px solid #3B6D11; border-radius: 8px;
  padding: 10px 16px; margin-bottom: 12px; font-size: 13px; color: #3B6D11; }
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
        if "analysis_results" in st.session_state:
            st.caption("✅ Analysis complete")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Upload & Configure")

# ── SESSION ACTIVE BANNER — shown when returning from Report page ─────────────
session_has_data = (
    "vessel_df_processed" in st.session_state and
    "vessel_name" in st.session_state
)

if session_has_data:
    vessel_name_active = st.session_state["vessel_name"]
    has_results = "analysis_results" in st.session_state

    st.markdown(f"""
    <div class="session-bar">
      ✅ <strong>Active session: {vessel_name_active}</strong>
      {"&nbsp;·&nbsp; Analysis complete — view the <a href='/2_Report' target='_self'>📊 Machinery Report</a>" if has_results else "&nbsp;·&nbsp; Files loaded, ready to run analysis"}
      &nbsp;·&nbsp; <em>Upload new files below only if you want to start a fresh analysis</em>
    </div>
    """, unsafe_allow_html=True)

    # Offer quick re-run with variant accepts applied (common use case from Report page)
    if has_results:
        col_rerun, col_clear = st.columns([2, 1])
        with col_rerun:
            if st.button("🔄 Re-run analysis (apply accepted mappings)", type="primary"):
                _df = st.session_state["vessel_df_processed"]
                _profile = st.session_state["vessel_profile"]
                _canonical = st.session_state.get("canonical_list", [])
                _critical  = st.session_state.get("critical_list", [])
                _vs        = st.session_state.get("vessel_specific", [])

                # Re-resolve with latest transform map (user may have accepted new mappings)
                _tm = load_transform_map()
                _raw_names = _df["Machinery Location"].dropna().unique().tolist() if "Machinery Location" in _df.columns else []
                _resolutions = resolve_names(_raw_names, _canonical, _tm)
                _df = apply_resolutions(_df, _resolutions)
                st.session_state["vessel_df_processed"] = _df

                with st.spinner("Re-running analysis with updated mappings..."):
                    try:
                        results = run_analysis(
                            vessel_df=_df,
                            canonical_machinery_list=_canonical,
                            critical_machinery_list=_critical,
                            vessel_specific_list=_vs,
                            vessel_profile=_profile,
                        )
                        st.session_state["analysis_results"] = results
                        st.success("✅ Analysis updated. Go to the Machinery Report page.")
                    except Exception as e:
                        st.error(f"Analysis error: {e}")
                        import traceback; st.code(traceback.format_exc())
        with col_clear:
            if st.button("🗑 Clear session / upload new vessel"):
                for key in ["vessel_df_processed", "vessel_name", "analysis_results",
                            "vessel_profile", "canonical_list", "critical_list",
                            "vessel_specific", "ref_sheets_loaded", "resolutions_cache"]:
                    st.session_state.pop(key, None)
                st.rerun()

    st.divider()
    st.markdown("**Or upload new files to start a fresh analysis:**")

# ── Step 1 & 2: File uploads ──────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">Step 1 — Vessel Data Export</div>', unsafe_allow_html=True)
    vessel_file = st.file_uploader(
        "Vessel data (.xlsx or .csv)",
        type=["xlsx", "csv"],
        key="vessel_upload",
        help="Export from your PMS — Vessel Data sheet required",
    )

with col2:
    st.markdown('<div class="section-header">Step 2 — Reference Sheet</div>', unsafe_allow_html=True)
    ref_file = st.file_uploader(
        "Reference Sheet (.xlsx)",
        type=["xlsx"],
        key="ref_upload",
        help="AESM Reference_Sheet.xlsx",
    )

# ── If no new file uploaded AND session data exists → stop here, already shown ─
if not vessel_file and session_has_data:
    st.stop()

# ── If no file at all → prompt ────────────────────────────────────────────────
if not vessel_file:
    st.info("Upload a vessel data file above to begin.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# NEW FILE UPLOADED — process from scratch
# ══════════════════════════════════════════════════════════════════════════════

# ── Step 3: Vessel profile ────────────────────────────────────────────────────
st.markdown('<div class="section-header">Step 3 — Vessel Profile</div>', unsafe_allow_html=True)
profiles = load_vessel_profiles()

# Auto-detect vessel name from the uploaded file
auto_vessel_name = None
try:
    _preview_df = load_vessel_data(vessel_file)
    vessel_file.seek(0)
    for col_candidate in ["Vessel", "Vessel Name", "VesselName", "Ship", "Ship Name"]:
        if col_candidate in _preview_df.columns:
            names_found = _preview_df[col_candidate].dropna().unique().tolist()
            if names_found:
                auto_vessel_name = str(names_found[0]).strip()
                break
except Exception:
    pass

with st.container(border=True):
    col_a, col_b, col_c, col_d = st.columns(4)

    with col_a:
        vessel_options = []
        if auto_vessel_name:
            vessel_options.append(auto_vessel_name)
        for v in profiles:
            if v not in vessel_options:
                vessel_options.append(v)
        vessel_options.append("+ Enter manually")

        vessel_sel = st.selectbox(
            "Vessel name" + (" (auto-detected ✓)" if auto_vessel_name else ""),
            vessel_options, index=0, key="vessel_sel",
        )
        if vessel_sel == "+ Enter manually":
            vessel_sel = st.text_input("Enter vessel name", key="vessel_manual") or "Unknown Vessel"

    selected_profile = profiles.get(vessel_sel, {})

    with col_b:
        vtype_opts = ["Chemical Tanker","Bulk Carrier","Container","General Cargo","Tanker","LNG Carrier"]
        vt_def = selected_profile.get("vessel_type", "Chemical Tanker")
        vessel_type = st.selectbox("Vessel type", vtype_opts,
            index=vtype_opts.index(vt_def) if vt_def in vtype_opts else 0)

    with col_c:
        me_type = st.selectbox("Main engine type",
            ["MAN B&W ME-C (MEC)","MAN B&W ME-B (MEB)","Wartsila RT-flex","Wartsila X-series"])

    with col_d:
        cyl_opts = [4,5,6,7,8,9]
        cyl_def = selected_profile.get("cylinder_count", 6)
        cyl_count = st.selectbox("Cylinder count", cyl_opts,
            index=cyl_opts.index(cyl_def) if cyl_def in cyl_opts else 2)

    col_e, col_f, col_g, col_h = st.columns(4)

    with col_e:
        ae_make = st.selectbox("Aux engine make",
            ["Yanmar 6EY22","Wartsila 6L26","MAN L23/30H","Caterpillar 3512"])

    with col_f:
        ae_opts = [2,3,4]
        ae_def = selected_profile.get("aux_engine_count", 3)
        ae_count = st.selectbox("Aux engine count", ae_opts,
            index=ae_opts.index(ae_def) if ae_def in ae_opts else 1)

    with col_g:
        bwts_opts = ["Optimarine","Alfa Laval","ERMA FIRST","Echlor","Techcross","Sunrui","None"]
        bwts_def = selected_profile.get("bwts_maker", "Optimarine")
        bwts_maker = st.selectbox("BWTS maker", bwts_opts,
            index=bwts_opts.index(bwts_def) if bwts_def in bwts_opts else 0)

    with col_h:
        egcs = st.selectbox("EGCS installed", ["Yes","No"],
            index=0 if selected_profile.get("egcs", True) else 1)

    st.selectbox("SCR system",
        ["LP SCR (Yanmar) + HP SCR (Hitachi)","LP SCR only","HP SCR only","None"])

vessel_profile = {
    "vessel_type": vessel_type,
    "main_engine": me_type.split("(")[1].rstrip(")") if "(" in me_type else me_type,
    "aux_engine": ae_make,
    "aux_engine_count": int(ae_count),
    "cylinder_count": int(cyl_count),
    "bwts_maker": bwts_maker,
    "egcs": egcs == "Yes",
    "sheet_mapping": {
        "BWTS": f"BWTS{bwts_maker[:4].replace(' ','')}",
        "Main Engine": "MEMEC",
        "LP SCR": "LPSCRYANMAR",
        "HP SCR": "HPSCRHITACHI",
    },
}

# ── Step 4: Column mapping validation ─────────────────────────────────────────
st.markdown('<div class="section-header">Step 4 — Column Mapping Validation</div>', unsafe_allow_html=True)

try:
    vessel_df = load_vessel_data(vessel_file)
except Exception as e:
    st.error(f"Could not read vessel file: {e}")
    st.stop()

detected_cols = list(vessel_df.columns)
expected_cols = {
    "Machinery Location":    ["Machinery Location","MachineryLocation","Machinery"],
    "Sub Component Location":["Sub Component Location","SubComponent","Sub Component"],
    "Critical":              ["Critical","Criticality","Critical Status"],
    "Job Code":              ["Job Code","JobCode","Code"],
    "Performing Rank":       ["Performing Rank","PerformingRank","Rank"],
    "Job Source":            ["Job Source","Source","JobSource"],
    "Attachment Indicator":  ["Attachment Indicator","Attachment","AttachmentIndicator"],
    "Frequency":             ["Frequency","Freq"],
}

col_mapping = {}
mapping_rows = []
for expected, aliases in expected_cols.items():
    found = next((c for c in detected_cols if c in aliases), None)
    col_mapping[expected] = found
    badge = "✅ Matched" if found == expected else ("🔶 Remapped" if found else "❌ Missing")
    mapping_rows.append({"Expected column": expected, "Detected as": found or "— not found", "Status": badge})

st.dataframe(pd.DataFrame(mapping_rows), use_container_width=True, hide_index=True)

rename_map = {v: k for k, v in col_mapping.items() if v and v != k}
vessel_df = vessel_df.rename(columns=rename_map)

# ── Variant resolution ────────────────────────────────────────────────────────
transform_map = load_transform_map()
ref_sheets = {}

if ref_file:
    try:
        ref_sheets = load_reference_sheet(ref_file)
        st.session_state["ref_sheets_loaded"] = list(ref_sheets.keys())
    except Exception as e:
        st.warning(f"Could not fully read reference sheet: {e}")

canonical_list = sorted(set(entry["canonical"] for entry in transform_map))
if "Machinery Location" in ref_sheets:
    canon_df = ref_sheets["Machinery Location"]
    if "Machinery Location" in canon_df.columns:
        canonical_list = sorted(canon_df["Machinery Location"].dropna().unique().tolist())

critical_list = []
vessel_specific = []
if "Critical Machinery" in ref_sheets:
    cdf = ref_sheets["Critical Machinery"]
    if "Critical Machinery" in cdf.columns:
        critical_list = cdf["Critical Machinery"].dropna().unique().tolist()
if "Vessel Specific Machinery" in ref_sheets:
    vsdf = ref_sheets["Vessel Specific Machinery"]
    if "Vessel Specific Machinery" in vsdf.columns:
        vessel_specific = vsdf["Vessel Specific Machinery"].dropna().unique().tolist()

raw_names = vessel_df["Machinery Location"].dropna().unique().tolist() if "Machinery Location" in vessel_df.columns else []
resolutions = resolve_names(raw_names, canonical_list, transform_map)

unresolved  = {k: v for k, v in resolutions.items() if v["status"] == "unresolved"}
suggestions = {k: v for k, v in resolutions.items() if v["status"] == "fuzzy_suggest"}
n_resolved  = len([v for v in resolutions.values() if v["status"] in ("exact","fuzzy_auto")])

# ── Variant panel — optional, never blocks ────────────────────────────────────
if unresolved or suggestions:
    n_pending = len(unresolved) + len(suggestions)
    st.info(
        f"ℹ {n_pending} machinery name variant(s) could not be auto-resolved. "
        "Accept suggestions below **or skip and run the analysis now** — "
        "unresolved names will be flagged in the report."
    )
    with st.expander(f"🔍 Review {n_pending} unresolved variants (optional)", expanded=False):
        st.caption("Accepting a mapping adds it permanently to the transform map.")
        for name, info in {**suggestions, **unresolved}.items():
            cols = st.columns([3, 3, 1, 1])
            cols[0].code(name)
            suggested = info.get("canonical") or ""
            new_val = cols[1].text_input(
                "Map to canonical", value=suggested,
                key=f"map_{name}", label_visibility="collapsed",
                placeholder="Type canonical name...",
            )
            score = info.get("score", 0)
            cols[2].markdown(f"**{round(score)}%**" if score else "—")
            if cols[3].button("Accept", key=f"acc_{name}"):
                if new_val.strip():
                    transform_map.append({"variant": name, "canonical": new_val.strip()})
                    save_transform_map(transform_map)
                    st.rerun()

vessel_df = apply_resolutions(vessel_df, resolutions)

# Persist everything in session_state immediately after processing
# so navigating away and back doesn't lose the data
st.session_state["vessel_df_processed"] = vessel_df
st.session_state["vessel_name"]         = vessel_sel
st.session_state["vessel_profile"]      = vessel_profile
st.session_state["canonical_list"]      = canonical_list
st.session_state["critical_list"]       = critical_list
st.session_state["vessel_specific"]     = vessel_specific
st.session_state["resolutions_cache"]   = resolutions

# ── Run analysis ──────────────────────────────────────────────────────────────
st.divider()
col_btn, col_status = st.columns([2, 5])

with col_btn:
    run_btn = st.button("▶ Run Sufficiency Check", type="primary", use_container_width=True)

with col_status:
    st.caption(
        f"✅ {n_resolved} names resolved automatically  ·  "
        f"{'⚠ ' + str(len(suggestions)) + ' suggestions pending  ·  ' if suggestions else ''}"
        f"{'❓ ' + str(len(unresolved)) + ' unresolved (flagged in report)' if unresolved else ''}"
    )

if run_btn:
    with st.spinner(f"Running analysis for {vessel_sel}..."):
        try:
            results = run_analysis(
                vessel_df=vessel_df,
                canonical_machinery_list=canonical_list,
                critical_machinery_list=critical_list,
                vessel_specific_list=vessel_specific,
                vessel_profile=vessel_profile,
            )
            st.session_state["analysis_results"] = results
            st.success(
                f"✅ Analysis complete for **{vessel_sel}**. "
                "Open the **📊 Machinery Report** page to view results."
            )
        except Exception as e:
            st.error(f"Analysis error: {e}")
            import traceback
            st.code(traceback.format_exc())
