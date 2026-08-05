# -*- coding: utf-8 -*-
"""
spot_check.py — Human-oracle spot-check with zero-acceptance sampling.

Reuses the zero-acceptance math from acceptance_sampling.py but replaces
the machine oracle (_is_defect) with a human reviewing one row at a time.

Stratification
--------------
Stage 2 (cleaning): groups rows by (סיווג_מקור, אחריות_מקור) — i.e. by the
decision path that produced the classification and responsibility labels.

Stage 3 (geocoding): groups rows by (מסלול_כתובת, דיוק_גאוקוד) — i.e. by
the address-parsing route and the geocode precision tier.

Within each stratum we draw a zero-acceptance sample.  The user reviews
each sampled row and says "correct" or "wrong".  At β=0.10, p_reject=0.05,
that's 47 rows per stratum — curtailed at the first defect.  Note that the
total workload is 47 × (number of strata), which on a real export is several
hundred rows, not fifty; the UI must quote the figure from the actual plan.

A row the reviewer marks "not sure" is recorded as `unknown`, never as a pass.
Its stratum becomes `incomplete`, because a zero-acceptance plan only licenses
an accept when the whole sample was actually judged.

Acceptance card
---------------
build_acceptance_card() produces a dict that records:
  stage, timestamp, strata (lot/sample/defects/verdict per stratum),
  overall_claim, sample_ticket_ids, run_id.
This card is stored in session state and written into the Excel export.
"""

import math
import random
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

# ── Sample-size formula (same as acceptance_sampling.py) ────────────────────

DEFAULT_P_REJECT = 0.05
DEFAULT_BETA = 0.10


def sample_size(lot_size: int, p_reject: float = DEFAULT_P_REJECT,
                beta: float = DEFAULT_BETA) -> int:
    if lot_size == 0:
        return 0
    n = math.ceil(-math.log(beta) / p_reject)
    return min(n, lot_size)


# ── Stratification ──────────────────────────────────────────────────────────

CLEAN_STRATA_COLS = ["סיווג_מקור", "אחריות_מקור"]
GEOCODE_STRATA_COLS = ["מסלול_כתובת", "דיוק_גאוקוד"]


def _stratum_label(keys: dict) -> str:
    """Human-readable label for a stratum dict."""
    parts = []
    labels = {
        "סיווג_מקור": "סיווג",
        "אחריות_מקור": "אחריות",
        "מסלול_כתובת": "מסלול",
        "דיוק_גאוקוד": "דיוק",
    }
    for k, v in keys.items():
        nice_key = labels.get(k, k)
        parts.append(f"{nice_key}: {v}")
    return " · ".join(parts) if parts else "(הכל)"


def stratify(df: pd.DataFrame, strata_cols: list,
             min_stratum_size: int = 5) -> dict:
    """
    Group df by strata_cols.  Returns {label: (keys_dict, sub_df)}.
    Strata with fewer than min_stratum_size rows are merged into "(אחר)".
    """
    present = [c for c in strata_cols if c in df.columns]
    if not present:
        return {"(הכל)": ({}, df)}

    grouped = df.groupby(present, dropna=False)
    strata = {}
    other_frames = []

    for keys, sub in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        keys_dict = {c: str(k) if pd.notna(k) else "—" for c, k in zip(present, keys)}
        label = _stratum_label(keys_dict)
        if len(sub) < min_stratum_size:
            other_frames.append(sub)
        else:
            strata[label] = (keys_dict, sub)

    if other_frames:
        other_df = pd.concat(other_frames)
        strata["(אחר)"] = ({"סיווג": "מעורב"}, other_df)

    return strata


# ── Drawing a sample per stratum ────────────────────────────────────────────

def build_sample_plan(df: pd.DataFrame, strata_cols: list,
                      p_reject: float = DEFAULT_P_REJECT,
                      beta: float = DEFAULT_BETA,
                      seed: Optional[int] = 42) -> list:
    """
    Return a list of dicts, one per stratum:
      {label, keys, lot_size, sample_n, sample_indices, sample_tickets}
    """
    strata = stratify(df, strata_cols)
    rng = random.Random(seed)
    plan = []

    for label, (keys, sub) in strata.items():
        lot = len(sub)
        n = sample_size(lot, p_reject, beta)
        indices = rng.sample(list(sub.index), min(n, lot))
        tickets = []
        if "מס' פניה" in sub.columns:
            tickets = [str(sub.at[i, "מס' פניה"]) for i in indices]
        plan.append({
            "label": label,
            "keys": keys,
            "lot_size": lot,
            "sample_n": n,
            "sample_indices": indices,
            "sample_tickets": tickets,
        })

    plan.sort(key=lambda s: s["lot_size"], reverse=True)
    return plan


# ── What to show the reviewer ──────────────────────────────────────────────

def row_for_review(df: pd.DataFrame, idx, stage: str) -> dict:
    """
    Extract the fields needed for a single review card.
    Returns a dict with 'original' (CRM text) and 'decision' (machine output).
    """
    row = df.loc[idx]

    def _g(col, default=""):
        v = row.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return str(v).strip() or default

    original = {
        "מס' פניה": _g("מס' פניה"),
        "נושא": _g("נושא"),
        "תת נושא": _g("תת נושא"),
        "תיאור": _g("תיאור"),
        "כתובת גולמית": _g("כתובת ואתר/מוסד"),
        "סטטוס": _g("סטטוס פנייה"),
    }

    if stage == "clean":
        decision = {
            "קטגוריה חדשה": _g("תת_נושא_חדש"),
            "אחריות": _g("אחריות"),
            "שיטת סיווג": _g("סיווג_מקור"),
            "שיטת אחריות": _g("אחריות_מקור"),
            "פירוט": _g("_confidence_details"),
        }
    elif stage == "geocode":
        decision = {
            "רחוב": _g("רחוב_ראשי"),
            "מספר בית": _g("מספר_בית"),
            "קו רוחב": _g("קו_רוחב"),
            "קו אורך": _g("קו_אורך"),
            "מסלול כתובת": _g("מסלול_כתובת"),
            "דיוק": _g("דיוק_גאוקוד"),
            "שיטה": _g("geocode_method", "—"),
        }
    else:
        decision = {}

    return {"original": original, "decision": decision}


# ── Acceptance card builder ─────────────────────────────────────────────────

def build_acceptance_card(stage: str, strata_results: list,
                          p_reject: float, beta: float,
                          run_id: str = "") -> dict:
    """
    Produce a structured acceptance card from completed spot-check results.

    strata_results is a list of dicts, one per stratum:
      {label, lot_size, sample_n, reviewed, defects, verdict, sample_tickets}

    Returns a card dict ready for storage and Excel export.
    """
    total_lot = sum(s["lot_size"] for s in strata_results)
    total_reviewed = sum(s["reviewed"] for s in strata_results)
    total_defects = sum(s["defects"] for s in strata_results)
    total_unknown = sum(s.get("unknown", 0) for s in strata_results)
    all_passed = all(s["verdict"] == "pass" for s in strata_results)
    # A stratum whose sample was not fully judged has not satisfied its
    # zero-acceptance plan, so it cannot contribute to a pass.
    incomplete = [s for s in strata_results if s["verdict"] == "incomplete"]

    detect_pct = round((1 - beta) * 100)
    if incomplete:
        claim = (f"נבדקו {total_reviewed} שורות מתוך {total_lot:,}, "
                 f"ו-{total_unknown} סומנו כ״לא בטוח״. "
                 f"{len(incomplete)} שכבות לא הושלמו, ולכן לא ניתן לקבוע פסיקה. "
                 f"השלימו את הבדיקה או בקשו דגימה חלופית.")
    elif all_passed:
        claim = (f"נבדקו {total_reviewed} שורות מתוך {total_lot:,}. "
                 f"נמצאו 0 שגיאות. "
                 f"אילו שיעור השגיאה האמיתי היה {p_reject*100:.0f}% או יותר, "
                 f"היה סיכוי של {detect_pct}% שהבדיקה הייתה מגלה זאת.")
    else:
        claim = (f"נבדקו {total_reviewed} שורות מתוך {total_lot:,}. "
                 f"נמצאו {total_defects} שגיאות. "
                 f"אי אפשר להבטיח ששיעור השגיאה נמוך מ-{p_reject*100:.0f}%.")

    return {
        "stage": stage,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "p_reject": p_reject,
        "beta": beta,
        "claim": claim,
        "passed": all_passed and not incomplete,
        "incomplete": bool(incomplete),
        "total_lot": total_lot,
        "total_reviewed": total_reviewed,
        "total_defects": total_defects,
        "total_unknown": total_unknown,
        "strata": strata_results,
        "run_id": run_id,
    }


def card_to_dataframe(card: dict) -> pd.DataFrame:
    """Convert an acceptance card's strata into a summary DataFrame for export."""
    _v = {"pass": "✅ עבר", "fail": "❌ נכשל", "incomplete": "⚠️ לא הושלם"}
    rows = []
    for s in card["strata"]:
        rows.append({
            "שכבה": s["label"],
            "גודל_מנה": s["lot_size"],
            "גודל_דגימה": s["sample_n"],
            "נבדקו": s["reviewed"],
            "לא בטוח": s.get("unknown", 0),
            "שגיאות": s["defects"],
            "פסיקה": _v.get(s["verdict"], s["verdict"]),
        })
    rows.append({
        "שכבה": "סה״כ",
        "גודל_מנה": card["total_lot"],
        "גודל_דגימה": "",
        "נבדקו": card["total_reviewed"],
        "לא בטוח": card.get("total_unknown", 0),
        "שגיאות": card["total_defects"],
        "פסיקה": ("⚠️ לא הושלם" if card.get("incomplete")
                  else ("✅ עבר" if card["passed"] else "❌ נכשל")),
    })
    return pd.DataFrame(rows)
