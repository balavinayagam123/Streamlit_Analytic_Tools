"""
loader.py
Reads all persistent JSON reference data and the uploaded Reference Sheet xlsx.
All functions return plain Python dicts/lists — no Streamlit dependencies.
"""
import json
import os
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(filename: str):
    path = DATA_DIR / filename
    if not path.exists():
        return {} if filename.endswith(".json") and "map" in filename else []
    with open(path) as f:
        return json.load(f)


def save_json(filename: str, data):
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_transform_map() -> list[dict]:
    return load_json("transform_map.json")


def load_matching_titles() -> dict:
    return load_json("matching_titles.json")


def load_vessel_profiles() -> dict:
    return load_json("vessel_profiles.json")


def save_transform_map(entries: list[dict]):
    save_json("transform_map.json", entries)


def save_vessel_profiles(profiles: dict):
    save_json("vessel_profiles.json", profiles)


def load_vessel_data(uploaded_file) -> pd.DataFrame:
    """Load the PMS vessel export. Accepts xlsx or csv."""
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        xl = pd.ExcelFile(uploaded_file)
        # Try to find 'Vessel Data' sheet, fall back to first sheet
        sheet = "Vessel Data" if "Vessel Data" in xl.sheet_names else xl.sheet_names[0]
        df = pd.read_excel(uploaded_file, sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_reference_sheet(uploaded_file) -> dict[str, pd.DataFrame]:
    """
    Load the Reference Sheet xlsx.
    Returns a dict of {sheet_name: DataFrame} for all sheets we care about.
    """
    xl = pd.ExcelFile(uploaded_file)
    wanted = {
        "AESM SMS Sheet", "SMS Sheet", "Machinery Location",
        "Critical Machinery", "Vessel Specific Machinery",
        "Matching Titles", "ME Jobs", "AE Jobs", "MEMEC", "MEWINGD",
        "BWTSOpti", "BWTSAlfalaval", "BWTSERMA", "BWTSEchlor",
        "BWTSSunrai", "BWTStechcross", "LPSCRYANMAR", "HPSCRHITACHI",
        "Steering", "Boiler", "OWS", "Purifiers", "Fans", "Pumps",
        "Compressor", "Mooring", "Crane", "Boats", "LSAFFA",
        "Bridge", "Emg", "FFASYS", "IGSystem", "Incin",
        "Cargohanding", "Cargo Pumping", "Tanks", "Misc",
    }
    sheets = {}
    for name in xl.sheet_names:
        if name in wanted:
            try:
                df = pd.read_excel(uploaded_file, sheet_name=name)
                df.columns = [str(c).strip() for c in df.columns]
                sheets[name] = df
            except Exception:
                pass
    return sheets


def get_aesm_library(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return the main SMS job library from whichever sheet is available."""
    for preferred in ["AESM SMS Sheet", "SMS Sheet"]:
        if preferred in sheets:
            df = sheets[preferred].copy()
            # Normalise column names to consistent keys
            col_map = {
                "Main Machinery": "Machinery",
                "Machinery Name": "Machinery",
                "UI Job Code": "Job Code",
                "J3 Job Title": "Job Title",
                "Original BPES Frequency": "Frequency",
                "Performing Rank": "Performing Rank",
                "Department": "Department",
                "Critical Status": "Critical Status",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            # Keep only rows with a Job Code
            if "Job Code" in df.columns:
                df = df[df["Job Code"].notna()]
                df["Job Code"] = df["Job Code"].astype(str).str.strip()
            return df
    return pd.DataFrame()
