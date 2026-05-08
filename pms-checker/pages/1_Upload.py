import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.loader import (
    load_vessel_data, load_reference_sheet, load_transform_map,
    load_vessel_profiles, get_aesm_library,
)
from engine.matcher import resolve_names, apply_resolutions, build_lookup
from engine.gap_analysis import run_analysis

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Upload & Configure | PMS Checker", layout="wide")

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #F8F9FB; }
[data-testid="stSidebar"] { background: #003963; }
[data-testid="stSidebar"] * { color: #E8EDF2 !important; }
[data-testid="stSidebar"] .stSelectbox label { color: #A5B8CC !important; }
div[data-testid="metric-container"] { background: white; border: 0.5px solid #E0E5EC;
  border-radius: 8px; padding: 12px 16px; }
.upload-label { font-size: 12px; font-weight: 600; color: #003963;
  text-transform: uppercase; letter-spacing: .05em; margin-bottom: 4px; }
.status-ok   { color: #3B6D11; font-weight: 600; }
.status-warn { color: #BA7517; font-weight: 600; }
.status-err  { color: #A32D2D; font-weight: 600; }
.section-header { font-size: 11px; font-weight: 700; color: #6B7280;
  text-transform: uppercase; letter-spacing: .06em; margin: 16px 0 6px; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙ PMS Checker")
    st.markdown("---")
    st.page_link("pages/1_Upload.py",   label="📤 Upload & Configure", icon=None)
    st.page_link("pages/2_Report.py",   label="📊 Machinery Report",   icon=None)
    st.page_link("pages/3_Admin.py",    label="⚙ Admin — Registry",   icon=None)
    st.markdown("---")
    if "vessel_name" in st.session_state:
        st.caption("CURRENT SESSION")
        st.markdown(f"**{st.session_state.vessel_name}**")
        vp = load_vessel_profiles().get(st.session_state.vessel_name, {})
        st.caption(vp.get("vessel_type", ""))

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Upload & Configure")
st.caption("Upload your PMS vessel export and reference sheet, configure the vessel profile, then run the sufficiency check.")

# ── Step 1 & 2: File uploads ──────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">Step 1 — Vessel Data Export</div>', unsafe_allow_html=True)
    vessel_file = st.file_uploader(
        "Vessel data (.xlsx or .csv)",
        type=["xlsx", "csv"],
        key="vessel_upload",
        help="Export from your PMS system — must contain the Vessel Data sheet",
    )

with col2:
    st.markdown('<div class="section-header">Step 2 — Reference Sheet</div>', unsafe_allow_html=True)
    ref_file = st.file_uploader(
        "Reference Sheet (.xlsx)",
        type=["xlsx"],
        key="ref_upload",
        help="AESM Reference_Sheet.xlsx — contains SMS library, machinery lists, vessel-specific jobs",
    )

# ── Step 3: Vessel profile ────────────────────────────────────────────────────
st.markdown('<div class="section-header">Step 3 — Vessel Profile</div>', unsafe_allow_html=True)

profiles = load_vessel_profiles()
vessel_names = list(profiles.keys()) + ["+ Add new vessel"]

with st.container(border=True):
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        vessel_sel = st.selectbox("Vessel name", vessel_names, key="vessel_sel")
    
    selected_profile = profiles.get(vessel_sel, {}) if vessel_sel != "+ Add new vessel" else {}

    with col_b:
        vessel_type = st.selectbox("Vessel type",
            ["Chemical Tanker", "Bulk Carrier", "Container", "General Cargo", "Tanker", "LNG Carrier"],
            index=["Chemical Tanker","Bulk Carrier","Container","General Cargo","Tanker","LNG Carrier"].index(
                selected_profile.get("vessel_type", "Chemical Tanker")) if selected_profile.get("vessel_type") else 0,
        )
    with col_c:
        me_type = st.selectbox("Main engine type",
            ["MAN B&W ME-C (MEC)", "MAN B&W ME-B (MEB)", "Wartsila RT-flex", "Wartsila X-series"],
        )
    with col_d:
        cyl_count = st.selectbox("Cylinder count", [4,5,6,7,8,9],
            index=[4,5,6,7,8,9].index(selected_profile.get("cylinder_count", 6)) if selected_profile.get("cylinder_count") else 2,
        )

    col_e, col_f, col_g, col_h = st.columns(4)
    with col_e:
        ae_make = st.selectbox("Aux engine make",
            ["Yanmar 6EY22", "Wartsila 6L26", "MAN L23/30H", "Caterpillar 3512"],
        )
    with col_f:
        ae_count = st.selectbox("Aux engine count", [2, 3, 4],
            index=[2,3,4].index(selected_profile.get("aux_engine_count", 3)) if selected_profile.get("aux_engine_count") else 1,
        )
    with col_g:
        bwts_maker = st.selectbox("BWTS maker",
            ["Optimarine", "Alfa Laval", "ERMA FIRST", "Echlor", "Techcross", "Sunrui", "None"],
            index=["Optimarine","Alfa Laval","ERMA FIRST","Echlor","Techcross","Sunrui","None"].index(
                selected_profile.get("bwts_maker","Optimarine")) if selected_profile.get("bwts_maker") else 0,
        )
    with col_h:
        egcs = st.selectbox("EGCS installed", ["Yes", "No"],
            index=0 if selected_profile.get("egcs", True) else 1,
        )

    scr_options = ["LP SCR (Yanmar) + HP SCR (Hitachi)", "LP SCR only", "HP SCR only", "None"]
    scr_sel = st.selectbox("SCR system", scr_options)

# Store profile in session for use across pages
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

# ── Column Mapping Validation ─────────────────────────────────────────────────
if vessel_file:
    st.markdown('<div class="section-header">Step 4 — Column Mapping Validation</div>', unsafe_allow_html=True)

    try:
        vessel_df = load_vessel_data(vessel_file)
    except Exception as e:
        st.error(f"Could not read vessel file: {e}")
        st.stop()

    detected_cols = list(vessel_df.columns)
    expected_cols = {
        "Machinery Location": ["Machinery Location", "MachineryLocation", "Machinery"],
        "Sub Component Location": ["Sub Component Location", "SubComponent", "Sub Component"],
        "Critical": ["Critical", "Criticality", "Critical Status"],
        "Job Code": ["Job Code", "JobCode", "Code"],
        "Performing Rank": ["Performing Rank", "PerformingRank", "Rank"],
        "Job Source": ["Job Source", "Source", "JobSource"],
        "Attachment Indicator": ["Attachment Indicator", "Attachment", "AttachmentIndicator"],
        "Frequency": ["Frequency", "Freq"],
    }

    col_mapping = {}
    mapping_rows = []
    for expected, aliases in expected_cols.items():
        found = next((c for c in detected_cols if c in aliases), None)
        if found:
            col_mapping[expected] = found
            if found != expected:
                status, badge = "Remapped", "🔶 Remapped"
            else:
                status, badge = "Matched", "✅ Matched"
        else:
            col_mapping[expected] = None
            status, badge = "Missing", "❌ Missing"
        mapping_rows.append({"Expected Column": expected, "Detected As": found or "— not found", "Status": badge})

    st.dataframe(
        pd.DataFrame(mapping_rows),
        use_container_width=True,
        hide_index=True,
    )

    # Apply column renames to vessel_df
    rename_map = {v: k for k, v in col_mapping.items() if v and v != k}
    vessel_df = vessel_df.rename(columns=rename_map)

    # ── Variant resolution ────────────────────────────────────────────────────
    transform_map = load_transform_map()
    ref_sheets = {}

    if ref_file:
        try:
            ref_sheets = load_reference_sheet(ref_file)
        except Exception as e:
            st.warning(f"Could not fully read reference sheet: {e}")

    # Build canonical list from reference or transform map
    canonical_list = sorted(set(
        entry["canonical"] for entry in transform_map
    ))
    if "Machinery Location" in ref_sheets:
        canon_df = ref_sheets["Machinery Location"]
        if "Machinery Location" in canon_df.columns:
            canonical_list = sorted(canon_df["Machinery Location"].dropna().unique().tolist())

    raw_names = vessel_df["Machinery Location"].dropna().unique().tolist() if "Machinery Location" in vessel_df.columns else []
    resolutions = resolve_names(raw_names, canonical_list, transform_map)

    # Categorise
    unresolved  = {k: v for k, v in resolutions.items() if v["status"] == "unresolved"}
    suggestions = {k: v for k, v in resolutions.items() if v["status"] == "fuzzy_suggest"}
    auto_mapped = {k: v for k, v in resolutions.items() if v["status"] in ("fuzzy_auto",)}

    if unresolved or suggestions:
        st.warning(f"⚠ {len(unresolved) + len(suggestions)} machinery name variant(s) need review before running analysis.")

        with st.expander("🔍 Review unresolved name variants", expanded=True):
            for name, info in {**suggestions, **unresolved}.items():
                cols = st.columns([3, 3, 1, 1])
                cols[0].code(name)
                if info["canonical"]:
                    new_val = cols[1].text_input("Map to canonical", value=info["canonical"], key=f"map_{name}", label_visibility="collapsed")
                    cols[2].markdown(f"**{info['score']}%**")
                else:
                    new_val = cols[1].text_input("Type canonical name", value="", key=f"map_{name}", label_visibility="collapsed")
                    cols[2].markdown("—")
                if cols[3].button("Accept", key=f"acc_{name}"):
                    transform_map.append({"variant": name, "canonical": new_val})
                    from engine.loader import save_transform_map
                    save_transform_map(transform_map)
                    st.rerun()

    # Apply resolutions to df
    vessel_df = apply_resolutions(vessel_df, resolutions)

    # ── Run analysis button ───────────────────────────────────────────────────
    st.divider()
    col_btn, col_status = st.columns([2, 5])
    with col_btn:
        run_btn = st.button("▶ Run Sufficiency Check", type="primary", use_container_width=True)
    with col_status:
        st.caption(f"{len([v for v in resolutions.values() if v['status'] in ('exact','fuzzy_auto')])} names resolved · "
                   f"{len(suggestions)} suggestions pending · {len(unresolved)} unresolved")

    if run_btn:
        # Build lists for analysis
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

        with st.spinner("Running analysis..."):
            try:
                results = run_analysis(
                    vessel_df=vessel_df,
                    canonical_machinery_list=canonical_list,
                    critical_machinery_list=critical_list,
                    vessel_specific_list=vessel_specific,
                    vessel_profile=vessel_profile,
                )
                st.session_state["analysis_results"] = results
                st.session_state["vessel_name"] = vessel_sel if vessel_sel != "+ Add new vessel" else "Unknown Vessel"
                st.session_state["vessel_df"] = vessel_df
                st.session_state["vessel_profile"] = vessel_profile
                st.success("✅ Analysis complete. Open the Machinery Report page to view results.")
            except Exception as e:
                st.error(f"Analysis error: {e}")
                import traceback; st.code(traceback.format_exc())
else:
    st.info("Upload a vessel data file above to begin.")
