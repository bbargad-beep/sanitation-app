# -*- coding: utf-8 -*-
"""
rules.py — כללי התיקון האוטומטי: בניית ספר כללים, מסכות, והחלטות משתמש
Rule ledger for the cleaning stage.

Why this module exists
----------------------
The cleaning stage produces tens of thousands of individual corrections
(~48,000 on a full-year municipal export).  Rendering them as 48,000 table
rows is unreviewable: a human cannot form a judgement about the pipeline by
scrolling a grid that large, and a per-row override mechanism means undoing a
single bad rule costs thousands of clicks.

But those 48,000 corrections are not 48,000 decisions.  Every correction is
produced by one of a small closed set of rules — a mapping-table entry, a
keyword group, a topic fallback, or an address-parsing route.  On the real
export that is ~50 distinct rules.  Reviewing 50 rules covers 100% of the
rows; reviewing a sample of rows covers a sample.

So this module inverts the unit of review:  build_ledger() groups every
correction by the rule that produced it, sorted by blast radius, and
rule_mask() maps a rule back to the exact rows it touched so a verdict can be
applied to all of them at once.

Rule identity
-------------
A rule_id is a stable string derived from (kind, before, after).  It must stay
stable across reruns and across re-uploads of the same source file, because
user verdicts are keyed on it and persisted.
"""

import hashlib
from typing import Optional

import pandas as pd

# ── Column names ────────────────────────────────────────────────────────────
COL_TICKET   = "מס' פניה"
COL_ORIG_SUB = "תת נושא"
COL_TOPIC    = "נושא"
COL_NEW_CAT  = "תת_נושא_חדש"
COL_CAT_SRC  = "סיווג_מקור"
COL_RESP     = "אחריות"
COL_RESP_SRC = "אחריות_מקור"
COL_RESP_KW  = "אחריות_מילה"
COL_ROUTE    = "מסלול_כתובת"
COL_STREET   = "רחוב_ראשי"
COL_HOUSE    = "מספר_בית"
COL_RAW_ADDR = "כתובת ואתר/מוסד"
COL_DESC     = "תיאור"
COL_CONF     = "_confidence"

# Column holding the reviewer's verdict, written back onto the data so that
# "auto-applied" and "auto-applied and a human approved the rule" stop looking
# identical downstream.
COL_VERDICT  = "_rule_verdict"

# Address routes that represent an actual parse (as opposed to "nothing matched")
REAL_ROUTES = {"std", "intersection", "range", "apt_suffix", "multi", "landmark"}

ROUTE_LABELS = {
    "std":          "כתובת רגילה (רחוב + מספר)",
    "intersection": "צומת שני רחובות",
    "range":        "טווח בתים",
    "apt_suffix":   "מספר בית עם סיומת דירה/קומה",
    "multi":        "מספרי בית מרובים",
    "landmark":     "ציון דרך (ללא מספר בית)",
    "empty":        "לא זוהתה כתובת",
}

# Human-readable name for each rule family, and which field it writes.
KIND_META = {
    "cat_map": {
        "label": "סיווג לפי טבלת מיפוי",
        "field": COL_NEW_CAT,
        "colour": "#16a34a",
    },
    "cat_fallback": {
        "label": "סיווג שנגזר מהנושא הראשי",
        "field": COL_NEW_CAT,
        "colour": "#d97706",
    },
    "cat_passthrough": {
        "label": "תת-נושא שלא זוהה — הועתק כמו שהוא",
        "field": COL_NEW_CAT,
        "colour": "#dc2626",
    },
    "resp_map": {
        "label": "אחריות לפי טבלת מיפוי",
        "field": COL_RESP,
        "colour": "#16a34a",
    },
    "resp_keyword": {
        "label": "אחריות שהוסקה ממילת מפתח בתיאור",
        "field": COL_RESP,
        "colour": "#d97706",
    },
    "resp_context": {
        "label": "אחריות שהוסקה מהקשר הפנייה",
        "field": COL_RESP,
        "colour": "#d97706",
    },
    "addr_route": {
        "label": "פירוק כתובת גולמית",
        "field": COL_STREET,
        "colour": "#2563a8",
    },
    "user": {
        "label": "החלטה שלך",
        "field": "",
        "colour": "#6366f1",
    },
}

# Verdicts a reviewer can give a rule.
VERDICT_APPROVED = "approved"
VERDICT_REJECTED = "rejected"
VERDICT_EDITED   = "edited"

VERDICT_LABELS = {
    VERDICT_APPROVED: "✅ אושר",
    VERDICT_REJECTED: "❌ נדחה",
    VERDICT_EDITED:   "✎ שונה",
}

# Sources written back when a reviewer overrules a rule.  These are deliberately
# distinct from the automatic sources so the provenance never claims a machine
# made a decision a human made.
SRC_REJECTED = "rule_rejected"
SRC_EDITED   = "rule_edited"


def _rid(kind: str, before: str, after: str) -> str:
    """Stable short id for a rule.  Hashed so Hebrew text is safe as a widget key."""
    raw = f"{kind}||{before}||{after}"
    return f"{kind}_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:10]}"


def _s(df: pd.DataFrame, col: str) -> pd.Series:
    """Column as a stripped string Series, or an empty-string Series if absent."""
    if col not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype=object)
    return df[col].fillna("").astype(str).str.strip()


def has_provenance(df: pd.DataFrame) -> bool:
    """True when the frame carries enough provenance to build a ledger at all."""
    return COL_CAT_SRC in df.columns or COL_RESP_SRC in df.columns or COL_ROUTE in df.columns


# ══════════════════════════════════════════════════════════════════════════
#  Masks — a rule maps back to the exact rows it produced
# ══════════════════════════════════════════════════════════════════════════

def rule_mask(df: pd.DataFrame, rule: dict) -> pd.Series:
    """
    Recompute the boolean row mask for a rule against the current frame.

    Masks are recomputed rather than stored as index lists because the frame is
    mutated between reruns (Q&A answers, overrides, re-uploads), and a stale
    index list would apply a bulk verdict to the wrong rows.
    """
    kind = rule["kind"]
    keys = rule.get("keys", {})
    false = pd.Series(False, index=df.index)

    if kind == "cat_map":
        if COL_CAT_SRC not in df.columns:
            return false
        return (_s(df, COL_CAT_SRC) == "map") & \
               (_s(df, COL_ORIG_SUB) == keys.get("before", "")) & \
               (_s(df, COL_NEW_CAT) == keys.get("after", ""))

    if kind == "cat_fallback":
        if COL_CAT_SRC not in df.columns:
            return false
        return (_s(df, COL_CAT_SRC) == "topic_fallback") & \
               (_s(df, COL_TOPIC) == keys.get("before", "")) & \
               (_s(df, COL_NEW_CAT) == keys.get("after", ""))

    if kind == "cat_passthrough":
        if COL_CAT_SRC not in df.columns:
            return false
        return (_s(df, COL_CAT_SRC) == "passthrough") & \
               (_s(df, COL_NEW_CAT) == keys.get("after", ""))

    if kind == "resp_map":
        if COL_RESP_SRC not in df.columns:
            return false
        return (_s(df, COL_RESP_SRC) == "map") & \
               (_s(df, COL_NEW_CAT) == keys.get("before", "")) & \
               (_s(df, COL_RESP) == keys.get("after", ""))

    if kind == "resp_keyword":
        if COL_RESP_SRC not in df.columns:
            return false
        m = _s(df, COL_RESP_SRC).str.startswith("keyword:") & \
            (_s(df, COL_RESP) == keys.get("after", ""))
        # Frames cleaned before אחריות_מילה existed have no keyword to match on;
        # such rules are built as a single per-responsibility group instead.
        if keys.get("before"):
            m &= (_s(df, COL_RESP_KW) == keys["before"])
        return m

    if kind == "resp_context":
        if COL_RESP_SRC not in df.columns:
            return false
        return (_s(df, COL_RESP_SRC) == "context_resolve") & \
               (_s(df, COL_NEW_CAT) == keys.get("before", "")) & \
               (_s(df, COL_RESP) == keys.get("after", ""))

    if kind == "addr_route":
        if COL_ROUTE not in df.columns:
            return false
        return (_s(df, COL_ROUTE) == keys.get("route", "")) & \
               (_s(df, COL_STREET) != "")

    if kind == "user":
        src = keys.get("src_col", "")
        if src not in df.columns:
            return false
        return _s(df, src) == keys.get("src_val", "")

    return false


# ══════════════════════════════════════════════════════════════════════════
#  Ledger construction
# ══════════════════════════════════════════════════════════════════════════

def _group(df: pd.DataFrame, mask: pd.Series, before_col, after_col,
           kind: str, n_examples: int, before_literal: Optional[str] = None) -> list:
    """
    Build one rule per distinct (before, after) pair inside `mask`.

    Vectorized on purpose: the previous per-row itertuples pass over 17k rows
    was the dominant cost of rendering this stage.
    """
    if not mask.any():
        return []
    sub = df[mask]
    before = (pd.Series([before_literal] * len(sub), index=sub.index)
              if before_literal is not None else _s(sub, before_col))
    after = _s(sub, after_col)
    out = []
    for (b, a), grp in pd.DataFrame({"b": before, "a": after}).groupby(["b", "a"], dropna=False):
        out.append({
            "rule_id": _rid(kind, str(b), str(a)),
            "kind": kind,
            "before": str(b) if str(b) else "(ריק)",
            "after": str(a) if str(a) else "(ריק)",
            "keys": {"before": str(b), "after": str(a)},
            "n_rows": int(len(grp)),
            "example_idx": list(grp.index[:n_examples]),
        })
    return out


def build_ledger(df: pd.DataFrame, n_examples: int = 3) -> list:
    """
    Return every rule that fired on this frame, sorted by rows touched, desc.

    Each entry:
      rule_id, kind, before, after, keys, n_rows, example_idx,
      kind_label, field, colour, user_made
    """
    if df is None or df.empty or not has_provenance(df):
        return []

    rules: list = []

    # ── Category ────────────────────────────────────────────────────────────
    if COL_CAT_SRC in df.columns:
        cat_src = _s(df, COL_CAT_SRC)
        rules += _group(df, cat_src == "map", COL_ORIG_SUB, COL_NEW_CAT,
                        "cat_map", n_examples)
        # The fallback path was previously invisible in the correction log even
        # though on a real export it accounts for every category assigned.
        rules += _group(df, cat_src == "topic_fallback", COL_TOPIC, COL_NEW_CAT,
                        "cat_fallback", n_examples)
        rules += _group(df, cat_src == "passthrough", None, COL_NEW_CAT,
                        "cat_passthrough", n_examples,
                        before_literal="(תת-נושא לא מוכר)")

    # ── Responsibility ──────────────────────────────────────────────────────
    if COL_RESP_SRC in df.columns:
        resp_src = _s(df, COL_RESP_SRC)
        rules += _group(df, resp_src == "map", COL_NEW_CAT, COL_RESP,
                        "resp_map", n_examples)

        kw_mask = resp_src.str.startswith("keyword:")
        if kw_mask.any():
            if COL_RESP_KW in df.columns and (_s(df, COL_RESP_KW) != "").any():
                rules += _group(df, kw_mask, COL_RESP_KW, COL_RESP,
                                "resp_keyword", n_examples)
            else:
                # Legacy frame: the matched keyword was never recorded, so the
                # finest honest grouping is one rule per resulting label.
                rules += _group(df, kw_mask, None, COL_RESP,
                                "resp_keyword", n_examples,
                                before_literal="")

        rules += _group(df, resp_src == "context_resolve", COL_NEW_CAT, COL_RESP,
                        "resp_context", n_examples)

    # ── Address routes ──────────────────────────────────────────────────────
    if COL_ROUTE in df.columns:
        route = _s(df, COL_ROUTE)
        street = _s(df, COL_STREET)
        for r in sorted(set(route) & REAL_ROUTES):
            m = (route == r) & (street != "")
            if not m.any():
                continue
            rules.append({
                "rule_id": _rid("addr_route", r, ""),
                "kind": "addr_route",
                "before": "כתובת גולמית מה-CRM",
                "after": ROUTE_LABELS.get(r, r),
                "keys": {"route": r},
                "n_rows": int(m.sum()),
                "example_idx": list(df.index[m][:n_examples]),
            })

    # ── Decisions the user already made (shown, never require approval) ─────
    for src_col, prefix in ((COL_RESP_SRC, "אחריות"), (COL_CAT_SRC, "סיווג")):
        if src_col not in df.columns:
            continue
        s = _s(df, src_col)
        # SRC_REJECTED / SRC_EDITED rows are already documented by the rule card
        # that produced the verdict (kept visible via merge_decided), so listing
        # them again here would double-count the same decision.
        for val in sorted(v for v in set(s) if v.startswith("user")):
            m = s == val
            if not m.any():
                continue
            rules.append({
                "rule_id": _rid("user", f"{src_col}:{val}", ""),
                "kind": "user",
                "before": prefix,
                "after": val,
                "keys": {"src_col": src_col, "src_val": val},
                "n_rows": int(m.sum()),
                "example_idx": list(df.index[m][:n_examples]),
            })

    for r in rules:
        meta = KIND_META.get(r["kind"], {})
        r["kind_label"] = meta.get("label", r["kind"])
        r["field"] = meta.get("field", "")
        r["colour"] = meta.get("colour", "#64748b")
        r["user_made"] = r["kind"] == "user"

    rules.sort(key=lambda x: x["n_rows"], reverse=True)
    return rules


# ══════════════════════════════════════════════════════════════════════════
#  Coverage — the number that replaces "48,000 corrections"
# ══════════════════════════════════════════════════════════════════════════

def merge_decided(ledger: list, decisions: dict) -> list:
    """
    Re-insert rules that a verdict removed from the data.

    Rejecting a rule withdraws its corrections, so the rule stops appearing in
    a freshly built ledger.  Left alone that would make the card vanish the
    moment it is acted on, and — worse — shrink the coverage denominator, so
    reviewing a rule by rejecting it would not count as having reviewed it.
    Each decision therefore carries a snapshot of the rule it ruled on, and
    those snapshots are merged back in here.
    """
    present = {r["rule_id"] for r in ledger}
    merged = list(ledger)
    for rid, d in decisions.items():
        snap = d.get("rule")
        if snap and rid not in present:
            merged.append({**snap, "withdrawn": True})
    merged.sort(key=lambda x: x["n_rows"], reverse=True)
    return merged


def coverage(rules: list, decisions: dict) -> dict:
    """
    How much of the corrected volume is covered by rules a human has ruled on.

    'Reviewed' deliberately counts approved + edited + rejected: what matters is
    that a human looked, not which way they went.  Rules the user themselves
    created are excluded from the denominator — approving your own edit is not
    evidence of anything.
    """
    auto = [r for r in rules if not r["user_made"]]
    total_rows = sum(r["n_rows"] for r in auto)
    reviewed_rows = sum(r["n_rows"] for r in auto if decisions.get(r["rule_id"]))
    approved_rows = sum(r["n_rows"] for r in auto
                        if (decisions.get(r["rule_id"]) or {}).get("verdict") == VERDICT_APPROVED)
    rejected_rows = sum(r["n_rows"] for r in auto
                        if (decisions.get(r["rule_id"]) or {}).get("verdict") == VERDICT_REJECTED)
    edited_rows = sum(r["n_rows"] for r in auto
                      if (decisions.get(r["rule_id"]) or {}).get("verdict") == VERDICT_EDITED)
    n_reviewed = sum(1 for r in auto if decisions.get(r["rule_id"]))
    return {
        "n_rules": len(auto),
        "n_reviewed": n_reviewed,
        "n_unreviewed": len(auto) - n_reviewed,
        "total_rows": total_rows,
        "reviewed_rows": reviewed_rows,
        "unreviewed_rows": total_rows - reviewed_rows,
        "approved_rows": approved_rows,
        "rejected_rows": rejected_rows,
        "edited_rows": edited_rows,
        "pct_reviewed": round(reviewed_rows / total_rows * 100) if total_rows else 0,
    }


def pareto(rules: list, target_pct: int = 90) -> int:
    """How many rules, largest first, are needed to cover target_pct of rows."""
    auto = [r for r in rules if not r["user_made"]]
    total = sum(r["n_rows"] for r in auto)
    if not total:
        return 0
    run = 0
    for i, r in enumerate(sorted(auto, key=lambda x: x["n_rows"], reverse=True), 1):
        run += r["n_rows"]
        if run / total * 100 >= target_pct:
            return i
    return len(auto)


# ══════════════════════════════════════════════════════════════════════════
#  Applying a verdict to every row the rule touched
# ══════════════════════════════════════════════════════════════════════════

def apply_verdict(df: pd.DataFrame, rule: dict, verdict: str,
                  new_value: str = "") -> tuple:
    """
    Apply a rule-level verdict to all rows the rule produced.

    Returns (df, n_rows_affected).  The frame is modified in place and also
    returned, matching the convention used elsewhere in the pipeline.

      approved — stamp COL_VERDICT so downstream can tell verified rows from
                 merely-automatic ones.  Values are not touched.
      rejected — the machine's answer is withdrawn: the field is reset to the
                 project's "unknown" value, provenance is relabelled, and the
                 rows drop to low confidence so they surface for manual work.
                 Address parses cannot be un-parsed, so those rows are only
                 flagged for review rather than blanked.
      edited   — every row gets the reviewer's value, provenance relabelled.
    """
    mask = rule_mask(df, rule)
    n = int(mask.sum())
    if n == 0:
        return df, 0

    if COL_VERDICT not in df.columns:
        df[COL_VERDICT] = ""
    df.loc[mask, COL_VERDICT] = verdict

    kind = rule["kind"]
    field = rule.get("field", "")

    if verdict == VERDICT_APPROVED:
        return df, n

    if verdict == VERDICT_EDITED and new_value:
        if field and field in df.columns:
            df.loc[mask, field] = new_value
        if kind.startswith("cat") and COL_CAT_SRC in df.columns:
            df.loc[mask, COL_CAT_SRC] = SRC_EDITED
        if kind.startswith("resp") and COL_RESP_SRC in df.columns:
            df.loc[mask, COL_RESP_SRC] = SRC_EDITED
        return df, n

    if verdict == VERDICT_REJECTED:
        if kind == "addr_route":
            # A parsed address has no meaningful "undo" — the raw string is
            # still there.  Flag for manual work instead of destroying data.
            if COL_CONF in df.columns:
                df.loc[mask, COL_CONF] = "low"
            return df, n
        if kind.startswith("cat"):
            if COL_NEW_CAT in df.columns:
                df.loc[mask, COL_NEW_CAT] = "לא מסווג"
            if COL_CAT_SRC in df.columns:
                df.loc[mask, COL_CAT_SRC] = SRC_REJECTED
        if kind.startswith("resp"):
            if COL_RESP in df.columns:
                df.loc[mask, COL_RESP] = "א.מ.ל"
            if COL_RESP_SRC in df.columns:
                df.loc[mask, COL_RESP_SRC] = SRC_REJECTED
        if COL_CONF in df.columns:
            df.loc[mask, COL_CONF] = "low"
        return df, n

    return df, n


# ══════════════════════════════════════════════════════════════════════════
#  Explanations shown on a rule card
# ══════════════════════════════════════════════════════════════════════════

def explain(rule: dict) -> str:
    """One plain-Hebrew sentence describing what the rule does."""
    b, a = rule["before"], rule["after"]
    kind = rule["kind"]
    if kind == "cat_map":
        return f'כל פנייה שתת-הנושא שלה "{b}" מסווגת לקטגוריה "{a}".'
    if kind == "cat_fallback":
        return (f'תת-הנושא ריק בייצוא ה-CRM, ולכן הקטגוריה נגזרה מהנושא הראשי '
                f'"{b}" → "{a}". זהו כלל חלש יותר ממיפוי ישיר.')
    if kind == "cat_passthrough":
        return (f'תת-הנושא לא נמצא בטבלת המיפוי, ולכן הועתק כמו שהוא ל-"{a}" '
                f'ללא סיווג אמיתי.')
    if kind == "resp_map":
        return f'כל פנייה בקטגוריה "{b}" מקבלת אחריות "{a}".'
    if kind == "resp_keyword":
        if b and b != "(ריק)":
            return (f'פניות שהתיאור שלהן מכיל את המילה "{b}" קיבלו אחריות "{a}". '
                    f'המילה מסומנת בדוגמאות למטה.')
        return (f'פניות שקיבלו אחריות "{a}" ממילת מפתח בתיאור. '
                f'המילה עצמה לא נשמרה בקובץ זה — הריצו את שלב הניקוי מחדש כדי לראותה.')
    if kind == "resp_context":
        return (f'פניות בקטגוריה "{b}" שכבר טופלו — האחריות נקבעה כ-"{a}" מהקשר '
                f'הפנייה ולא ממילה מפורשת.')
    if kind == "addr_route":
        return f'הכתובת הגולמית פורקה לרחוב ומספר בית לפי הדפוס: {a}.'
    if kind == "user":
        return f'{rule["n_rows"]:,} שורות שנקבעו על ידך ({a}).'
    return ""


def highlight(text: str, needle: str) -> str:
    """
    Return `text` with every occurrence of `needle` wrapped in a <mark>.

    Used to show the reviewer exactly which words in the description triggered
    a keyword rule, so a decision can be checked at a glance instead of trusted.
    """
    if not needle or not text:
        return text or ""
    out, low_needle = [], needle
    i = 0
    while True:
        j = text.find(low_needle, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append(f'<mark style="background:#fde68a;padding:0 2px;border-radius:3px;">'
                   f'{text[j:j + len(low_needle)]}</mark>')
        i = j + len(low_needle)
    return "".join(out)
