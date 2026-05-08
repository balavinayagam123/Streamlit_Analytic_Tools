import streamlit as st
import pandas as pd
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.loader import (
    load_transform_map, save_transform_map,
    load_vessel_profiles, save_vessel_profiles,
    load_matching_titles,
)

st.set_page_config(page_title="Admin — Registry | PMS Checker", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #F8F9FB; }
[data-testid="stSidebar"] { background: #003963; }
[data-testid="stSidebar"] * { color: #E8EDF2 !important; }
.section-header { font-size: 11px; font-weight: 700; color: #6B7280;
  text-transform: uppercase; letter-spacing: .06em; margin: 16px 0 6px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙ PMS Checker")
    st.markdown("---")
    st.page_link("pages/1_Upload.py", label="📤 Upload & Configure")
    st.page_link("pages/2_Report.py", label="📊 Machinery Report")
    st.page_link("pages/3_Admin.py",  label="⚙ Admin — Registry")
    st.markdown("---")
    st.caption("Changes here persist to GitHub and apply to all future uploads.")

st.title("Admin — Registry")
st.caption("Manage reference data: transform map, job code aliases, vessel profiles, and library versions.")

# ── Check for GitHub secrets ──────────────────────────────────────────────────
github_available = False
try:
    token = st.secrets.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "")
    github_available = bool(token and repo)
except Exception:
    pass

if not github_available:
    st.info("💡 GitHub push not configured. Changes save locally only. "
            "Add GITHUB_TOKEN and GITHUB_REPO to Streamlit secrets to enable cloud persistence.")

# ── Tab layout ────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🔀 Transform Map",
    "🔢 Job Code Aliases",
    "🚢 Vessel Profiles",
    "📚 Reference Library",
])

# ── Tab 1: Transform Map ──────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-header">Machinery name variant → canonical mappings</div>', unsafe_allow_html=True)
    st.caption("When the PMS export uses a different name from the canonical machinery list, add the mapping here. "
               "New variants detected during upload are surfaced on the Upload page for quick acceptance.")

    transform_map = load_transform_map()
    tm_df = pd.DataFrame(transform_map) if transform_map else pd.DataFrame(columns=["variant","canonical"])
    tm_df.columns = ["Variant (PMS export)", "Canonical name"]

    edited_tm = st.data_editor(
        tm_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Variant (PMS export)": st.column_config.TextColumn("Variant (PMS export)", width="large"),
            "Canonical name":       st.column_config.TextColumn("Canonical name",       width="large"),
        },
    )

    col_save, col_status = st.columns([1, 4])
    with col_save:
        if st.button("💾 Save transform map", type="primary"):
            updated = [
                {"variant": row["Variant (PMS export)"], "canonical": row["Canonical name"]}
                for _, row in edited_tm.iterrows()
                if pd.notna(row["Variant (PMS export)"]) and str(row["Variant (PMS export)"]).strip()
            ]
            save_transform_map(updated)

            if github_available:
                from engine.github_writer import push_json
                ok = push_json(repo, "data/transform_map.json", updated, token,
                               "Update transform_map.json from Admin panel")
                if ok:
                    col_status.success("Saved locally and pushed to GitHub.")
                else:
                    col_status.warning("Saved locally. GitHub push failed — check token permissions.")
            else:
                col_status.success(f"Saved locally. {len(updated)} mappings active.")

# ── Tab 2: Job Code Aliases ───────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-header">Job code alias map (from Matching Titles sheet)</div>', unsafe_allow_html=True)
    st.caption("These are known job code equivalences — if a vessel uses code 890, it maps to 896 in the SMS library. "
               "Seeded from the Reference Sheet 'Matching Titles' tab.")

    aliases = load_matching_titles()
    alias_df = pd.DataFrame([
        {"Vessel job code": k, "SMS library code": v}
        for k, v in aliases.items()
    ])

    edited_aliases = st.data_editor(
        alias_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Vessel job code":  st.column_config.TextColumn(width="medium"),
            "SMS library code": st.column_config.TextColumn(width="medium"),
        },
    )

    if st.button("💾 Save alias map"):
        updated_aliases = {
            str(row["Vessel job code"]): str(row["SMS library code"])
            for _, row in edited_aliases.iterrows()
            if pd.notna(row["Vessel job code"])
        }
        from engine.loader import save_json
        save_json("matching_titles.json", updated_aliases)

        if github_available:
            from engine.github_writer import push_json
            push_json(repo, "data/matching_titles.json", updated_aliases, token, "Update matching_titles.json")
        st.success(f"Saved {len(updated_aliases)} alias mappings.")

# ── Tab 3: Vessel Profiles ────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-header">Vessel configuration profiles</div>', unsafe_allow_html=True)
    st.caption("Each vessel profile defines which reference sheet variants to use (BWTS maker, engine type, SCR, etc.). "
               "This drives which tabs of the Reference Sheet are selected during analysis.")

    profiles = load_vessel_profiles()

    for vessel, profile in profiles.items():
        with st.expander(f"🚢 {vessel}", expanded=True):
            c1, c2, c3 = st.columns(3)
            new_type = c1.text_input("Vessel type", value=profile.get("vessel_type",""), key=f"vt_{vessel}")
            new_me   = c2.text_input("Main engine", value=profile.get("main_engine",""), key=f"me_{vessel}")
            new_ae   = c3.text_input("Aux engine",  value=profile.get("aux_engine",""),  key=f"ae_{vessel}")

            c4, c5, c6, c7 = st.columns(4)
            new_cyl  = c4.number_input("Cylinders",   value=int(profile.get("cylinder_count",6)), min_value=4, max_value=9, key=f"cy_{vessel}")
            new_aen  = c5.number_input("Aux count",   value=int(profile.get("aux_engine_count",3)), min_value=1, max_value=6, key=f"an_{vessel}")
            new_bwts = c6.text_input("BWTS maker",    value=profile.get("bwts_maker",""), key=f"bw_{vessel}")
            new_egcs = c7.selectbox("EGCS", ["Yes","No"], index=0 if profile.get("egcs") else 1, key=f"eg_{vessel}")

            if st.button(f"Save {vessel}", key=f"save_{vessel}"):
                profiles[vessel] = {
                    **profile,
                    "vessel_type": new_type,
                    "main_engine": new_me,
                    "aux_engine": new_ae,
                    "cylinder_count": int(new_cyl),
                    "aux_engine_count": int(new_aen),
                    "bwts_maker": new_bwts,
                    "egcs": new_egcs == "Yes",
                }
                save_vessel_profiles(profiles)
                if github_available:
                    from engine.github_writer import push_json
                    push_json(repo, "data/vessel_profiles.json", profiles, token, f"Update profile for {vessel}")
                st.success(f"Profile saved for {vessel}.")

    st.divider()
    with st.expander("➕ Add new vessel"):
        new_name = st.text_input("Vessel name")
        if st.button("Create profile") and new_name:
            profiles[new_name] = {
                "vessel_type": "Chemical Tanker",
                "main_engine": "MAN_MEC",
                "aux_engine": "Yanmar 6EY22",
                "cylinder_count": 6,
                "aux_engine_count": 3,
                "bwts_maker": "Optimarine",
                "egcs": True,
                "sheet_mapping": {"BWTS": "BWTSOpti", "Main Engine": "MEMEC"},
            }
            save_vessel_profiles(profiles)
            st.success(f"Created profile for {new_name}. Configure it above.")
            st.rerun()

# ── Tab 4: Reference Library ──────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-header">Reference library version control</div>', unsafe_allow_html=True)
    st.caption("The Reference Sheet is uploaded fresh on each session (Option A). "
               "This tab shows what was loaded in the current session and lets you review the library stats.")

    if "ref_sheets_loaded" in st.session_state:
        st.success(f"Reference sheet loaded this session — {len(st.session_state['ref_sheets_loaded'])} sheets parsed.")
        for sheet_name in sorted(st.session_state["ref_sheets_loaded"]):
            st.markdown(f"- {sheet_name}")
    else:
        st.info("No reference sheet loaded this session. Upload it on the Upload & Configure page.")

    st.divider()
    st.markdown("**Persistent JSON data files (GitHub)**")
    st.caption("These files are committed to the repo and loaded on every app start.")

    from engine.loader import DATA_DIR
    for fname in ["transform_map.json", "matching_titles.json", "vessel_profiles.json"]:
        fpath = DATA_DIR / fname
        if fpath.exists():
            size = fpath.stat().st_size
            data = json.loads(fpath.read_text())
            count = len(data)
            st.markdown(f"- **{fname}** — {count} entries · {size/1024:.1f} KB")
            with st.expander(f"Preview {fname}"):
                st.json(data)
        else:
            st.markdown(f"- **{fname}** — ⚠ file not found")
