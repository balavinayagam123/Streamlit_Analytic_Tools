"""
matcher.py
Resolves machinery name variants from vessel data against the canonical list
using the transform map (exact) and rapidfuzz (fuzzy fallback).
"""
from rapidfuzz import process, fuzz
import pandas as pd


EXACT_THRESHOLD = 90   # score >= this → auto-accept suggestion
SUGGEST_THRESHOLD = 70 # score >= this → show as suggestion, user must accept


def build_lookup(transform_map: list[dict]) -> dict[str, str]:
    """Build a dict {variant_lower: canonical} from the transform map."""
    return {entry["variant"].lower(): entry["canonical"] for entry in transform_map}


def resolve_names(
    names: list[str],
    canonical_list: list[str],
    transform_map: list[dict],
) -> dict[str, dict]:
    """
    For each name in `names`, attempt to resolve to a canonical machinery name.

    Returns dict keyed by original name:
      {
        "original_name": {
          "canonical": str | None,
          "score": int,
          "status": "exact" | "fuzzy_auto" | "fuzzy_suggest" | "unresolved",
        }
      }
    """
    lookup = build_lookup(transform_map)
    canonical_lower = {c.lower(): c for c in canonical_list}
    results = {}

    for name in names:
        name_stripped = name.strip()
        name_lower = name_stripped.lower()

        # 1. Exact match in transform map
        if name_lower in lookup:
            results[name_stripped] = {
                "canonical": lookup[name_lower],
                "score": 100,
                "status": "exact",
            }
            continue

        # 2. Exact match against canonical list (case-insensitive)
        if name_lower in canonical_lower:
            results[name_stripped] = {
                "canonical": canonical_lower[name_lower],
                "score": 100,
                "status": "exact",
            }
            continue

        # 3. Fuzzy match against canonical list
        match = process.extractOne(
            name_stripped,
            canonical_list,
            scorer=fuzz.token_sort_ratio,
        )
        if match:
            best_name, score, _ = match
            if score >= EXACT_THRESHOLD:
                results[name_stripped] = {
                    "canonical": best_name,
                    "score": score,
                    "status": "fuzzy_auto",
                }
            elif score >= SUGGEST_THRESHOLD:
                results[name_stripped] = {
                    "canonical": best_name,
                    "score": score,
                    "status": "fuzzy_suggest",
                }
            else:
                results[name_stripped] = {
                    "canonical": None,
                    "score": score,
                    "status": "unresolved",
                }
        else:
            results[name_stripped] = {
                "canonical": None,
                "score": 0,
                "status": "unresolved",
            }

    return results


def apply_resolutions(df: pd.DataFrame, resolutions: dict, col: str = "Machinery Location") -> pd.DataFrame:
    """Add a 'Canonical Machinery' column to df based on resolved names."""
    df = df.copy()
    df["Canonical Machinery"] = df[col].map(
        lambda x: resolutions.get(str(x).strip(), {}).get("canonical") or str(x).strip()
    )
    return df
