# -*- coding: utf-8 -*-
"""
validation.py — מצב אימות: השוואה בין פלט הצינור לקובץ יחוס
Herzliya Municipality — Pipeline output vs. reference comparison.

compare_to_reference(pipeline_df, reference_df) joins on מס' פניה and
returns a per-column agreement report plus a joined diff DataFrame.
"""

import pandas as pd
import numpy as np

JOIN_COL = "מס' פניה"


def compare_to_reference(
    pipeline_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    columns: list = None,
) -> dict:
    """
    Compare pipeline output to a human-verified reference on a per-column basis.

    Parameters
    ----------
    pipeline_df   : output of the pipeline (after geocode/enrich)
    reference_df  : ground-truth / hand-corrected reference file
    columns       : columns to compare; defaults to intersection of both dfs
                    (excluding the join key and internal _cols)

    Returns
    -------
    {
        "matched_rows"  : int,           # rows present in both files
        "only_pipeline" : int,           # rows in pipeline not in reference
        "only_reference": int,           # rows in reference not in pipeline
        "per_column"    : pd.DataFrame,  # columns: עמודה, הסכמה, שונה, חסר_בציר, אחוז_הסכמה
        "diff"          : pd.DataFrame,  # joined, one row per matched pair
    }
    """
    pid = JOIN_COL
    if pid not in pipeline_df.columns:
        raise ValueError(f"pipeline_df missing join column: {pid!r}")
    if pid not in reference_df.columns:
        raise ValueError(f"reference_df missing join column: {pid!r}")

    p = pipeline_df.copy().astype({pid: str})
    r = reference_df.copy().astype({pid: str})

    p_ids = set(p[pid])
    r_ids = set(r[pid])
    matched_ids = p_ids & r_ids

    result_meta = {
        "matched_rows":   len(matched_ids),
        "only_pipeline":  len(p_ids - r_ids),
        "only_reference": len(r_ids - p_ids),
    }

    # Restrict to matched rows
    p_matched = p[p[pid].isin(matched_ids)].set_index(pid)
    r_matched = r[r[pid].isin(matched_ids)].set_index(pid)

    # Determine columns to compare
    if columns is None:
        cols_p = {c for c in p.columns if not c.startswith("_") and c != pid}
        cols_r = {c for c in r.columns if not c.startswith("_") and c != pid}
        compare_cols = sorted(cols_p & cols_r)
    else:
        compare_cols = [c for c in columns if c != pid]

    # Per-column agreement
    per_col_rows = []
    for col in compare_cols:
        if col not in p_matched.columns or col not in r_matched.columns:
            continue
        pv = p_matched[col].reindex(r_matched.index)
        rv = r_matched[col]

        # Normalise: strip whitespace, lower for strings
        def _norm(s):
            s = s.copy()
            str_mask = s.apply(lambda x: isinstance(x, str))
            s[str_mask] = s[str_mask].str.strip().str.lower()
            return s

        pv_n = _norm(pv.astype(str).fillna(""))
        rv_n = _norm(rv.astype(str).fillna(""))

        agree   = int((pv_n == rv_n).sum())
        differ  = int((pv_n != rv_n).sum())
        missing = int(pv.isna().sum())
        total   = agree + differ
        pct     = round(agree / total * 100, 1) if total > 0 else None
        per_col_rows.append({
            "עמודה":       col,
            "הסכמה":       agree,
            "שונה":        differ,
            "חסר_בצינור":  missing,
            "אחוז_הסכמה":  pct,
        })

    per_column_df = pd.DataFrame(per_col_rows)

    # Build diff DataFrame — joined on ticket ID, suffixed _צינור / _יחוס
    diff_df = p_matched[compare_cols].join(
        r_matched[[c for c in compare_cols if c in r_matched.columns]],
        lsuffix="_צינור", rsuffix="_יחוס",
    ).reset_index()

    return {
        "matched_rows":   result_meta["matched_rows"],
        "only_pipeline":  result_meta["only_pipeline"],
        "only_reference": result_meta["only_reference"],
        "per_column":     per_column_df,
        "diff":           diff_df,
    }
