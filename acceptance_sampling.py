# -*- coding: utf-8 -*-
"""
acceptance_sampling.py — דגימה לקבלה אפס-פגמים לפי רמת גאוקוד
Herzliya Municipality — Zero-acceptance sampling per geocode precision tier.

Zero-acceptance plan: a lot is ACCEPTED when 0 defects are found in the sample;
REJECTED when ≥1 defect is found.  Sample sizes are derived from the Poisson
approximation: to achieve consumer risk β of finding 0 defects when the true
defect rate is p_reject, the sample size is:

    n = ceil(-ln(β) / p_reject)

Default: β = 0.10 (90% chance of rejection if true rate ≥ p_reject).
"""

import math
import random
import pandas as pd
import numpy as np
from typing import Callable, Optional

# Geocode precision tier column (written by geocode_pipeline)
PRECISION_COL = "דיוק_גאוקוד"

# Known tiers in descending quality order
PRECISION_TIERS = ["address", "near_address", "street", "none"]

# Default per-tier reject threshold (true defect rate that should trigger rejection)
# "address" tier: expect ≤ 5% errors → reject if ≥ 5%
# "street"  tier: expect ≤ 15% errors → reject if ≥ 15%
DEFAULT_P_REJECT = {
    "address":      0.05,
    "near_address": 0.10,
    "street":       0.15,
    "none":         1.00,  # all ungeocoded = defect by definition
}

DEFAULT_BETA = 0.10   # consumer risk


def sample_size(lot_size: int, p_reject: float, beta: float = DEFAULT_BETA) -> int:
    """
    Compute zero-acceptance sample size for a lot.

    n = ceil(-ln(β) / p_reject), capped at lot_size.
    Returns 0 if lot_size == 0.
    """
    if lot_size == 0:
        return 0
    if p_reject <= 0 or p_reject > 1:
        raise ValueError(f"p_reject must be in (0, 1], got {p_reject}")
    if beta <= 0 or beta >= 1:
        raise ValueError(f"beta must be in (0, 1), got {beta}")
    n = math.ceil(-math.log(beta) / p_reject)
    return min(n, lot_size)


def draw_sample(df: pd.DataFrame, n: int, seed: Optional[int] = None) -> pd.DataFrame:
    """Draw n rows from df without replacement (or all rows if n >= len(df))."""
    if n <= 0 or df.empty:
        return df.iloc[:0].copy()
    n = min(n, len(df))
    rng = random.Random(seed)
    idx = rng.sample(list(df.index), n)
    return df.loc[idx].copy()


def _is_defect(row: pd.Series, tier: str) -> bool:
    """
    A row is a defect if:
      - tier == "address"/"near_address": lat/lon is missing or outside Herzliya
      - tier == "street": lat/lon is missing
      - tier == "none": always a defect (ungeocoded)
    """
    from flags import HERZLIYA_BOUNDS
    lat = pd.to_numeric(str(row.get("קו_רוחב", "")).replace(",", ""), errors="coerce")
    lon = pd.to_numeric(str(row.get("קו_אורך", "")).replace(",", ""), errors="coerce")

    if pd.isna(lat) or pd.isna(lon):
        return True
    if tier in ("address", "near_address"):
        in_bounds = (
            HERZLIYA_BOUNDS["lat_min"] <= lat <= HERZLIYA_BOUNDS["lat_max"] and
            HERZLIYA_BOUNDS["lon_min"] <= lon <= HERZLIYA_BOUNDS["lon_max"]
        )
        return not in_bounds
    return False   # street tier: has coords → not a defect


def run_sampling_plan(
    df: pd.DataFrame,
    p_reject: dict = None,
    beta: float = DEFAULT_BETA,
    seed: Optional[int] = None,
    defect_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Run a zero-acceptance sampling plan across all geocode precision tiers.

    Parameters
    ----------
    df        : pipeline output DataFrame (must have PRECISION_COL)
    p_reject  : dict mapping tier → reject threshold (defaults to DEFAULT_P_REJECT)
    beta      : consumer risk (default 0.10)
    seed      : random seed for reproducible samples
    defect_fn : optional callable(row, tier) → bool overriding _is_defect

    Returns
    -------
    DataFrame with one row per tier:
      tier | lot_size | sample_n | defects | verdict | defect_pct
    """
    if p_reject is None:
        p_reject = DEFAULT_P_REJECT
    if defect_fn is None:
        defect_fn = _is_defect

    if PRECISION_COL not in df.columns:
        tiers_present = {"(all)": df}
    else:
        tiers_present = {}
        for tier in PRECISION_TIERS:
            subset = df[df[PRECISION_COL] == tier]
            if not subset.empty:
                tiers_present[tier] = subset

    rows = []
    for tier, subset in tiers_present.items():
        lot = len(subset)
        pr  = p_reject.get(tier, DEFAULT_P_REJECT.get(tier, 0.10))
        n   = sample_size(lot, pr, beta)
        sample = draw_sample(subset, n, seed=seed)

        defects = int(sum(defect_fn(row, tier) for _, row in sample.iterrows()))
        verdict = "✅ קבל" if defects == 0 else "❌ דחה"
        defect_pct = round(defects / n * 100, 1) if n > 0 else None

        rows.append({
            "רמת_גאוקוד":  tier,
            "גודל_מנה":    lot,
            "גודל_דגימה":  n,
            "פגמים":       defects,
            "פסיקה":       verdict,
            "אחוז_פגמים":  defect_pct,
        })

    return pd.DataFrame(rows)
