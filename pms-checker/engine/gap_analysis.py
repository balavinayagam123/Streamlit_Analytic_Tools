"""
gap_analysis.py
Core analysis engine. Takes vessel DataFrame + reference sheets + vessel profile.
Returns a structured results dict consumed by the report page.
"""
import pandas as pd
import numpy as np
from collections import defaultdict


# ── Column name constants ──────────────────────────────────────────────────────
COL_MACHINERY   = "Canonical Machinery"
COL_RAW         = "Machinery Location"
COL_SUB         = "Sub Component Location"
COL_CRITICAL    = "Critical"
COL_JOB_CODE    = "Job Code"
COL_JOB_STATUS  = "Job Status"
COL_RANK        = "Performing Rank"
COL_SOURCE      = "Job Source"
COL_FREQUENCY   = "Frequency"
COL_DEPT        = "Department"
COL_ATTACH      = "Attachment Indicator"

DECK_OFFICERS   = {"Master", "Chief Officer", "2nd Officer", "3rd Officer"}
ENGINE_FUNCS    = {"Propulsion Power", "Electrical Power", "Auxiliary Systems",
                   "Bilge and Sludge System", "Lubricating Oil Service System",
                   "Fuel Oil Service System", "Steam Power", "Cooling Sea Water System"}

ME_SUB_COMPONENTS = [
    "Cylinder Cover", "Cylinder Liner", "Exhaust Valve",
    "Fuel Valve", "Indicator Valve", "Piston",
    "Start Air Valve", "Stuffing Box",
]
AE_SUB_COMPONENTS = [
    "AE Air Cooler", "AE Alarms", "AE Alternator", "AE Connecting Rod",
    "AE Crankcase Relief Valve", "AE Cylinder Head", "AE Cylinder Liner",
    "AE Fuel Injection Pump", "AE Fuel Valve", "AE LO Cooler",
    "AE Main Bearing", "AE Piston", "AE Starting Air Motor",
    "AE Starting Air Valve", "AE Turbocharger",
]

SOURCE_NORMALISE = {
    "Instruction Manual": "Maker / IM",
    "Instruction Manual/SMS": "Maker / IM",
    "Generic": "Generic",
    "SMS": "SMS",
    "CMS File": "CMS File",
    "Generic/SMS": "Generic",
}


def normalise_source(val: str) -> str:
    if not isinstance(val, str):
        return "Unknown"
    val = val.strip()
    # Strip quoted annotation e.g. SMS "ANNEX 2"
    base = val.split('"')[0].strip().split("'")[0].strip()
    return SOURCE_NORMALISE.get(base, base)


def run_analysis(
    vessel_df: pd.DataFrame,
    canonical_machinery_list: list[str],
    critical_machinery_list: list[str],
    vessel_specific_list: list[str],
    vessel_profile: dict,
) -> dict:
    """
    Main entry point. Returns a results dict with all sections.
    """
    df = vessel_df.copy()

    # Normalise job source
    if COL_SOURCE in df.columns:
        df["Source Normalised"] = df[COL_SOURCE].apply(normalise_source)
    else:
        df["Source Normalised"] = "Unknown"

    # Normalise critical flag
    if COL_CRITICAL in df.columns:
        df["Is Critical"] = df[COL_CRITICAL].astype(str).str.strip().str.upper() == "C"
    else:
        df["Is Critical"] = False

    results = {}

    # 1. Missing machineries
    results["missing_machineries"] = _missing_machineries(
        df, canonical_machinery_list
    )

    # 2. Job source breakdown
    results["job_source_breakdown"] = _job_source_breakdown(df)

    # 3. Critical machinery job counts
    results["critical_machinery_jobs"] = _critical_machinery_jobs(
        df, critical_machinery_list
    )

    # 4. Vessel-specific machinery counts
    results["vessel_specific_jobs"] = _vessel_specific_jobs(
        df, vessel_specific_list
    )

    # 5. ME cylinder unit completeness
    results["me_unit_completeness"] = _me_unit_completeness(df, vessel_profile)

    # 6. AE sub-component completeness
    results["ae_subcomponent_completeness"] = _ae_subcomponent_completeness(
        df, vessel_profile
    )

    # 7. Rank violations
    results["rank_violations"] = _rank_violations(df)

    # 8. Low-frequency job distribution
    results["low_freq_distribution"] = _low_freq_distribution(df)

    # 9. Duplicate jobs
    results["duplicate_jobs"] = _duplicate_jobs(df)

    # 10. Motors and fans
    results["motors_fans"] = _motors_fans(df)

    # 11. Pumps with >6 jobs
    results["pumps_high_jobs"] = _pumps_high_jobs(df)

    # 12. System coverage overview
    results["system_coverage"] = _system_coverage(df, vessel_profile)

    # 13. Scorecard
    results["scorecard"] = _scorecard(results, df, canonical_machinery_list)

    return results


# ── Section builders ──────────────────────────────────────────────────────────

def _missing_machineries(df: pd.DataFrame, canonical_list: list[str]) -> list[str]:
    present = set(df[COL_MACHINERY].dropna().unique()) if COL_MACHINERY in df.columns else set()
    return sorted([m for m in canonical_list if m not in present])


def _job_source_breakdown(df: pd.DataFrame) -> list[dict]:
    counts = df["Source Normalised"].value_counts()
    total = counts.sum()
    order = ["Maker / IM", "SMS", "Generic", "CMS File"]
    rows = []
    for src in order:
        cnt = int(counts.get(src, 0))
        rows.append({
            "source": src,
            "count": cnt,
            "pct": round(cnt / total * 100) if total else 0,
        })
    # Add any remaining
    for src, cnt in counts.items():
        if src not in order:
            rows.append({"source": src, "count": int(cnt), "pct": round(int(cnt)/total*100) if total else 0})
    return rows


def _critical_machinery_jobs(df: pd.DataFrame, critical_list: list[str]) -> list[dict]:
    rows = []
    mach_col = COL_MACHINERY if COL_MACHINERY in df.columns else COL_RAW
    for mach in sorted(critical_list):
        sub = df[df[mach_col] == mach] if mach_col in df.columns else pd.DataFrame()
        if sub.empty:
            rows.append({"machinery": mach, "generic": 0, "sms": 0, "maker": 0, "total": 0})
            continue
        g = int((sub["Source Normalised"] == "Generic").sum())
        s = int((sub["Source Normalised"] == "SMS").sum())
        m = int((sub["Source Normalised"] == "Maker / IM").sum())
        rows.append({"machinery": mach, "generic": g, "sms": s, "maker": m, "total": g + s + m})
    # Sort by total descending
    rows.sort(key=lambda x: x["total"], reverse=True)
    return rows


def _vessel_specific_jobs(df: pd.DataFrame, specific_list: list[str]) -> list[dict]:
    return _critical_machinery_jobs(df, specific_list)  # same shape


def _me_unit_completeness(df: pd.DataFrame, profile: dict) -> dict:
    """
    Returns per-cylinder-unit job counts for each ME sub-component.
    Highlights anomalies where counts differ across units.
    """
    n_cylinders = profile.get("cylinder_count", 6)
    units = [f"Cylinder Unit#{i}" for i in range(1, n_cylinders + 1)]
    sub_col = COL_SUB if COL_SUB in df.columns else None
    me_mask = df[COL_MACHINERY].str.contains("Main Engine", na=False) if COL_MACHINERY in df.columns else pd.Series(False, index=df.index)
    me_df = df[me_mask]

    table = {}
    for unit in units:
        unit_mask = me_df[sub_col].str.contains(unit, na=False) if sub_col else pd.Series(False, index=me_df.index)
        unit_df = me_df[unit_mask]
        row = {}
        for sc in ME_SUB_COMPONENTS:
            sc_mask = unit_df[sub_col].str.contains(sc, na=False) if sub_col else pd.Series(False, index=unit_df.index)
            row[sc] = int(sc_mask.sum())
        row["Total"] = sum(row.values())
        table[unit] = row

    # Compute totals and flag anomalies
    totals = {}
    anomalies = {}
    for sc in ME_SUB_COMPONENTS:
        vals = [table[u][sc] for u in units]
        modal = max(set(vals), key=vals.count) if vals else 0
        totals[sc] = sum(vals)
        anomalies[sc] = [u for u in units if table[u][sc] != modal]

    grand_total = sum(totals.values())
    expected_total = sum(max(set([table[u][sc] for u in units]), key=[table[u][sc] for u in units].count) for sc in ME_SUB_COMPONENTS) * n_cylinders if units else 0

    return {
        "units": units,
        "sub_components": ME_SUB_COMPONENTS,
        "table": table,
        "totals": totals,
        "anomalies": anomalies,
        "grand_total": grand_total,
        "expected_total": expected_total,
    }


def _ae_subcomponent_completeness(df: pd.DataFrame, profile: dict) -> dict:
    n_ae = profile.get("aux_engine_count", 3)
    engines = [f"Auxiliary Engine#{i}" for i in range(1, n_ae + 1)]
    mach_col = COL_MACHINERY if COL_MACHINERY in df.columns else COL_RAW
    sub_col = COL_SUB if COL_SUB in df.columns else None

    table = {}
    for eng in engines:
        eng_mask = df[mach_col].str.contains("Auxiliary Engine", na=False) if mach_col in df.columns else pd.Series(False, index=df.index)
        # Also try to match on raw machinery location with #N suffix
        raw_mask = df[COL_RAW].astype(str).str.startswith(eng) if COL_RAW in df.columns else pd.Series(False, index=df.index)
        eng_df = df[eng_mask & raw_mask] if not raw_mask.empty else df[eng_mask]
        row = {}
        for sc in AE_SUB_COMPONENTS:
            if sub_col:
                cnt = int(eng_df[sub_col].astype(str).str.contains(sc, na=False).sum())
            else:
                cnt = 0
            row[sc] = cnt
        row["Total"] = sum(row.values())
        table[eng] = row

    totals = {}
    anomalies = {}
    for sc in AE_SUB_COMPONENTS:
        vals = [table[e][sc] for e in engines]
        modal = max(set(vals), key=vals.count) if vals else 0
        totals[sc] = sum(vals)
        anomalies[sc] = [e for e in engines if table[e][sc] != modal]

    grand_total = sum(totals.values())

    return {
        "engines": engines,
        "sub_components": AE_SUB_COMPONENTS,
        "table": table,
        "totals": totals,
        "anomalies": anomalies,
        "grand_total": grand_total,
    }


def _rank_violations(df: pd.DataFrame) -> dict:
    """Detect rank assignment mismatches."""
    rank_col = COL_RANK if COL_RANK in df.columns else None
    dept_col = COL_DEPT if COL_DEPT in df.columns else None
    violations = {
        "engine_to_co": 0,
        "engine_to_master": 0,
        "engine_to_3o": 0,
        "electrical_to_deck": 0,
        "total": 0,
        "details": [],
    }
    if rank_col is None:
        return violations

    engine_jobs = df[df[dept_col] == "Engine"] if dept_col else pd.DataFrame()
    electrical_jobs = df[df["Source Normalised"].str.contains("Electr", na=False)] if "Source Normalised" in df.columns else pd.DataFrame()

    for _, row in engine_jobs.iterrows():
        ranks = str(row.get(rank_col, "")).split(",")
        for r in ranks:
            r = r.strip()
            if r == "Chief Officer":
                violations["engine_to_co"] += 1
                violations["details"].append({"job": row.get("Title", ""), "rank": r, "type": "Engine → Deck"})
            elif r == "Master":
                violations["engine_to_master"] += 1
                violations["details"].append({"job": row.get("Title", ""), "rank": r, "type": "Engine → Deck"})
            elif r == "3rd Officer":
                violations["engine_to_3o"] += 1
                violations["details"].append({"job": row.get("Title", ""), "rank": r, "type": "Engine → Deck"})

    for _, row in electrical_jobs.iterrows():
        ranks = str(row.get(rank_col, "")).split(",")
        for r in ranks:
            r = r.strip()
            if r in DECK_OFFICERS:
                violations["electrical_to_deck"] += 1

    violations["total"] = (violations["engine_to_co"] + violations["engine_to_master"] +
                           violations["engine_to_3o"] + violations["electrical_to_deck"])
    return violations


def _low_freq_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Count jobs per rank per frequency bucket (≤4 months / <500 hrs)."""
    freq_col = COL_FREQUENCY if COL_FREQUENCY in df.columns else None
    rank_col = COL_RANK if COL_RANK in df.columns else None
    if freq_col is None or rank_col is None:
        return pd.DataFrame()

    buckets = {
        "7 Days": lambda f: str(f).strip() == "7 Days",
        "15 Days": lambda f: str(f).strip() == "15 Days",
        "1 Month": lambda f: str(f).strip() in ("1 Months", "1 Month"),
        "2 Months": lambda f: str(f).strip() in ("2 Months",),
        "3 Months": lambda f: str(f).strip() in ("3 Months",),
        "4 Months": lambda f: str(f).strip() in ("4 Months",),
    }

    rows = defaultdict(lambda: defaultdict(int))
    for _, row in df.iterrows():
        freq = str(row.get(freq_col, "")).strip()
        matched_bucket = None
        for bucket, check in buckets.items():
            if check(freq):
                matched_bucket = bucket
                break
        if matched_bucket is None:
            continue
        ranks = str(row.get(rank_col, "")).split(",")
        for r in ranks:
            r = r.strip()
            if r:
                rows[r][matched_bucket] += 1

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows).T.fillna(0).astype(int)
    # Ensure all buckets present
    for b in buckets:
        if b not in result.columns:
            result[b] = 0
    result = result[[b for b in buckets if b in result.columns]]
    result["Grand Total"] = result.sum(axis=1)
    result = result.sort_values("Grand Total", ascending=False)
    return result


def _duplicate_jobs(df: pd.DataFrame) -> list[dict]:
    """Find machinery items with duplicate job codes."""
    if COL_JOB_CODE not in df.columns:
        return []
    # Normalise machinery column
    mach_col = COL_MACHINERY if COL_MACHINERY in df.columns else COL_RAW
    dups = (
        df.groupby([COL_RAW, COL_JOB_CODE])
        .size()
        .reset_index(name="count")
    )
    dups = dups[dups["count"] > 1]
    summary = (
        dups.groupby(COL_RAW)["count"]
        .sum()
        .reset_index()
        .rename(columns={COL_RAW: "machinery", "count": "duplicates"})
        .sort_values("duplicates", ascending=False)
    )
    rows = []
    for _, r in summary.iterrows():
        cnt = int(r["duplicates"])
        severity = "Critical" if cnt >= 20 else "High" if cnt >= 8 else "Medium" if cnt >= 4 else "Low"
        rows.append({"machinery": r["machinery"], "duplicates": cnt, "severity": severity})
    return rows


def _motors_fans(df: pd.DataFrame) -> list[dict]:
    """Find motor/fan sub-components with more than 3 jobs."""
    sub_col = COL_SUB if COL_SUB in df.columns else None
    if sub_col is None:
        return []
    motor_mask = df[sub_col].astype(str).str.contains(r"Motor|Fan|Pump", case=False, na=False, regex=True)
    motor_df = df[motor_mask]
    counts = motor_df.groupby(sub_col).size().reset_index(name="job_count")
    counts = counts[counts["job_count"] > 3].sort_values("job_count", ascending=False)
    rows = []
    for _, r in counts.iterrows():
        cnt = int(r["job_count"])
        color = "danger" if cnt >= 6 else "warning" if cnt >= 5 else "info"
        rows.append({"sub_component": r[sub_col], "job_count": cnt, "color": color})
    return rows


def _pumps_high_jobs(df: pd.DataFrame) -> list[dict]:
    """Find pump machinery items with more than 6 jobs."""
    mach_col = COL_MACHINERY if COL_MACHINERY in df.columns else COL_RAW
    pump_mask = df[mach_col].astype(str).str.contains("Pump", case=False, na=False)
    pump_df = df[pump_mask]
    counts = (
        pump_df.groupby(COL_RAW).size()
        .reset_index(name="job_count")
        .sort_values("job_count", ascending=False)
    )
    counts = counts[counts["job_count"] > 6]
    return [{"machinery": r[COL_RAW], "job_count": int(r["job_count"])} for _, r in counts.iterrows()]


SYSTEM_MAP = {
    "Main Engine":          ["Main Engine"],
    "Auxiliary Engines":    ["Auxiliary Engine"],
    "BWTS":                 ["Ballast Water Treatment Plant"],
    "Purifiers":            ["FO Purifier", "ME LO Purifier", "LO Purifier"],
    "Boilers":              ["Boiler", "Boiler Feed Water Pump", "Boiler FO Supply Pump"],
    "Emergency Generator":  ["Emergency Generator"],
    "Fire Protection":      ["Fire Protection System", "Fire Detection and Alarm System"],
    "OWS":                  ["Oily Water Separator"],
    "Steering Gear":        ["Steering Gear"],
    "EGCS":                 ["EGCS"],
    "Inert Gas Plant":      ["Inert Gas Plant", "Inert Gas Generating Plant"],
    "Cargo Pumps":          ["Cargo Pump"],
    "Mooring Winches":      ["Mooring Winch", "Combined Windlass Mooring Winch"],
}

# Approximate expected job counts per system (from reference sheet analysis)
EXPECTED_JOBS = {
    "Main Engine": 443, "Auxiliary Engines": 615, "BWTS": 63,
    "Purifiers": 84, "Boilers": 88, "Emergency Generator": 33,
    "Fire Protection": 84, "OWS": 51, "Steering Gear": 55,
    "EGCS": 86, "Inert Gas Plant": 66, "Cargo Pumps": 36,
    "Mooring Winches": 132,
}


def _system_coverage(df: pd.DataFrame, profile: dict) -> list[dict]:
    mach_col = COL_MACHINERY if COL_MACHINERY in df.columns else COL_RAW
    rows = []
    for system, machineries in SYSTEM_MAP.items():
        mask = df[mach_col].astype(str).apply(
            lambda x: any(m.lower() in x.lower() for m in machineries)
        )
        actual = int(mask.sum())
        expected = EXPECTED_JOBS.get(system, max(actual, 1))
        pct = min(round(actual / expected * 100), 100) if expected > 0 else 0
        missing = max(expected - actual, 0)
        status = "Good" if pct >= 90 else "Review" if pct >= 75 else "Action needed"
        rows.append({
            "system": system,
            "actual": actual,
            "expected": expected,
            "coverage_pct": pct,
            "missing": missing,
            "status": status,
        })
    rows.sort(key=lambda x: x["coverage_pct"])
    return rows


def _scorecard(results: dict, df: pd.DataFrame, canonical_list: list[str]) -> dict:
    missing_count = len(results.get("missing_machineries", []))
    total_canonical = len(canonical_list) if canonical_list else 1
    equip_pct = round((1 - missing_count / total_canonical) * 100) if total_canonical else 0

    dup_rows = results.get("duplicate_jobs", [])
    total_dups = sum(r["duplicates"] for r in dup_rows)
    total_jobs = len(df)
    dup_pct = round((1 - total_dups / total_jobs) * 100) if total_jobs else 100

    rank_v = results.get("rank_violations", {}).get("total", 0)
    rank_pct = round((1 - rank_v / max(total_jobs, 1)) * 100)

    src = results.get("job_source_breakdown", [])
    sms_cnt = next((r["count"] for r in src if r["source"] == "SMS"), 0)
    sms_pct = round(sms_cnt / max(total_jobs, 1) * 100) if total_jobs else 0

    crit_jobs = sum(r["total"] for r in results.get("critical_machinery_jobs", []))

    overall = round((equip_pct + dup_pct + rank_pct) / 3)

    return {
        "overall": overall,
        "equipment_completeness": equip_pct,
        "sms_coverage": sms_pct,
        "rank_compliance": rank_pct,
        "duplicate_ratio": dup_pct,
        "critical_jobs_configured": crit_jobs,
        "total_jobs": total_jobs,
    }
