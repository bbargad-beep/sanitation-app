# -*- coding: utf-8 -*-
# SYNC TEST 2 - 2026-07-16
"""
app.py — מערכת עיבוד פניות תברואה | עיריית הרצליה
Staged pipeline: העלאה → ניקוי → גאוקוד → העשרה → פלט
Wraps clean_pipeline, geocode_pipeline, enrich_pipeline, flags, heatmap.
"""

import io
import re
import sys
import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="מערכת עיבוד פניות תברואה | הרצליה",
    page_icon="🗑️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Import pipeline modules ─────────────────────────────────────────────────
sys.path.insert(0, ".")
_IMPORT_ERR = None
try:
    import clean_pipeline as cp
    import geocode_pipeline as gp
    import enrich_pipeline as ep
    import flags as fl
    import heatmap as hm
    import audit_log as al
    MODULES_OK = True
except Exception as e:
    MODULES_OK = False
    _IMPORT_ERR = str(e)

# ── RTL + CSS (preserves existing visual identity) ──────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family:'Heebo',Arial,sans-serif; direction:rtl; }
.stApp { direction:rtl; }
h1,h2,h3,p,div,span,label { direction:rtl; text-align:right; }
.main-header {
  background:linear-gradient(135deg,#1a3a5c 0%,#2563a8 100%); color:white;
  padding:1.6rem 2rem; border-radius:12px; margin-bottom:1.4rem; text-align:right;
}
.main-header h1 { color:white; font-size:1.8rem; font-weight:700; margin:0 0 .3rem 0; }
.main-header p  { color:#c8d9f0; font-size:.92rem; margin:0; }

/* Stepper */
.stepper { display:flex; flex-direction:row-reverse; gap:0; margin-bottom:1.6rem;
           background:white; border:1px solid #e2e8f0; border-radius:12px; padding:.5rem; }
.step { flex:1; text-align:center; padding:.7rem .4rem; border-radius:8px;
        font-size:.85rem; color:#94a3b8; position:relative; }
.step.active { background:#2563a8; color:white; font-weight:600; }
.step.done   { color:#059669; font-weight:500; }
.step .num { display:inline-block; width:22px; height:22px; line-height:22px;
             border-radius:50%; background:#e2e8f0; color:#64748b; font-size:.78rem;
             margin-left:6px; }
.step.active .num { background:white; color:#2563a8; }
.step.done .num   { background:#059669; color:white; }

.stat-row { display:flex; gap:1rem; margin-bottom:1.2rem; flex-direction:row-reverse; }
.stat-card { flex:1; background:white; border:1px solid #e2e8f0; border-radius:10px;
             padding:1rem 1.2rem; text-align:center; box-shadow:0 1px 4px rgba(0,0,0,.06); }
.stat-card .num { font-size:1.9rem; font-weight:700; color:#1a3a5c; }
.stat-card .lbl { font-size:.78rem; color:#64748b; margin-top:.2rem; }
.stat-card.warn .num { color:#d97706; } .stat-card.good .num { color:#059669; }
.stat-card.alert .num { color:#dc2626; }

.step-card { background:#f8fafc; border-right:4px solid #2563a8; border-radius:8px;
             padding:.9rem 1.1rem; margin-bottom:.8rem; direction:rtl; }
.step-card h4 { color:#1a3a5c; font-size:.93rem; font-weight:600; margin:0 0 .3rem 0; }
.step-card p  { color:#475569; font-size:.86rem; margin:0; line-height:1.6; }

.banner-success { background:#d1fae5; border:1px solid #6ee7b7; border-radius:8px;
  padding:.8rem 1.2rem; color:#065f46; font-weight:500; margin-bottom:1rem; direction:rtl; text-align:right; }
.banner-error { background:#fee2e2; border:1px solid #fca5a5; border-radius:8px;
  padding:.8rem 1.2rem; color:#991b1b; font-weight:500; margin-bottom:1rem; direction:rtl; text-align:right; }
.banner-warn { background:#fef3c7; border:1px solid #fcd34d; border-radius:8px;
  padding:.8rem 1.2rem; color:#92400e; font-weight:500; margin-bottom:1rem; direction:rtl; text-align:right; }

.stTabs [data-baseweb="tab-list"] { flex-direction:row-reverse; }
.stTabs [data-baseweb="tab"] { direction:rtl; }
.dataframe { direction:rtl; }

/* ── Dataframe scroll + cell readability ── */
/* Allow the dataframe container to scroll horizontally */
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {
    overflow-x: auto !important;
    max-width: 100% !important;
}
/* Each column header and cell: don't let RTL hide text off the left edge.
   ellipsis + LTR inside each cell keeps Hebrew readable without clipping. */
[data-testid="stDataFrame"] [role="columnheader"],
[data-testid="stDataFrame"] [role="gridcell"] {
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    direction: rtl !important;
    text-align: right !important;
    padding-right: 8px !important;
    padding-left: 4px !important;
}
/* Streamlit new dataframe (glide-data-grid) canvas fallback: ensure wrapper scrolls */
.stDataFrame > div { overflow-x: auto !important; }

/* ── Hover tooltips ── */
.tip-wrap { display:inline-block; position:relative; cursor:help; }
.tip-icon { color:#6366f1; font-size:.9rem; vertical-align:middle; }
.tip-box {
  display:none; position:absolute;
  right:0; top:1.5rem;
  background:#1e293b; color:#f8fafc;
  border-radius:10px; padding:.65rem 1rem;
  font-size:.78rem; line-height:1.65;
  width:290px; z-index:9999;
  direction:rtl; text-align:right;
  box-shadow:0 6px 20px rgba(0,0,0,.35);
  white-space:normal; pointer-events:none;
}
.tip-wrap:hover .tip-box { display:block; }
</style>
""", unsafe_allow_html=True)

# ── Constants ───────────────────────────────────────────────────────────────
DATE_MIN = "2026-01-01"
DATE_MAX = "2026-05-31"
STAGES = [
    ("upload",  "העלאה"),
    ("clean",   "ניקוי"),
    ("geocode", "גאוקוד"),
    ("enrich",  "העשרה"),
    ("output",  "פלט וניתוח"),
]
REQUIRED_COLS = {
    "מס' פניה": "מספר הפניה",
    "תאריך ושעת פתיחה": "תאריך ושעה",
    "כתובת ואתר/מוסד": "כתובת",
    "תת נושא": "תת-נושא",
}

# ── Persistent state (survives Streamlit disconnections) ────────────────────
import os, tempfile, pickle, hashlib

_STATE_FILE = os.path.join(tempfile.gettempdir(), "herzliya_sanitation_app_state.pkl")

def _save_state():
    """Persist all session state to disk."""
    try:
        state = {
            "stage":    st.session_state.get("stage", "upload"),
            "df":       st.session_state.get("df"),
            "filename": st.session_state.get("filename", ""),
            "stats":    st.session_state.get("stats", {}),
            "geocoded": st.session_state.get("geocoded", False),
            "enriched": st.session_state.get("enriched", False),
        }
        with open(_STATE_FILE, "wb") as f:
            pickle.dump(state, f)
    except Exception:
        pass

def _load_state():
    """Load persisted state from disk into session state (only on first load)."""
    if st.session_state.get("_state_loaded"):
        return
    st.session_state["_state_loaded"] = True
    if not os.path.exists(_STATE_FILE):
        return
    try:
        with open(_STATE_FILE, "rb") as f:
            state = pickle.load(f)
        # Only restore if we have real data
        if state.get("df") is not None and len(state["df"]) > 0:
            for k, v in state.items():
                st.session_state.setdefault(k, v)
            st.session_state["_just_restored"] = True
    except Exception:
        pass

def _clear_state():
    """Delete persisted state file."""
    try:
        if os.path.exists(_STATE_FILE):
            os.remove(_STATE_FILE)
    except Exception:
        pass

def _init_state():
    _load_state()
    ss = st.session_state
    ss.setdefault("stage", "upload")
    ss.setdefault("df", None)
    ss.setdefault("filename", "")
    ss.setdefault("stats", {})
    ss.setdefault("geocoded", False)
    ss.setdefault("enriched", False)

_init_state()

def goto(stage):
    st.session_state.stage = stage
    _save_state()
    st.rerun()





# ── Geocode checkpoint helpers ───────────────────────────────────────────────
import os, tempfile

def _checkpoint_path(filename: str) -> str:
    """Return a stable temp-file path for a given source filename."""
    safe = re.sub(r"[^\w]", "_", filename)
    return os.path.join(tempfile.gettempdir(), f"geocode_checkpoint_{safe}.pkl")

def _save_checkpoint(df: pd.DataFrame, filename: str):
    df.to_pickle(_checkpoint_path(filename))

def _load_checkpoint(filename: str):
    p = _checkpoint_path(filename)
    if os.path.exists(p):
        return pd.read_pickle(p)
    return None

def _clear_checkpoint(filename: str):
    p = _checkpoint_path(filename)
    if os.path.exists(p):
        os.remove(p)


# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════

def run_clean_in_memory(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Delegate to the single authoritative clean path in clean_pipeline."""
    df_clean, cstats = cp.clean_dataframe(df_raw)
    st.session_state["_clean_stats"] = cstats
    return df_clean


_JUNK_STREET_RE = re.compile(r"^[\d\s\.\,\-\_\!\?\(\)״׳'\"]+$")

from corrections import KNOWN_UNRESOLVABLE as _KNOWN_UNRESOLVABLE, DESCRIPTIVE_PREFIXES as _DESCRIPTIVE_PREFIXES



def auto_fix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Auto-resolve blocking flags before showing them to the human reviewer.
    Only touches rows that would block; leaves valid data untouched.

    Fixes:
      1. Ticket ID hygiene (whitespace, .0 suffix)
      2. Street name hygiene (trim whitespace + trailing punctuation)
      3. Known-unresolvable raw addresses → סוג_מיקום = "ציון דרך"
         so flags.py produces addr_desc (warn) not addr_empty (block)
      4. Blank/junk רחוב_ראשי where raw address matches a descriptive prefix
         → same treatment as #3
      5. Rows where רחוב_ראשי is blank but raw address looks like a real street
         → re-run parse_address to attempt recovery
    """
    _orig_sug = df["סוג_מיקום"].copy() if "סוג_מיקום" in df.columns else None
    _orig_street = df["רחוב_ראשי"].copy() if "רחוב_ראשי" in df.columns else None
    df = df.copy()
    if _orig_sug is not None:
        _orig_sug = _orig_sug.copy()
    if _orig_street is not None:
        _orig_street = _orig_street.copy()

    # 1. Ticket ID
    df["מס' פניה"] = (
        df["מס' פניה"].astype(str).str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
    )

    # 2. Street name hygiene — only trim, never blank a real value
    if "רחוב_ראשי" in df.columns:
        df["רחוב_ראשי"] = (
            df["רחוב_ראשי"].fillna("").astype(str)
            .str.strip().str.rstrip(".,;:")
        )
        df["רחוב_ראשי"] = df["רחוב_ראשי"].replace({"nan": "", "None": ""})

    if "כתובת ואתר/מוסד" not in df.columns or "סוג_מיקום" not in df.columns:
        return df

    raw = df["כתובת ואתר/מוסד"].fillna("").astype(str).str.strip()
    street = df["רחוב_ראשי"].fillna("").astype(str).str.strip()
    street_blank = street.isin(["", "nan", "None"])
    street_junk  = street.str.fullmatch(r"[\d\s\.\,\-\_\!\?\(\)״׳'\"]+") & ~street_blank

    # 3. Known-unresolvable exact matches
    is_known_bad = raw.isin(_KNOWN_UNRESOLVABLE)
    df.loc[is_known_bad, "סוג_מיקום"] = "ציון דרך"
    # Clear junk street text so addr_junk flag won't fire on top of addr_desc
    df.loc[is_known_bad & (street_blank | street_junk), "רחוב_ראשי"] = ""

    # 4. Blank/junk street + raw address starts with a descriptive prefix
    is_descriptive_prefix = raw.str.startswith(_DESCRIPTIVE_PREFIXES, na=False)
    needs_desc = is_descriptive_prefix & (street_blank | street_junk) & ~is_known_bad
    df.loc[needs_desc, "סוג_מיקום"] = "ציון דרך"
    df.loc[needs_desc, "רחוב_ראשי"] = ""

    # 4b. Parenthetical-only raw address: "(גינת כיבוש העבודה)" → strip parens, re-parse
    # Also handles "10(בית הראשונים)" where number comes before street name in parens
    import re as _re
    if "כתובת ואתר/מוסד" in df.columns:
        raw2 = df["כתובת ואתר/מוסד"].fillna("").astype(str)
        street2 = df["רחוב_ראשי"].fillna("").astype(str).str.strip()
        street_blank2 = street2.isin(["", "nan", "None"])
        street_junk2  = street2.str.fullmatch(r'[\d\s.,\-_!?()״׳\'"]+') & ~street_blank2

        for idx in df.index[street_blank2 | street_junk2]:
            raw_val = str(df.at[idx, "כתובת ואתר/מוסד"]).strip()
            # Pattern: digits then (street name) — e.g. "10(בית הראשונים)"
            m = _re.match(r"^\d+\(([^)]+)\)", raw_val)
            if m:
                candidate = m.group(1).strip()
                try:
                    loc = cp.parse_address(candidate)
                    if loc["רחוב_ראשי"]:
                        df.at[idx, "רחוב_ראשי"] = loc["רחוב_ראשי"]
                        df.at[idx, "סוג_מיקום"] = loc["סוג_מיקום"] or "ציון דרך"
                        continue
                except Exception:
                    pass
            # Pattern: entire address is (something) — e.g. "(גינת כיבוש העבודה)"
            m2 = _re.match(r"^\(([^)]+)\)$", raw_val)
            if m2:
                candidate = m2.group(1).strip()
                try:
                    loc = cp.parse_address(candidate)
                    if loc["רחוב_ראשי"]:
                        df.at[idx, "רחוב_ראשי"] = loc["רחוב_ראשי"]
                        df.at[idx, "סוג_מיקום"] = loc["סוג_מיקום"] or "ציון דרך"
                    else:
                        df.at[idx, "סוג_מיקום"] = "ציון דרך"
                except Exception:
                    df.at[idx, "סוג_מיקום"] = "ציון דרך"

    # 5. Blank street + raw address looks like it has real content → re-parse
    #    (catches cases where parse_address failed due to encoding or whitespace)
    maybe_real = street_blank & ~is_known_bad & ~needs_desc & (raw.str.len() > 2)
    for idx in df.index[maybe_real]:
        raw_val = df.at[idx, "כתובת ואתר/מוסד"]
        try:
            loc = cp.parse_address(raw_val)
            if loc["רחוב_ראשי"] and not _JUNK_STREET_RE.match(str(loc["רחוב_ראשי"])):
                df.at[idx, "רחוב_ראשי"] = loc["רחוב_ראשי"]
                df.at[idx, "מספר_בית"]  = loc["מספר_בית"] or df.at[idx, "מספר_בית"]
                df.at[idx, "סוג_מיקום"] = loc["סוג_מיקום"]
        except Exception:
            pass

    # Audit log — auto_fix changes
    try:
        ticket_col = df["מס' פניה"]
        if _orig_sug is not None:
            changed_sug = df["סוג_מיקום"] != _orig_sug
            for idx in df.index[changed_sug]:
                al.log_correction(
                    ticket_col.iloc[df.index.get_loc(idx)],
                    "סוג_מיקום", _orig_sug.iloc[df.index.get_loc(idx)],
                    df.at[idx, "סוג_מיקום"], "auto_fix"
                )
        if _orig_street is not None:
            changed_st = df["רחוב_ראשי"] != _orig_street
            for idx in df.index[changed_st]:
                al.log_correction(
                    ticket_col.iloc[df.index.get_loc(idx)],
                    "רחוב_ראשי", _orig_street.iloc[df.index.get_loc(idx)],
                    df.at[idx, "רחוב_ראשי"], "auto_fix"
                )
    except Exception:
        pass

    return df


def _flag_breakdown(flagged: pd.DataFrame, severity: str) -> pd.DataFrame:
    """Return a value-counts table of individual flag labels for a given severity."""
    subset = flagged[flagged["_flag_severity"] == severity]
    if subset.empty:
        return pd.DataFrame(columns=["סוג בעיה", "שורות"])
    counts = (
        subset["_flag_labels"]
        .str.split(";")
        .explode()
        .str.strip()
        .loc[lambda s: s != ""]
        .value_counts()
        .reset_index()
    )
    counts.columns = ["סוג בעיה", "שורות"]
    return counts


COORD_COLS = ["קו_רוחב", "קו_אורך"]


def _coerce_coords(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee coordinate columns are float64 (strips stray commas, coerces non-numeric)."""
    df = df.copy()
    for col in COORD_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            ).astype("float64")
    return df


def excel_bytes(df: pd.DataFrame, stats: dict) -> bytes:
    """Single Excel output: color-flagged data sheet + Hebrew summary sheet."""
    df = _coerce_coords(df.copy())
    # Re-detect flags for coloring (drop internal cols from the visible sheet)
    flagged = fl.detect_flags(df, DATE_MIN, DATE_MAX, stage="all")
    severity = flagged["_flag_severity"].tolist()
    flag_labels = flagged["_flag_labels"].tolist()
    export = df.copy()
    export["דגל_בדיקה"] = flag_labels
    internal = [c for c in export.columns if c.startswith("_")]
    export = export.drop(columns=internal, errors="ignore")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        # Summary sheet
        summary_rows = [
            ("סה\u05f4כ שורות", stats.get("rows", len(df))),
            ("גאוקודד", stats.get("geo_ok", "")),
            ("אחוז כיסוי גאוקוד", stats.get("geo_pct", "")),
            ("בתוך תחום העיר", stats.get("in_city", "")),
            ("תלונות חוזרות", stats.get("recurring", "")),
            ("שיעור תלונות חוזרות", stats.get("recurring_pct", "")),
            ("תלונות ביום פינוי", stats.get("same_day", "")),
            ("שיעור תלונות ביום פינוי", stats.get("same_day_pct", "")),
            ("שורות עם דגל אזהרה", stats.get("warn_rows", "")),
        ]
        pd.DataFrame(summary_rows, columns=["מדד", "ערך"]).to_excel(
            writer, index=False, sheet_name="סיכום")
        ws_s = writer.sheets["סיכום"]
        fmt_hdr = wb.add_format({"bold": True, "bg_color": "#1a3a5c",
                                 "font_color": "white", "align": "right"})
        ws_s.set_column("A:A", 34); ws_s.set_column("B:B", 18)
        ws_s.write(0, 0, "מדד", fmt_hdr); ws_s.write(0, 1, "ערך", fmt_hdr)

        # Data sheet with row coloring
        export.to_excel(writer, index=False, sheet_name="נתונים")
        ws_d = writer.sheets["נתונים"]
        fmt_block = wb.add_format({"bg_color": "#fee2e2"})
        fmt_warn  = wb.add_format({"bg_color": "#fef3c7"})
        ncols = len(export.columns)
        for i, sev in enumerate(severity):
            if sev == "block":
                ws_d.set_row(i + 1, None, fmt_block)
            elif sev == "warn":
                ws_d.set_row(i + 1, None, fmt_warn)
        for j, col in enumerate(export.columns):
            ws_d.write(0, j, col, fmt_hdr)

        # Audit log sheet
        try:
            audit_df = al.log_to_dataframe()
        except Exception:
            import pandas as _pd
            audit_df = _pd.DataFrame(columns=["ticket", "field", "old", "new", "source", "timestamp", "run_id"])
        audit_df.to_excel(writer, index=False, sheet_name="יומן_תיקונים")
        ws_a = writer.sheets["יומן_תיקונים"]
        for j, col in enumerate(audit_df.columns):
            ws_a.write(0, j, col, fmt_hdr)
    return buf.getvalue()


def _tip(html_content: str) -> str:
    """Render a hover-tooltip '?' icon. html_content is the inner HTML of the bubble."""
    return (
        f'<span class="tip-wrap">'
        f'<span class="tip-icon">❓</span>'
        f'<div class="tip-box">{html_content}</div>'
        f'</span>'
    )


def _find_street_variants(df: pd.DataFrame) -> list:
    """
    Find street names in the data that have variant spellings or differ from the
    canonical form in the municipal street registry (imported from geocode_pipeline).

    Returns list of:
      {"canonical": str, "total": int, "variants": [{"raw": str, "count": int}],
       "registry_match": str|None}
    sorted by total occurrences descending, capped at 15 groups.
    """
    try:
        import re as _re
        from collections import defaultdict as _dd
        import geocode_pipeline as _gp

        _prefix = _re.compile(r"^(רחוב|רח[׳']|ר[׳']|ה?רחוב)\s+", _re.UNICODE)
        _suffix = _re.compile(r"\s*([,\.;]|\d{1,5}|ת\.א|ת\.ל)\s*$", _re.UNICODE)

        def _norm(s: str) -> str:
            s = str(s).strip()
            s = _prefix.sub("", s)
            s = _suffix.sub("", s)
            return s.strip()

        streets = df["רחוב_ראשי"].dropna().astype(str) if "רחוב_ראשי" in df.columns else pd.Series(dtype=str)
        streets = streets[streets.str.strip() != ""]

        raw_counts: dict = {}
        for raw in streets:
            raw_counts[raw] = raw_counts.get(raw, 0) + 1

        # Group raw → normalized
        norm_groups: dict = _dd(lambda: _dd(int))
        for raw, cnt in raw_counts.items():
            norm_groups[_norm(raw)][raw] += cnt

        results = []
        for norm_key, raw_cnt_map in norm_groups.items():
            total = sum(raw_cnt_map.values())
            if total < 5:
                continue
            # Only show groups with >1 distinct spelling OR whose canonical differs from raw
            all_raws = sorted(raw_cnt_map, key=lambda k: -raw_cnt_map[k])
            canonical = all_raws[0]  # most common raw form
            variants = [{"raw": r, "count": raw_cnt_map[r]} for r in all_raws[1:] if raw_cnt_map[r] >= 2]

            # Check registry
            reg_canon, _ = _gp._registry_resolve(norm_key)
            if reg_canon is None and len(all_raws) > 1:
                reg_canon, _ = _gp._registry_resolve(canonical)

            if variants or (reg_canon and reg_canon != canonical):
                results.append({
                    "canonical": canonical,
                    "normalized": norm_key,
                    "total": total,
                    "variants": variants,
                    "registry_match": reg_canon,
                })

        return sorted(results, key=lambda x: -x["total"])[:15]
    except Exception:
        return []


def _center_style(df: pd.DataFrame):
    """Return a pandas Styler with centered, RTL cells — works in both HTML and canvas modes."""
    return (df.style
              .set_properties(**{"text-align": "center", "direction": "rtl"})
              .set_table_styles([{"selector": "th", "props": [("text-align", "center"), ("direction", "rtl")]}]))


def _render_flagged_table(df: pd.DataFrame, max_rows: int = 500):
    """
    Render a flagged-rows table with explicit column widths so the browser
    shows a horizontal scrollbar instead of squishing all columns.
    Strips internal _cols; shows only the most diagnostic fields.
    """
    COLS = {
        "מס' פניה":     st.column_config.TextColumn("מס' פניה",    width=90),
        "תאריך":        st.column_config.TextColumn("תאריך",        width=100),
        "כתובת ואתר/מוסד": st.column_config.TextColumn("כתובת מקורית", width=200),
        "רחוב_ראשי":   st.column_config.TextColumn("רחוב",         width=140),
        "מספר_בית":    st.column_config.TextColumn("מס' בית",      width=80),
        "סוג_מיקום":   st.column_config.TextColumn("סוג מיקום",    width=100),
        "geocode_method": st.column_config.TextColumn("שיטת גאוקוד", width=120),
        "_flag_labels": st.column_config.TextColumn("בעיות",        width=300),
    }
    present = [c for c in COLS if c in df.columns]
    display = df[present].head(max_rows).copy()
    col_cfg = {c: COLS[c] for c in present}
    h = min(480, max(80, len(display) * 35 + 42))
    st.dataframe(_center_style(display), column_config=col_cfg, hide_index=True, height=h)
    if len(df) > max_rows:
        st.caption(f"מוצגות {max_rows} שורות ראשונות מתוך {len(df):,}")


def _leaflet_map_html(df: pd.DataFrame, height: int = 400) -> str:
    """
    Build a self-contained Leaflet HTML fragment showing geocoded rows as pins.
    Pins are coloured by _flag_severity: red=block, orange=warn, blue=clean.
    Returns raw HTML string for use with st.components.v1.html().
    """
    import json
    color_map = {"block": "red", "warn": "orange", "review": "orange", "info": "blue", "": "green"}
    points = []
    for _, row in df.iterrows():
        try:
            lat = float(str(row.get("קו_רוחב", "")).replace(",", ""))
            lon = float(str(row.get("קו_אורך", "")).replace(",", ""))
            if not (32.0 <= lat <= 33.0 and 34.0 <= lon <= 36.0):
                continue
            sev = str(row.get("_flag_severity", ""))
            label = str(row.get("_flag_labels", "")) or "תקין"
            ticket = str(row.get("מס' פניה", ""))
            street = str(row.get("רחוב_ראשי", "")) + " " + str(row.get("מספר_בית", ""))
            points.append({"lat": lat, "lon": lon, "color": color_map.get(sev, "blue"),
                           "popup": f"<b>{ticket}</b><br>{street}<br>{label}"})
        except (ValueError, TypeError):
            continue

    points_json = json.dumps(points, ensure_ascii=False)
    center_lat = 32.166 if not points else sum(p["lat"] for p in points) / len(points)
    center_lon = 34.843 if not points else sum(p["lon"] for p in points) / len(points)

    return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{{margin:0;padding:0;height:{height}px;}}</style>
</head><body>
<div id="map"></div>
<script>
var map = L.map('map').setView([{center_lat},{center_lon}], 14);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{attribution:'© OpenStreetMap contributors',maxZoom:19}}).addTo(map);
var pts = {points_json};
pts.forEach(function(p){{
  L.circleMarker([p.lat,p.lon],{{radius:7,color:p.color,fillColor:p.color,fillOpacity:0.8}})
   .bindPopup(p.popup).addTo(map);
}});
</script></body></html>"""


def stepper_html(current: str) -> str:
    order = [s[0] for s in STAGES]
    ci = order.index(current)
    cells = []
    for i, (key, label) in enumerate(STAGES):
        cls = "active" if key == current else ("done" if i < ci else "")
        mark = "✓" if i < ci else str(i + 1)
        cells.append(f'<div class="step {cls}"><span class="num">{mark}</span>{label}</div>')
    return '<div class="stepper">' + "".join(cells) + "</div>"


# ══════════════════════════════════════════════════════════════════════════
#  HEADER + STEPPER
# ══════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="main-header">
  <h1>🗑️ מערכת עיבוד פניות תברואה</h1>
  <p>עיריית הרצליה — צינור מלא: ניקוי · גאוקוד · העשרה · ניתוח</p>
</div>
""", unsafe_allow_html=True)

if not MODULES_OK:
    st.markdown(f'<div class="banner-error">❌ שגיאה בטעינת מודולים: {_IMPORT_ERR}</div>',
                unsafe_allow_html=True)
    st.stop()

# Show recovery banner if we restored from disk
if (st.session_state.get("df") is not None
        and st.session_state.get("stage", "upload") != "upload"
        and st.session_state.get("_just_restored")):
    stage_labels = {"clean":"ניקוי","geocode":"גאוקוד","enrich":"העשרה","output":"פלט"}
    label = stage_labels.get(st.session_state.stage, st.session_state.stage)
    n = len(st.session_state.df)
    st.markdown(
        f'<div class="banner-warn">🔄 חיבור שוחזר — {n:,} שורות נטענו בחזרה. ממשיך משלב: <strong>{label}</strong></div>',
        unsafe_allow_html=True)
    st.session_state["_just_restored"] = False

st.markdown(stepper_html(st.session_state.stage), unsafe_allow_html=True)
stage = st.session_state.stage


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 1 — UPLOAD
# ══════════════════════════════════════════════════════════════════════════

if stage == "upload":
    st.markdown("### שלב 1 — העלאת קובץ ייצוא CRM 360")
    st.markdown("העלו קובץ Excel שיוצא ממערכת CRM 360. הקובץ צריך להכיל את העמודות הסטנדרטיות.")
    uploaded = st.file_uploader("בחרו קובץ .xlsx", type=["xlsx"], label_visibility="collapsed")

    if uploaded:
        try:
            df_raw = pd.read_excel(uploaded)
            found   = [c for c in REQUIRED_COLS if c in df_raw.columns]
            missing = [c for c in REQUIRED_COLS if c not in df_raw.columns]

            c1, c2 = st.columns(2)
            with c1: st.metric("סה\u05f4כ שורות", f"{len(df_raw):,}")
            with c2: st.metric("עמודות נדרשות", f"{len(found)}/{len(REQUIRED_COLS)}")

            if missing:
                for col in missing:
                    st.markdown(f'<div class="banner-error">❌ עמודה חסרה: <strong>{col}</strong> '
                                f'({REQUIRED_COLS[col]})</div>', unsafe_allow_html=True)
                st.markdown('<div class="banner-error">לא ניתן להמשיך — חסרות עמודות נדרשות.</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown('<div class="banner-success">✅ כל העמודות הנדרשות נמצאו</div>',
                            unsafe_allow_html=True)
                _preview_cols = [c for c in [
                    "מס' פניה", "תאריך ושעת פתיחה", "כתובת ואתר/מוסד",
                    "תת נושא", "סטטוס פנייה", "שם מגיש",
                ] if c in df_raw.columns] or list(df_raw.columns[:6])
                st.dataframe(
                    df_raw[_preview_cols].head(5),
                    hide_index=True,
                    column_config={c: st.column_config.TextColumn(c, width=160)
                                   for c in _preview_cols},
                )
                if st.button("▶ התחל עיבוד — נקה נתונים", type="primary", use_container_width=True):
                    with st.spinner("מנקה ומעבד..."):
                        df_clean = run_clean_in_memory(df_raw)
                        df_clean = auto_fix(df_clean)
                        st.session_state.df = df_clean
                        st.session_state.filename = uploaded.name
                        st.session_state.geocoded = False
                        st.session_state.enriched = False
                        _save_state()
                    goto("clean")
        except Exception as e:
            st.markdown(f'<div class="banner-error">❌ שגיאה בקריאת הקובץ: {e}</div>',
                        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 2 — CLEAN  (confidence-tiered review + explainability)
# ══════════════════════════════════════════════════════════════════════════

elif stage == "clean":
    df = st.session_state.df
    flagged = fl.detect_flags(df, DATE_MIN, DATE_MAX, stage="clean")
    n_block = fl.count_blocking(flagged)
    n_warn  = fl.count_warnings(flagged)

    # ── Confidence tier counts ──────────────────────────────────────────────
    _cs = st.session_state.get("_clean_stats", {})
    n_high   = _cs.get("conf_high",   int((df.get("_confidence", pd.Series()) == "high").sum())   if "_confidence" in df.columns else 0)
    n_medium = _cs.get("conf_medium", int((df.get("_confidence", pd.Series()) == "medium").sum()) if "_confidence" in df.columns else 0)
    n_low    = _cs.get("conf_low",    int((df.get("_confidence", pd.Series()) == "low").sum())    if "_confidence" in df.columns else 0)

    st.markdown("### שלב 2 — ניקוי: סקירת אמון ועדכון ידני")

    # ── Summary cards ────────────────────────────────────────────────────────
    _pct_auto = round(n_high / len(df) * 100) if len(df) else 0
    st.markdown(f"""
    <style>
    .conf-row {{display:flex;gap:.9rem;margin-bottom:1.3rem;flex-direction:row-reverse;}}
    .conf-card {{flex:1;border-radius:10px;padding:.9rem 1rem;text-align:center;
                 box-shadow:0 1px 4px rgba(0,0,0,.07);}}
    .conf-card .cn {{font-size:1.8rem;font-weight:700;line-height:1.1;}}
    .conf-card .cl {{font-size:.82rem;font-weight:600;margin-top:.3rem;}}
    .conf-card .cs {{font-size:.7rem;margin-top:.2rem;opacity:.75;}}
    .cc-green  {{background:#d1fae5;border:1px solid #6ee7b7;}}
    .cc-green .cn  {{color:#065f46;}}
    .cc-blue   {{background:#dbeafe;border:1px solid #93c5fd;}}
    .cc-blue .cn   {{color:#1e3a8a;}}
    .cc-orange {{background:#ffedd5;border:1px solid #fdba74;}}
    .cc-orange .cn {{color:#9a3412;}}
    .cc-gray   {{background:#f1f5f9;border:1px solid #cbd5e1;}}
    .cc-gray .cn   {{color:#334155;}}
    </style>
    <div class="conf-row">
      <div class="conf-card cc-green">
        <div class="cn">{n_high:,}</div>
        <div class="cl">✅ סווגו אוטומטית</div>
        <div class="cs">לא נדרשת פעולה</div>
      </div>
      <div class="conf-card cc-blue">
        <div class="cn">{n_medium:,}</div>
        <div class="cl">🔵 סווגו בחלקיות</div>
        <div class="cs">המערכת עשתה את ההערכה הטובה ביותר</div>
      </div>
      <div class="conf-card cc-orange">
        <div class="cn">{n_low:,}</div>
        <div class="cl">⚠️ לא ניתן לסווג</div>
        <div class="cs">דורשות קלט ממך או תיקון ב-Excel</div>
      </div>
      <div class="conf-card cc-gray">
        <div class="cn">{n_block:,}</div>
        <div class="cl">⛔ שגיאות מבניות</div>
        <div class="cs">נתון חסר/שגוי · חוסם המשך</div>
      </div>
    </div>
    <div style="text-align:right;color:#475569;font-size:.84rem;margin-bottom:1rem;">
      ✅ <strong>{_pct_auto}%</strong> מהשורות ({n_high:,}) סווגו באופן ודאי ואינן דורשות בדיקה.
      {f"⚠️ <strong>{n_low:,}</strong> שורות דורשות קלט ממך." if n_low > 0 else ""}
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    #  CLUSTER Q&A — resolve uncertain rows before export
    # ════════════════════════════════════════════════════════
    _clusters  = cp.find_clusters(df)
    _st_vars   = _find_street_variants(df)
    _has_questions = bool(_clusters["unknown_subtopics"] or _clusters["unresolved_resp"] or _st_vars)

    # Tooltip HTML for common reference points
    _TIP_RESP = _tip(
        "<strong>כשל עירוני</strong> — העירייה לא ביצעה את עבודתה: "
        "פינוי לא תקין, ניקוי שלא נעשה, ציוד שהתקלקל, עובדי ניקוי שלא הגיעו<br><br>"
        "<strong>התנהגות אזרח</strong> — אזרח גרם לבעיה: "
        "זרק אשפה, פיזר פסולת, גנב ציוד, גרם נזק<br><br>"
        "<strong>טבעי</strong> — הטבע הוא הגורם: "
        "גשם, רוח, עלים נשרו, ציפורים, בעלי חיים<br><br>"
        "<strong>לא רלוונטי</strong> — האחריות לא שייכת לביצועים: "
        "בקשות שירות, תביעות נזק"
    )
    _TIP_CAT = _tip(
        "<strong>אי פינוי</strong> — אשפה לא פונתה במועד הקבוע<br>"
        "<strong>תלונה על ביצוע הפינוי</strong> — הפינוי בוצע אך בצורה לא תקינה<br>"
        "<strong>משטח מלוכלך</strong> — רחוב, מדרכה, מגרש מלוכלכים<br>"
        "<strong>פסולת לא מורשית</strong> — ערמת זבל שהושלכה לא כחוק<br>"
        "<strong>כלי אצירה פגומים</strong> — פח/מכולה שבורים<br>"
        "<strong>כלי אצירה מלא</strong> — פח/מכולה מלאים מדי<br>"
        "<strong>פח נעלם</strong> — פח שנעלם לאחר פינוי<br>"
        "<strong>צואת כלבים</strong> — בעיה ספציפית של צואת כלבים<br>"
        "<strong>פגר</strong> — פגר בעל חיים ברחוב<br>"
        "<strong>פלישת צומח</strong> — עשבים שצמחו על מדרכה"
    )
    _TIP_STREET = _tip(
        "שם הרחוב הקנוני הוא השם הרשמי שמופיע ב-GIS העירוני של הרצליה.<br><br>"
        "כשיש כתיבות שונות לאותו רחוב, הגאוקוד עלול להיכשל על חלקן.<br><br>"
        "האחדה לשם אחד משפרת את הדיוק של מציאת הקואורדינטות."
    )

    if _has_questions:
        st.markdown("---")
        _total_q_rows = (
            sum(c["count"] for c in _clusters["unknown_subtopics"]) +
            sum(c["count"] for c in _clusters["unresolved_resp"]) +
            sum(v["total"] for v in _st_vars)
        )
        st.markdown(
            f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;'
            f'padding:.8rem 1.1rem;font-size:.9rem;direction:rtl;margin-bottom:1rem;">'
            f'🙋 <strong>נדרש קלט ממך</strong> — מצאנו {_total_q_rows:,} פניות שלא ניתן '
            f'לסווג בלי המידע שלך. ענה על השאלות הבאות כדי שהמערכת תסווג אותן אוטומטית. '
            f'לכל שאלה יש כפתור ❓ עם הסבר — רחף מעליו לפני שאתה עונה.'
            f'</div>',
            unsafe_allow_html=True,
        )

        _qa_answers: dict = {}

        # ── Type 1: Unknown sub-topics ────────────────────────────────────
        if _clusters["unknown_subtopics"]:
            st.markdown(
                f'**📋 תת-נושאים שלא מוכרים למערכת** {_TIP_CAT}',
                unsafe_allow_html=True,
            )
            for _cl in _clusters["unknown_subtopics"]:
                _sub = _cl["value"]
                _cnt = _cl["count"]
                _ex  = " • ".join(_cl.get("examples", [])[:2])
                st.markdown(
                    f'<div style="background:#fff7ed;border-right:3px solid #fb923c;'
                    f'padding:.55rem .9rem;border-radius:6px;direction:rtl;margin:.5rem 0 .2rem;">'
                    f'<strong>"{_sub}"</strong> — {_cnt:,} פניות'
                    f'{f"<br><small style=color:#78716c;font-size:.8rem>{_ex}</small>" if _ex else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                _opts = ["השאר לבדיקה ב-Excel"] + cp.KNOWN_CATEGORIES_LIST
                _ans = st.selectbox(
                    f'לאיזו קטגוריה שייכות פניות "{_sub}"?',
                    _opts, key=f"qa_sub_{_sub}",
                    help="בחר את הקטגוריה המתאימה. רחף מעל ❓ למעלה לראות הגדרות הקטגוריות.",
                )
                if _ans != "השאר לבדיקה ב-Excel":
                    _qa_answers[f"subtopic:{_sub}"] = _ans

        # ── Type 2: Unresolved responsibility (with description samples) ──
        if _clusters["unresolved_resp"]:
            st.markdown(
                f'**📋 קטגוריות שלא ברור מי אחראי לטיפול** {_TIP_RESP}',
                unsafe_allow_html=True,
            )
            for _cl in _clusters["unresolved_resp"]:
                _cat  = _cl["category"]
                _cnt  = _cl["count"]
                _smpl = _cl.get("desc_samples", [])
                _samples_html = ""
                if _smpl:
                    _samples_html = (
                        '<br><small style="color:#78716c;font-size:.79rem;">'
                        '<em>דוגמאות מהתיאורים (כדי שתוכל לשפוט):</em><br>'
                        + "<br>".join(f"• {s}" for s in _smpl)
                        + "</small>"
                    )
                st.markdown(
                    f'<div style="background:#fff7ed;border-right:3px solid #fb923c;'
                    f'padding:.55rem .9rem;border-radius:6px;direction:rtl;margin:.5rem 0 .2rem;">'
                    f'<strong>"{_cat}"</strong> — {_cnt:,} פניות ללא סיווג אחריות'
                    f'{_samples_html}'
                    f'<br><small style="color:#9a3412;font-size:.78rem;">⚠️ שים לב: הפניות בקטגוריה זו עשויות להיות מסיבות שונות. '
                    f'אם לא ניתן לתת תשובה אחת לכולן — השאר כ-"לא ידוע".</small>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                _resp_opts = ["השאר כ-לא ידוע"] + cp.KNOWN_RESPONSIBILITIES
                _ans = st.selectbox(
                    f'מי אחראי לטיפול ב"{_cat}"?',
                    _resp_opts, key=f"qa_resp_{_cat}",
                    help=(
                        "כשל עירוני — העירייה לא ביצעה את עבודתה\n"
                        "התנהגות אזרח — אזרח גרם לבעיה\n"
                        "טבעי — גשם, רוח, ציפורים, בעלי חיים\n"
                        "לא רלוונטי — בקשות שירות, תביעות\n\n"
                        "⚠️ אם הפניות מגוונות ואין תשובה אחת — השאר כ-'לא ידוע'"
                    ),
                )
                if _ans != "השאר כ-לא ידוע":
                    _qa_answers[f"resp:{_cat}"] = _ans

        # ── Type 3: Street name variants ──────────────────────────────────
        if _st_vars:
            st.markdown(
                f'**🗺️ שמות רחובות בכתיבות שונות** {_TIP_STREET}',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;'
                f'padding:.5rem .8rem;font-size:.82rem;direction:rtl;margin-bottom:.6rem;">'
                f'💡 האחדת שמות רחובות לכתיב הרשמי משפרת את דיוק הגאוקוד (מציאת הקואורדינטות). '
                f'<a href="https://v5.gis-net.co.il/v5/Hertzeliya?minisite=public" target="_blank">'
                f'לבדיקת השם הנכון ב-GIS העירוני →</a></div>',
                unsafe_allow_html=True,
            )
            for _sv in _st_vars:
                _can  = _sv["canonical"]
                _tot  = _sv["total"]
                _reg  = _sv.get("registry_match")
                _vars = _sv["variants"]
                _suggested = _reg if _reg else _can
                _vars_text = ", ".join(f'"{v["raw"]}" ({v["count"]}×)' for v in _vars[:4])
                _reg_note = (
                    f'<br><small style="color:#065f46;">✅ שם קנוני ב-GIS: <strong>{_reg}</strong> — '
                    f'מומלץ להשתמש בו, אך אמת קודם</small>'
                ) if _reg and _reg != _can else ""
                st.markdown(
                    f'<div style="background:#f0fdf4;border-right:3px solid #4ade80;'
                    f'padding:.55rem .9rem;border-radius:6px;direction:rtl;margin:.5rem 0 .2rem;">'
                    f'<strong>"{_can}"</strong> — {_tot:,} פניות סה"כ'
                    f'{f"<br><small style=color:#475569;font-size:.79rem>כתיבות נוספות שנמצאו: {_vars_text}</small>" if _vars_text else ""}'
                    f'{_reg_note}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                # Build variant options: each raw form that appears
                _all_raws_for_street = [_can] + [v["raw"] for v in _vars]
                _street_opts = ["השאר כמו שיש"] + (
                    [_reg] if _reg and _reg not in _all_raws_for_street else []
                ) + _all_raws_for_street
                _ans = st.selectbox(
                    f'מה הכתיב הנכון של "{_can}"?',
                    _street_opts, key=f"qa_street_{_can}",
                    index=1 if _reg and _reg not in _all_raws_for_street else 0,
                    help=(
                        "בחר את הכתיב הרשמי לאחר בדיקה ב-GIS העירוני.\n"
                        "כל הפניות עם כתיב שונה יועברו לכתיב שתבחר.\n"
                        "אל תשנה אם אינך בטוח — 'השאר כמו שיש' הוא תמיד בטוח."
                    ),
                )
                if _ans != "השאר כמו שיש" and _ans != _can:
                    # Apply to all variant raw forms in this group
                    for _raw_v in _all_raws_for_street:
                        if _raw_v != _ans:
                            _qa_answers[f"street:{_raw_v}"] = _ans

        st.markdown("")
        if st.button("✅ החל תשובות — סווג את הקבוצות האלה", type="primary", use_container_width=True):
            if _qa_answers:
                with st.spinner("מסווג ומעדכן..."):
                    _updated_df = cp.apply_user_answers(df, _qa_answers)
                    st.session_state.df = _updated_df
                    _ccs = st.session_state.get("_clean_stats", {}).copy()
                    _ccs["conf_high"]   = int((_updated_df["_confidence"] == "high").sum()   if "_confidence" in _updated_df.columns else 0)
                    _ccs["conf_medium"] = int((_updated_df["_confidence"] == "medium").sum() if "_confidence" in _updated_df.columns else 0)
                    _ccs["conf_low"]    = int((_updated_df["_confidence"] == "low").sum()    if "_confidence" in _updated_df.columns else 0)
                    st.session_state["_clean_stats"] = _ccs
                    al.log_correction("batch", "_cluster_qa", "pending", str(list(_qa_answers.keys())), "user_qa")
                st.rerun()
            else:
                st.info("לא נבחרה תשובה — בחר קטגוריה לפחות לאחת השאלות.")

    # ── Auto-processed preview ─────────────────────────────────────────────
    with st.expander(f"✅ סווגו אוטומטית — {n_high:,} שורות ({_pct_auto}%)", expanded=False):
        st.markdown(
            '<div style="color:#065f46;background:#d1fae5;border-radius:8px;'
            'padding:.7rem 1rem;font-size:.88rem;direction:rtl;margin-bottom:.8rem;">'
            '🔒 שורות אלו סווגו בצורה ודאית — הקטגוריה, האחריות, והכתובת כולן ברורות. '
            'אין צורך בשום פעולה.</div>',
            unsafe_allow_html=True,
        )
        if "_confidence" in df.columns:
            _high_df = df[df["_confidence"] == "high"]
            if not _high_df.empty:
                _h_sample = _high_df[
                    [c for c in ["מס' פניה", "תת_נושא_חדש", "אחריות", "רחוב_ראשי", "מספר_בית"]
                     if c in _high_df.columns]
                ].head(5)
                st.caption(f"דוגמה — 5 שורות מתוך {n_high:,}:")
                st.dataframe(_center_style(_h_sample), hide_index=True,
                             column_config={c: st.column_config.TextColumn(c, width=160)
                                            for c in _h_sample.columns})

    # ── Partially-classified rows ──────────────────────────────────────────
    if n_medium > 0:
        with st.expander(f"🔵 סווגו בחלקיות — {n_medium:,} שורות", expanded=False):
            st.markdown(
                '<div style="color:#1e3a8a;background:#dbeafe;border-radius:8px;'
                'padding:.7rem 1rem;font-size:.88rem;direction:rtl;margin-bottom:.8rem;">'
                '📋 שורות אלו עובדו על ידי המערכת בצורה הטובה ביותר שיכלה — '
                'לא הייתה לה גישה לכל המידע, אבל הסיווג הגיוני. '
                'לא נדרשת פעולה, אלא אם כן אתה רואה שגיאה ברורה.</div>',
                unsafe_allow_html=True,
            )
            if "_confidence" in df.columns:
                _med_df = df[df["_confidence"] == "medium"]
                _m_cols = [c for c in ["מס' פניה", "תת_נושא_חדש", "אחריות", "רחוב_ראשי"]
                           if c in _med_df.columns]
                st.caption(f"דוגמה — 5 שורות מתוך {n_medium:,}:")
                st.dataframe(_center_style(_med_df[_m_cols].head(5)), hide_index=True,
                             column_config={c: st.column_config.TextColumn(c, width=160) for c in _m_cols})

    # ── Cannot-classify rows ───────────────────────────────────────────────
    if n_low > 0:
        with st.expander(f"⚠️ לא ניתן לסווג אוטומטית — {n_low:,} שורות", expanded=(not _has_questions)):
            st.markdown(
                '<div style="color:#9a3412;background:#ffedd5;border-radius:8px;'
                'padding:.7rem 1rem;font-size:.88rem;direction:rtl;margin-bottom:.8rem;">'
                '📥 שורות אלו יופיעו בגיליון <strong>"לסקירה ידנית"</strong> בקובץ ה-Excel. '
                'תקנו אותן ישירות בקובץ, ולאחר מכן העלו אותו חזרה לכאן לבדיקה חוזרת.</div>',
                unsafe_allow_html=True,
            )
            if "_confidence" in df.columns:
                _low_df = df[df["_confidence"] == "low"]
                _l_cols = [c for c in ["מס' פניה", "תת נושא מקורי", "כתובת ואתר/מוסד",
                                       "תת_נושא_חדש", "אחריות"] if c in _low_df.columns]
                st.caption(f"10 שורות ראשונות מתוך {n_low:,}:")
                st.dataframe(_center_style(_low_df[_l_cols].head(10)), hide_index=True,
                             column_config={c: st.column_config.TextColumn(c, width=140) for c in _l_cols})
    else:
        st.markdown('<div class="banner-success">✅ כל הפניות סווגו — לא נותרו שורות לבדיקה ידנית!</div>',
                    unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    #  TIER D — Structural integrity flags (existing logic)
    # ════════════════════════════════════════════════════════
    _triage = fl.build_triage_groups(flagged)
    _tsumm  = fl.triage_summary(_triage)

    if _tsumm["blocking"] > 0 or _tsumm["review"] > 0:
        st.markdown("---")
        st.markdown("#### ⛔ בעיות מבניות בנתונים")

        col_bd1, col_bd2 = st.columns(2)
        with col_bd1:
            if n_block > 0:
                st.markdown("**🔴 פירוט בעיות חוסמות:**")
                _bd_block = _flag_breakdown(flagged, "block")
                st.dataframe(_center_style(_bd_block), hide_index=True,
                             column_config={"סוג בעיה": st.column_config.TextColumn("סוג בעיה", width=220),
                                            "שורות":    st.column_config.NumberColumn("שורות",   width=80)})
        with col_bd2:
            if n_warn > 0:
                st.markdown("**🟡 פירוט אזהרות:**")
                _bd_warn = _flag_breakdown(flagged, "warn")
                st.dataframe(_center_style(_bd_warn), hide_index=True,
                             column_config={"סוג בעיה": st.column_config.TextColumn("סוג בעיה", width=220),
                                            "שורות":    st.column_config.NumberColumn("שורות",   width=80)})

        if _tsumm["blocking"] > 0:
            with st.expander(f"🔴 חוסמות ({_tsumm['blocking']:,})", expanded=True):
                _render_flagged_table(_triage["blocking"])
        if _tsumm["review"] > 0:
            with st.expander(f"🟡 לסקירה ({_tsumm['review']:,})", expanded=False):
                _render_flagged_table(_triage["review"])

    # ── Download review Excel ───────────────────────────────────────────────
    st.markdown("---")

    def _review_excel(df: pd.DataFrame, flagged: pd.DataFrame) -> bytes:
        export = df.copy()
        severity    = flagged["_flag_severity"].tolist()
        flag_labels = flagged["_flag_labels"].tolist()
        conf_col    = export.get("_confidence", pd.Series([""] * len(export))).tolist() \
                      if "_confidence" in export.columns else [""] * len(export)
        det_col     = export.get("_confidence_details", pd.Series([""] * len(export))).tolist() \
                      if "_confidence_details" in export.columns else [""] * len(export)

        # Insert review columns up front
        export.insert(0, "פירוט_החלטה",    det_col)
        export.insert(0, "רמת_ביטחון",     conf_col)
        export.insert(0, "אזהרה_בלבד",     [s == "warn"  for s in severity])
        export.insert(0, "דורש_תיקון",     [s == "block" for s in severity])
        export.insert(0, "תיאור_בעיה",     flag_labels)
        export = export.drop(columns=[c for c in export.columns if c.startswith("_")],
                             errors="ignore")

        _conf_bg = {"high": "#dcfce7", "medium": "#fef9c3", "low": "#fee2e2", "": "#ffffff"}
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            wb = writer.book
            fmt_hdr    = wb.add_format({"bold": True, "bg_color": "#1a3a5c",
                                        "font_color": "white", "align": "right", "border": 1})
            fmt_block  = wb.add_format({"bg_color": "#fecaca", "border": 1})
            fmt_warn   = wb.add_format({"bg_color": "#fef08a", "border": 1})
            fmt_ok     = wb.add_format({"bg_color": "#ffffff", "border": 1})
            fmt_hi     = wb.add_format({"bg_color": "#dcfce7", "border": 1})
            fmt_med    = wb.add_format({"bg_color": "#fef9c3", "border": 1})
            fmt_lo     = wb.add_format({"bg_color": "#fecaca", "bold": True, "border": 1})

            # Sheet 1 — full dataset, row colored by flag severity
            export.to_excel(writer, index=False, sheet_name="כל הנתונים")
            ws = writer.sheets["כל הנתונים"]
            for j, col in enumerate(export.columns):
                ws.write(0, j, col, fmt_hdr)
            for i, sev in enumerate(severity):
                row_fmt = fmt_block if sev == "block" else (fmt_warn if sev == "warn" else fmt_ok)
                ws.set_row(i + 1, None, row_fmt)
            ws.set_column(0, 0, 40); ws.set_column(1, 4, 14); ws.set_column(5, len(export.columns), 18)
            ws.freeze_panes(1, 0)

            # Sheet 2 — low-confidence rows only (manual review list)
            _low_mask = [c == "low" for c in conf_col]
            _low_export = export[[m for m in _low_mask]]
            if any(_low_mask):
                _low_rows = export.iloc[[i for i, m in enumerate(_low_mask) if m]]
                _low_rows.to_excel(writer, index=False, sheet_name="לסקירה ידנית")
                ws2 = writer.sheets["לסקירה ידנית"]
                for j, col in enumerate(_low_rows.columns):
                    ws2.write(0, j, col, fmt_hdr)
                for i in range(len(_low_rows)):
                    ws2.set_row(i + 1, None, fmt_lo)
                ws2.set_column(0, 0, 40); ws2.set_column(5, len(_low_rows.columns), 18)
                ws2.freeze_panes(1, 0)

            # Sheet 3 — blocking structural issues
            _bl_rows = export.iloc[[i for i, s in enumerate(severity) if s == "block"]]
            if not _bl_rows.empty:
                _bl_rows.to_excel(writer, index=False, sheet_name="דורשות תיקון")
                ws3 = writer.sheets["דורשות תיקון"]
                for j, col in enumerate(_bl_rows.columns):
                    ws3.write(0, j, col, fmt_hdr)
                for i in range(len(_bl_rows)):
                    ws3.set_row(i + 1, None, fmt_block)
                ws3.set_column(0, 0, 40); ws3.set_column(5, len(_bl_rows.columns), 18)
                ws3.freeze_panes(1, 0)

            # Sheet 4 — summary
            _low_cnt  = sum(_low_mask)
            _med_cnt  = sum(c == "medium" for c in conf_col)
            _hi_cnt   = sum(c == "high"   for c in conf_col)
            pd.DataFrame([
                ("סה״כ שורות",          len(export)),
                ("סווגו ודאית",          _hi_cnt),
                ("סווגו בחלקיות",        _med_cnt),
                ("לסקירה ידנית",         _low_cnt),
                ("שגיאות מבניות",        n_block),
                ("אזהרות מבניות",        n_warn),
            ], columns=["מדד", "ערך"]).to_excel(writer, index=False, sheet_name="סיכום")
            ws4 = writer.sheets["סיכום"]
            ws4.set_column("A:A", 30); ws4.set_column("B:B", 14)
            for j, h in enumerate(["מדד", "ערך"]):
                ws4.write(0, j, h, fmt_hdr)

        return buf.getvalue()

    base = st.session_state.filename.replace(".xlsx", "")
    _dl_label = (
        f"📥 הורד קובץ Excel לסקירה — {len(df):,} שורות | "
        f"{n_high:,} ✅ ודאי | {n_medium:,} 🔵 חלקי | {n_low:,} ⚠️ לבדיקה"
    )
    st.download_button(
        label=_dl_label,
        data=_review_excel(df, flagged),
        file_name=f"{base}_לבדיקה.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # ── Re-upload corrected file ────────────────────────────────────────────
    with st.expander("📤 העלה קובץ מתוקן לבדיקה חוזרת", expanded=(n_block > 0)):
        st.markdown("לאחר תיקון ידני ב-Excel — העלו כאן את הקובץ המקורי המתוקן (לא קובץ הבדיקה) לבדיקה חוזרת.")
        reupload = st.file_uploader("קובץ מתוקן (.xlsx)", type=["xlsx"],
                                     key="reupload", label_visibility="collapsed")
        if reupload:
            try:
                df_fixed = pd.read_excel(reupload)
                df_fixed = df_fixed.drop(
                    columns=["תיאור_בעיה", "דורש_תיקון", "אזהרה_בלבד",
                             "רמת_ביטחון", "פירוט_החלטה"], errors="ignore")
                with st.spinner("מנקה ובודק שוב..."):
                    df_fixed = run_clean_in_memory(df_fixed)
                    df_fixed = auto_fix(df_fixed)
                flagged_new = fl.detect_flags(df_fixed, DATE_MIN, DATE_MAX, stage="clean")
                nb_new = fl.count_blocking(flagged_new)
                nw_new = fl.count_warnings(flagged_new)
                _cs_new = st.session_state.get("_clean_stats", {})
                nl_new  = _cs_new.get("conf_low", 0)
                st.markdown(
                    f'<div class="banner-success">✅ קובץ מתוקן נטען: '
                    f'<strong>{nb_new}</strong> חוסמות · <strong>{nw_new}</strong> אזהרות · '
                    f'<strong>{nl_new}</strong> נמוכי ביטחון</div>',
                    unsafe_allow_html=True,
                )
                if st.button("✅ אמץ קובץ מתוקן זה", type="primary", use_container_width=True):
                    st.session_state.df = df_fixed
                    st.session_state.filename = reupload.name
                    st.session_state.pop("_low_decisions", None)
                    st.session_state.pop("_medium_approved", None)
                    st.rerun()
            except Exception as e:
                st.markdown(f'<div class="banner-error">❌ שגיאה: {e}</div>',
                            unsafe_allow_html=True)

    if n_block > 0:
        st.markdown(
            f'<div class="banner-warn">⚠️ נותרו <strong>{n_block:,}</strong> שורות חוסמות. '
            f'הורידו את קובץ הבדיקה, תקנו את הגיליון <strong>"דורשות תיקון"</strong> '
            f'בקובץ המקורי, והעלו מחדש. '
            f'לחלופין — לחצו "החרג ועבור הלאה" אם הבעיות ידועות ואינן מונעות גאוקוד.</div>',
            unsafe_allow_html=True)

    # ── Navigation CTAs ─────────────────────────────────────────────────────
    st.markdown("---")
    _ready = (n_block == 0)

    if not _ready:
        st.markdown(
            '<div class="banner-warn">⛔ יש שגיאות מבניות — יש לתקן אותן לפני המשך לגאוקוד. '
            'הורד את קובץ ה-Excel, תקן את הגיליון "דורשות תיקון", והעלה חזרה.</div>',
            unsafe_allow_html=True)

    cta1, cta2, cta3 = st.columns([1, 1, 1])
    with cta1:
        if st.button("⬅ חזור להעלאה", use_container_width=True):
            st.session_state.df = None
            goto("upload")
    with cta2:
        if _ready:
            if st.button("▶ המשך לגאוקוד", type="primary", use_container_width=True):
                goto("geocode")
        else:
            st.button("▶ המשך לגאוקוד (יש לתקן שגיאות)", type="primary",
                      disabled=True, use_container_width=True)
    with cta3:
        if n_block > 0:
            if st.button("▶ עבור הלאה בכל זאת (רשום ביומן)", use_container_width=True):
                for _tid in fl.waived_tickets(flagged):
                    al.log_correction(_tid, "_flag_severity", "block", "waived", "waive")
                goto("geocode")


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 3 — GEOCODE (run + manual correction + gate)
# ══════════════════════════════════════════════════════════════════════════

elif stage == "geocode":
    df = st.session_state.df
    st.markdown("### שלב 3 — גאוקוד (המרת כתובות לקואורדינטות)")

    if not st.session_state.geocoded:
        st.markdown('<div class="step-card"><h4>מה קורה כאן?</h4><p>המערכת ממירה כל כתובת '
                    'לקואורדינטות בשלושה מעברים: Nominatim, מרכזי רחובות (OSM), ופורטל '
                    'ה-GIS העירוני. כתובות שלא נפתרו אוטומטית יופיעו לתיקון ידני.</p></div>',
                    unsafe_allow_html=True)

        # ── Resume from checkpoint if one exists ────────────────────────────
        checkpoint = _load_checkpoint(st.session_state.filename)
        if checkpoint is not None:
            rows_done = int(pd.to_numeric(
                checkpoint["קו_רוחב"].astype(str).str.replace(",", ""), errors="coerce"
            ).notna().sum())
            total_rows = len(checkpoint)
            pct_done = rows_done / total_rows * 100 if total_rows else 0
            st.markdown(
                f'<div class="banner-warn">🔄 <strong>נמצא קובץ המשך מריצה קודמת!</strong><br>'
                f'גאוקודדו <strong>{rows_done:,} מתוך {total_rows:,}</strong> שורות '
                f'({pct_done:.0f}%). '
                f'לחצו "המשך" כדי לחסוך את הזמן שכבר הושקע — '
                f'רק {total_rows - rows_done:,} השורות הנותרות יעובדו.</div>',
                unsafe_allow_html=True,
            )
            cr1, cr2 = st.columns(2)
            with cr1:
                if st.button("▶ המשך מנקודת עצירה", type="primary", use_container_width=True):
                    st.session_state.df = checkpoint
                    st.session_state["_auto_geocode"] = True
                    _clear_checkpoint(st.session_state.filename)
                    st.rerun()
            with cr2:
                if st.button("🗑️ בטל והתחל גאוקוד מחדש", use_container_width=True):
                    _clear_checkpoint(st.session_state.filename)
                    st.session_state.pop("_auto_geocode", None)
                    st.rerun()
        else:
            already = ("קו_רוחב" in df.columns and df["קו_רוחב"].notna().any())
            if already and not st.session_state.get("_auto_geocode"):
                st.markdown('<div class="banner-warn">⚠️ חלק מהשורות כבר מכילות קואורדינטות — '
                            'הגאוקוד ירוץ רק על שורות חסרות.</div>', unsafe_allow_html=True)

            _auto = st.session_state.pop("_auto_geocode", False)
            if _auto or st.button(
                "▶ המשך גאוקוד" if already else "▶ הרץ גאוקוד",
                type="primary", use_container_width=True
            ):
                prog = st.progress(0.0, text="מתחיל גאוקוד...")
                _df_ref = [df]

                # Save an immediate checkpoint so a crash at row 1 is still resumable
                _save_checkpoint(df, st.session_state.filename)

                def cb(pass_name, current, total, geocoded, failed):
                    if total > 0:
                        names = {"nominatim": "Nominatim", "gis": "פורטל GIS", "status": "מכין"}
                        label = names.get(pass_name, pass_name)
                        prog.progress(min(current / total, 1.0),
                                      text=f"{label}: {current:,}/{total:,} — נפתרו {geocoded:,}")

                def checkpoint_cb(df_snap):
                    _df_ref[0] = df_snap
                    _save_checkpoint(df_snap, st.session_state.filename)

                # checkpoint_every=25 — saves every 25 rows so closing mid-run
                # loses at most 25 rows of work instead of 100
                df_geo, gstats = gp.geocode_dataframe(df, progress_cb=cb,
                                                       checkpoint_cb=checkpoint_cb,
                                                       checkpoint_every=25)
                _df_ref[0] = df_geo  # update ref (though run is done)
                prog.progress(1.0, text="הושלם")
                _clear_checkpoint(st.session_state.filename)  # clean up on success
                st.session_state.df = df_geo
                st.session_state.geocoded = True
                st.session_state.stats.update({
                    "geo_ok": gstats["total_geocoded"],
                    "geo_pct": f"{gstats['coverage_pct']}%",
                    "rows": gstats["total_rows"],
                })
                _save_state()
                st.rerun()
    else:
        df = st.session_state.df
        flagged = fl.detect_flags(df, DATE_MIN, DATE_MAX, stage="geocode")
        n_block = fl.count_blocking(flagged)  # ungeocoded real addresses
        geo_ok = int(pd.to_numeric(df["קו_רוחב"].astype(str).str.replace(",", ""),
                                   errors="coerce").notna().sum())
        pct = geo_ok / len(df) * 100 if len(df) else 0

        st.markdown(f"""
        <div class="stat-row">
          <div class="stat-card good"><div class="num">{geo_ok:,}</div><div class="lbl">גאוקודד</div></div>
          <div class="stat-card"><div class="num">{pct:.1f}%</div><div class="lbl">אחוז כיסוי</div></div>
          <div class="stat-card alert"><div class="num">{n_block:,}</div><div class="lbl">לא נפתרו (חוסמות)</div></div>
        </div>
        """, unsafe_allow_html=True)

        if n_block > 0:
            st.markdown('<div class="banner-warn">⚠️ השורות הבאות לא גאוקודדו אוטומטית. '
                        'לחצו "נסה שוב דרך GIS" לניסיון נוסף, או הזינו קואורדינטות ידנית.</div>',
                        unsafe_allow_html=True)
            if st.button("🔄 נסה שוב — GIS בלבד", type="primary", use_container_width=True):
                with st.spinner("מתחבר לפורטל GIS העירוני..."):
                    df_retry = gp.gis_rescue_pass(st.session_state.df)
                    st.session_state.df = df_retry
                flagged_retry = fl.detect_flags(st.session_state.df, DATE_MIN, DATE_MAX, stage="geocode")
                n_block_retry = fl.count_blocking(flagged_retry)
                geo_ok_retry = int(pd.to_numeric(
                    st.session_state.df["קו_רוחב"].astype(str).str.replace(",", ""),
                    errors="coerce").notna().sum())
                if n_block_retry < n_block:
                    st.success(f"GIS פתר {n_block - n_block_retry} שורות נוספות — נותרו {n_block_retry} לא פתורות ({geo_ok_retry:,} גאוקודדו)")
                else:
                    st.error("פורטל GIS לא זמין כרגע — נסו שוב מאוחר יותר")
                st.rerun()
            unresolved = flagged[flagged["_flag_severity"] == "block"].copy()

            # Add a clickable Google Maps search link per row
            unresolved["🔗 Google Maps"] = unresolved.apply(
                lambda r: (
                    f'<a href="https://www.google.com/maps/search/?api=1&query='
                    f'{str(r.get("כתובת ואתר/מוסד","")).replace(" ","+")}+הרצליה" '
                    f'target="_blank">פתח מפה ↗</a>'
                ),
                axis=1,
            )

            # Show links table (read-only, HTML rendered) — RTL wrapper
            st.markdown(
                '<div style="direction:rtl;text-align:right">'
                + unresolved[["🔗 Google Maps", "כתובת ואתר/מוסד", "מס' פניה"]]
                .rename(columns={"מס' פניה": "מס׳ פניה"})
                .to_html(escape=False, index=False)
                + '</div>',
                unsafe_allow_html=True,
            )
            st.markdown("---")

            # ── Duplicate-address helper ──────────────────────────────────────
            # Show groups of unresolved rows that share the same address so the
            # user knows which ticket IDs to fill together in the bulk-paste box.
            _dup_key = ["רחוב_ראשי", "מספר_בית"]
            _dup_key_present = [c for c in _dup_key if c in unresolved.columns]
            if _dup_key_present:
                _addr_groups = (
                    unresolved.groupby(_dup_key_present, dropna=False)["מס' פניה"]
                    .apply(list)
                    .reset_index()
                )
                _multi = _addr_groups[_addr_groups["מס' פניה"].apply(len) > 1]
                if not _multi.empty:
                    with st.expander(f"🔁 {len(_multi)} כתובות שחוזרות על עצמן — הרחב לפרטים"):
                        st.caption("כתובות אלה מופיעות ביותר משורה אחת. הזן קואורדינטות פעם אחת בהזנה המרוכזת למטה.")
                        for _, _gr in _multi.iterrows():
                            _addr_lbl = " ".join(str(_gr[c]) for c in _dup_key_present if pd.notna(_gr[c]))
                            _ids = ", ".join(str(p) for p in _gr["מס' פניה"])
                            st.markdown(f"**{_addr_lbl}** — פניות: `{_ids}`")

            # ── Editable coordinate + address table ───────────────────────────
            cols_rtl = ["קו_אורך", "קו_רוחב", "מספר_בית", "רחוב_ראשי", "מס' פניה"]
            cols = [c for c in cols_rtl if c in unresolved.columns]
            st.caption(
                "ניתן לערוך: **קו רוחב**, **קו אורך**, **רחוב**, **מס׳ בית** (סיומות דירה/קומה יוסרו אוטומטית). "
                "העתקה/הדבקה: לחץ תא ← Ctrl+C ← לחץ יעד ← Ctrl+V. "
                "אם מופיע חלון הרשאה — לחץ 'אפשר'."
            )
            editor_df = unresolved[cols].copy()
            # Convert lat/lon to plain float so NaN renders as blank (not "None"/"ie")
            for coord_col in ["קו_רוחב", "קו_אורך"]:
                if coord_col in editor_df.columns:
                    editor_df[coord_col] = pd.to_numeric(
                        editor_df[coord_col].astype(str).str.replace(",", ""), errors="coerce"
                    ).astype(float)
            # Ticket ID numeric for right-align; house number stays as text so
            # values like "22 דירה 1" are visible and editable (stripped on writeback)
            if "מס' פניה" in editor_df.columns:
                editor_df["מס' פניה"] = pd.to_numeric(editor_df["מס' פניה"], errors="coerce")
            if "מספר_בית" in editor_df.columns:
                editor_df["מספר_בית"] = editor_df["מספר_בית"].astype(str).replace("nan", "")
            edited = st.data_editor(
                editor_df,
                use_container_width=True,
                height=360,
                num_rows="fixed",
                disabled=["מס' פניה"],           # street + house now editable
                key="geo_editor",
                column_config={
                    "מס' פניה":  st.column_config.NumberColumn("מס׳ פניה",   width="small",  format="%d"),
                    "רחוב_ראשי": st.column_config.TextColumn("רחוב ✏️",       width="large",
                                     help="ניתן לתקן שגיאות איות"),
                    "מספר_בית":  st.column_config.TextColumn("מס׳ בית ✏️",   width="small",
                                     help="הזן מספר בניין בלבד — דירה/קומה/כניסה יוסרו"),
                    "קו_רוחב":   st.column_config.NumberColumn("קו רוחב ✏️",  width="large",
                                     min_value=32.0, max_value=33.0, format="%.6f",
                                     help="לחץ על תא והזן ערך, או העתק/הדבק (Ctrl+C / Ctrl+V)"),
                    "קו_אורך":   st.column_config.NumberColumn("קו אורך ✏️",  width="large",
                                     min_value=34.0, max_value=35.5, format="%.6f",
                                     help="לחץ על תא והזן ערך, או העתק/הדבק (Ctrl+C / Ctrl+V)"),
                },
            )

            # Write back all editable columns to the main DataFrame
            for coord_col in ["קו_רוחב", "קו_אורך"]:
                if coord_col in edited.columns:
                    df.loc[unresolved.index, coord_col] = pd.to_numeric(
                        edited[coord_col].astype(str).str.replace(",", ""), errors="coerce")
            # Mark manually-edited rows with coordinates
            _edited_has_coords = (
                pd.to_numeric(edited["קו_רוחב"].astype(str).str.replace(",", ""), errors="coerce").notna()
                & pd.to_numeric(edited["קו_אורך"].astype(str).str.replace(",", ""), errors="coerce").notna()
            )
            df.loc[unresolved.index[_edited_has_coords], "geocode_method"] = "manual"
            df.loc[unresolved.index[_edited_has_coords], "דיוק_גאוקוד"] = "address"
            # Audit log — manual editor coordinate entries
            for _idx in unresolved.index[_edited_has_coords]:
                _pid = df.at[_idx, "מס' פניה"]
                al.log_correction(_pid, "קו_רוחב", None, df.at[_idx, "קו_רוחב"], "manual_editor")
                al.log_correction(_pid, "קו_אורך", None, df.at[_idx, "קו_אורך"], "manual_editor")
            if "רחוב_ראשי" in edited.columns:
                df.loc[unresolved.index, "רחוב_ראשי"] = edited["רחוב_ראשי"].values
            if "מספר_בית" in edited.columns:
                def _strip_apt(v):
                    s = str(v).strip()
                    if not s or s in ("nan", "None", "0"):
                        return ""
                    s = re.sub(r'\s*[/\\]\s*\d+$', '', s).strip()
                    s = re.sub(r'\s*דירה\s*\d*', '', s, flags=re.IGNORECASE).strip()
                    s = re.sub(r'\s*קומה\s*\d*', '', s, flags=re.IGNORECASE).strip()
                    s = re.sub(r'\s*כניסה\s*\w*', '', s, flags=re.IGNORECASE).strip()
                    return s
                df.loc[unresolved.index, "מספר_בית"] = edited["מספר_בית"].apply(_strip_apt).values
            st.session_state.df = df
            _save_state()   # persist after every edit — prevents data loss on session reset

            # ── Bulk paste ────────────────────────────────────────────────────
            st.markdown("**הזנה מרוכזת** — שימושי כשאותן קואורדינטות שייכות לכמה שורות")
            st.markdown("פורמט: `מספר_פניה,קו_רוחב,קו_אורך` — שורה לכל פניה. "
                        "ניתן לשכפל אותה שורה עם מספרי פניה שונים כדי למלא כמה שורות בבת אחת.")
            st.markdown('<style>[data-testid="stTextArea"] textarea { direction: ltr; text-align: left; }</style>',
                        unsafe_allow_html=True)
            bulk = st.text_area("הדבק כאן", height=100,
                                placeholder="12345,32.165120,34.832450\n12346,32.165120,34.832450\n12350,32.171000,34.841000",
                                key="geo_bulk")
            bc1, bc2 = st.columns([1, 1])
            with bc1:
                if st.button("💾 החל הזנה מרוכזת", use_container_width=True):
                    applied = 0
                    for line in bulk.strip().splitlines():
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) == 3:
                            pid, lat_s, lon_s = parts
                            try:
                                lat_v, lon_v = float(lat_s), float(lon_s)
                                mask = df["מס' פניה"].astype(str) == pid
                                df.loc[mask, "קו_רוחב"] = lat_v
                                df.loc[mask, "קו_אורך"] = lon_v
                                df.loc[mask, "geocode_method"] = "manual"
                                df.loc[mask, "דיוק_גאוקוד"] = "address"
                                al.log_correction(pid, "קו_רוחב", None, lat_v, "bulk_paste")
                                al.log_correction(pid, "קו_אורך", None, lon_v, "bulk_paste")
                                applied += 1
                            except ValueError:
                                pass
                    st.session_state.df = df
                    _save_state()
                    st.success(f"עודכנו {applied} שורות")
                    st.rerun()
            with bc2:
                if st.button("💾 שמור תיקונים ידניים", use_container_width=True):
                    _save_state()
                    st.success("נשמר!")
                    st.rerun()
        else:
            st.markdown('<div class="banner-success">✅ כל הכתובות גאוקודדו בהצלחה</div>',
                        unsafe_allow_html=True)

        st.divider()
        cta1, cta2, cta3 = st.columns([1, 1, 1])
        with cta1:
            if st.button("⬅ חזור לניקוי", use_container_width=True):
                goto("clean")
        with cta2:
            if n_block == 0:
                if st.button("▶ המשך להעשרה", type="primary", use_container_width=True):
                    goto("enrich")
            else:
                st.button(f"▶ המשך להעשרה (נותרו {n_block} לא פתורות)",
                          disabled=True, use_container_width=True)
        with cta3:
            if n_block > 0:
                if st.button("▶ החרג ועבור הלאה (רשום ב-יומן)", use_container_width=True):
                    _geo_flagged = fl.detect_flags(
                        st.session_state.df, DATE_MIN, DATE_MAX, stage="geocode")
                    for _tid in fl.waived_tickets(_geo_flagged):
                        al.log_correction(_tid, "_flag_severity", "block", "waived", "waive")
                    goto("enrich")


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 4 — ENRICH (zones + gate)
# ══════════════════════════════════════════════════════════════════════════

elif stage == "enrich":
    df = st.session_state.df
    st.markdown("### שלב 4 — העשרה (שיוך רובעי פינוי)")

    # Auto-recompute if coords changed since last enrichment
    _current_fp = ep.coord_fingerprint(df)
    _stored_fp = st.session_state.get("enrich_fingerprint", "")
    _needs_enrich = (not st.session_state.enriched) or (_current_fp != _stored_fp)

    if _needs_enrich:
        with st.spinner("משייך רובעים..."):
            df_en, estats = ep.enrich_dataframe(df)
            st.session_state.df = df_en
            df = df_en
            st.session_state.enriched = True
            st.session_state.enrich_fingerprint = _current_fp
            st.session_state.stats.update({
                "in_city": estats["in_city"],
                "same_day": estats["same_day"],
                "same_day_pct": f"{estats['same_day_pct']}%",
            })
            _save_state()

    if True:
        df = st.session_state.df
        n_unknown = int((df["רובע_פינוי"] == "לא ידוע").sum())
        n_out = int((df["רובע_פינוי"] == "מחוץ לתחום").sum())
        in_city = int((~df["רובע_פינוי"].isin(["לא ידוע", "מחוץ לתחום"])).sum())

        st.markdown(f"""
        <div class="stat-row">
          <div class="stat-card good"><div class="num">{in_city:,}</div><div class="lbl">בתוך תחום העיר</div></div>
          <div class="stat-card warn"><div class="num">{n_out:,}</div><div class="lbl">מחוץ לתחום</div></div>
          <div class="stat-card alert"><div class="num">{n_unknown:,}</div><div class="lbl">לא ידוע (ללא קואורדינטות)</div></div>
        </div>
        """, unsafe_allow_html=True)

        zc = df["רובע_פינוי"].value_counts().reset_index()
        zc.columns = ["רובע", "מספר פניות"]
        st.dataframe(_center_style(zc), use_container_width=True, hide_index=True)

        if n_unknown > 0:
            st.markdown(f'<div class="banner-warn">⚠️ {n_unknown} שורות ללא רובע — אלו שורות '
                        'ללא קואורדינטות (כתובות תיאוריות כמו חוף הים). ניתן להמשיך.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="banner-success">✅ כל השורות שויכו לרובע</div>',
                        unsafe_allow_html=True)

        st.divider()
        cta1, cta2 = st.columns([1, 1])
        with cta1:
            if st.button("⬅ חזור לגאוקוד", use_container_width=True):
                goto("geocode")
        with cta2:
            if st.button("▶ המשך לפלט וניתוח", type="primary", use_container_width=True):
                goto("output")


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 5 — OUTPUT (filters → heatmap + analytics + single download)
# ══════════════════════════════════════════════════════════════════════════

elif stage == "output":
    df = st.session_state.df
    st.markdown("### שלב 5 — פלט וניתוח")

    # Auto-recompute enrichment if coords changed
    _out_fp = ep.coord_fingerprint(df)
    if st.session_state.get("enrich_fingerprint", "") != _out_fp:
        with st.spinner("עדכון שיוך רובעים..."):
            df_re, estats = ep.enrich_dataframe(df)
            st.session_state.df = df_re
            df = df_re
            st.session_state.enriched = True
            st.session_state.enrich_fingerprint = _out_fp
            st.session_state.stats.update({
                "in_city": estats["in_city"],
                "same_day": estats["same_day"],
                "same_day_pct": f"{estats['same_day_pct']}%",
            })
            _save_state()

    # ── FILTERS (drive both heatmap and analytics) ──────────────────────────
    st.markdown('<div class="step-card"><h4>סינון נתונים</h4><p>בחרו את פרוסת הנתונים שברצונכם '
                'לראות. הבחירה משפיעה גם על מפת החום וגם על הניתוח. ברירת המחדל היא כל הנתונים.</p></div>',
                unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3)
    with f1:
        zones = ["הכל"] + sorted([z for z in df.get("רובע_פינוי", pd.Series()).dropna().unique()])
        sel_zone = st.selectbox("רובע", zones, key="f_zone")
    with f2:
        cats = ["הכל"] + sorted([c for c in df.get("תת_נושא_חדש", pd.Series()).dropna().unique()])
        sel_cat = st.selectbox("קטגוריה", cats, key="f_cat")
    with f3:
        resps = ["הכל"] + sorted([r for r in df.get("אחריות", pd.Series()).dropna().unique()])
        sel_resp = st.selectbox("אחריות", resps, key="f_resp")

    f4, f5, f6 = st.columns(3)
    with f4:
        statuses = ["הכל"] + sorted([s for s in df.get("סטטוס פנייה", pd.Series()).dropna().unique()])
        sel_status = st.selectbox("סטטוס", statuses, key="f_status")
    with f5:
        sel_recur = st.selectbox("חזרתיות", ["הכל", "חוזרות בלבד", "ראשונות בלבד"], key="f_recur")
    with f6:
        months = ["הכל"] + sorted([int(m) for m in df.get("חודש", pd.Series()).dropna().unique()])
        sel_month = st.selectbox("חודש", months, key="f_month")

    # Apply filters
    d = df.copy()
    if sel_zone != "הכל":   d = d[d["רובע_פינוי"] == sel_zone]
    if sel_cat != "הכל":    d = d[d["תת_נושא_חדש"] == sel_cat]
    if sel_resp != "הכל":   d = d[d["אחריות"] == sel_resp]
    if sel_status != "הכל": d = d[d["סטטוס פנייה"] == sel_status]
    if sel_recur == "חוזרות בלבד":  d = d[d["תלונה_חוזרת"] == 1]
    elif sel_recur == "ראשונות בלבד": d = d[d["תלונה_חוזרת"] == 0]
    if sel_month != "הכל":  d = d[d["חודש"] == sel_month]

    st.caption(f"מציג {len(d):,} מתוך {len(df):,} שורות")

    tab_map, tab_analytics, tab_download, tab_qa = st.tabs(
        ["🗺️ מפת חום", "📈 ניתוח", "⬇️ הורדה", "🎲 דגימת QA"])

    # ── HEATMAP ─────────────────────────────────────────────────────────────
    with tab_map:
        if len(d) == 0:
            st.info("אין נתונים לתצוגה עם הסינון הנוכחי.")
        else:
            html = hm.build_heatmap(d, show_markers=True,
                                    title=f"תלונות תברואה ({len(d):,})")
            components.html(html, height=600)

    # ── ANALYTICS ───────────────────────────────────────────────────────────
    with tab_analytics:
        if len(d) == 0:
            st.info("אין נתונים לתצוגה עם הסינון הנוכחי.")
        else:
            BLUE, GREEN, AMBER, RED, GRAY = "#2563a8","#059669","#d97706","#dc2626","#64748b"

            def _top(s):
                vc = s.dropna().value_counts()
                return (vc.index[0], int(vc.iloc[0])) if len(vc) else ("—", 0)

            tc, tcn = _top(d["תת_נושא_חדש"])
            ts, tsn = _top(d["רחוב_ראשי"])
            recur = d["תלונה_חוזרת"].mean()*100 if "תלונה_חוזרת" in d else 0
            muni  = (d["אחריות"]=="כשל עירוני").mean()*100 if "אחריות" in d else 0
            same  = (d["תלונה_ביום_פינוי"]==1).mean()*100 if "תלונה_ביום_פינוי" in d else 0

            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("קטגוריה מובילה", tc, f"{tcn:,}")
            m2.metric("רחוב מוביל", ts, f"{tsn:,}")
            m3.metric("תלונות חוזרות", f"{recur:.1f}%")
            m4.metric("אחריות עירונית", f"{muni:.1f}%")
            m5.metric("ביום פינוי", f"{same:.1f}%")
            st.divider()

            ca, cb = st.columns([3,2])
            with ca:
                cc = d["תת_נושא_חדש"].value_counts().reset_index()
                cc.columns = ["קטגוריה","פניות"]
                fig = px.bar(cc, x="פניות", y="קטגוריה", orientation="h",
                             color_discrete_sequence=[BLUE], text="פניות")
                fig.update_traces(textposition="outside")
                fig.update_layout(yaxis=dict(categoryorder="total ascending"),
                                  height=max(300, len(cc)*32), showlegend=False,
                                  font_family="Heebo", title_text="קטגוריות", title_x=1,
                                  xaxis_title="", yaxis_title="", plot_bgcolor="#f8fafc")
                st.plotly_chart(fig, use_container_width=True)
            with cb:
                rc = d["אחריות"].value_counts().reset_index()
                rc.columns = ["אחריות","מספר"]
                cmap = {"כשל עירוני":BLUE,"התנהגות אזרח":AMBER,"טבעי":GREEN,
                        "לא רלוונטי":GRAY,"א.מ.ל":RED}
                fig = px.pie(rc, names="אחריות", values="מספר", hole=0.45,
                             color="אחריות", color_discrete_map=cmap)
                fig.update_traces(textposition="outside", textinfo="label+percent")
                fig.update_layout(font_family="Heebo", title_text="אחריות", title_x=1,
                                  showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # Zone distribution
            if "רובע_פינוי" in d.columns:
                zc = d["רובע_פינוי"].value_counts().reset_index()
                zc.columns = ["רובע","פניות"]
                fig = px.bar(zc, x="רובע", y="פניות", color_discrete_sequence=[BLUE], text="פניות")
                fig.update_traces(textposition="outside")
                fig.update_layout(font_family="Heebo", title_text="פניות לפי רובע", title_x=1,
                                  xaxis_title="", yaxis_title="", showlegend=False, plot_bgcolor="#f8fafc")
                st.plotly_chart(fig, use_container_width=True)

            # Monthly trend
            if "חודש" in d.columns:
                MH = {1:"ינואר",2:"פברואר",3:"מרץ",4:"אפריל",5:"מאי",6:"יוני",
                      7:"יולי",8:"אוגוסט",9:"ספטמבר",10:"אוקטובר",11:"נובמבר",12:"דצמבר"}
                mc = d["חודש"].dropna().astype(int).value_counts().sort_index().reset_index()
                mc.columns = ["חודש","פניות"]
                mc["שם"] = mc["חודש"].map(MH)
                fig = px.line(mc, x="שם", y="פניות", markers=True,
                              color_discrete_sequence=[BLUE], text="פניות")
                fig.update_traces(textposition="top center")
                fig.update_layout(font_family="Heebo", title_text="מגמה חודשית", title_x=1,
                                  xaxis_title="", yaxis_title="", plot_bgcolor="#f8fafc")
                st.plotly_chart(fig, use_container_width=True)

            # Top recurring hotspots
            st.markdown("#### 🔁 מוקדי תלונות חוזרות")
            hot = (d[d["תלונה_חוזרת"]==1]
                   .groupby(["רחוב_ראשי","מספר_בית","תת_נושא_חדש"]).size()
                   .reset_index(name="חזרות").sort_values("חזרות", ascending=False).head(10)
                   .rename(columns={"רחוב_ראשי":"רחוב","מספר_בית":"מס׳ בית","תת_נושא_חדש":"קטגוריה"}))
            if not hot.empty:
                st.dataframe(_center_style(hot), use_container_width=True, hide_index=True)
            else:
                st.caption("אין תלונות חוזרות בפרוסה זו.")

    # ── DOWNLOAD (single file) ──────────────────────────────────────────────
    with tab_download:
        st.markdown('<div class="step-card"><h4>קובץ פלט יחיד</h4><p>קובץ Excel אחד המכיל את כל '
                    'הנתונים המעובדים: מנוקים, מגאוקודים, ומועשרים. שורות עם דגלים מסומנות בצבע '
                    '(אדום = דורש תיקון, צהוב = אזהרה) וכולל גיליון סיכום.</p></div>',
                    unsafe_allow_html=True)

        stats = st.session_state.stats.copy()
        stats.update({
            "rows": len(df),
            "recurring": int(df["תלונה_חוזרת"].sum()) if "תלונה_חוזרת" in df else 0,
            "recurring_pct": f"{df['תלונה_חוזרת'].mean()*100:.1f}%" if "תלונה_חוזרת" in df else "",
            "warn_rows": fl.count_warnings(fl.detect_flags(df, DATE_MIN, DATE_MAX, stage="all")),
        })

        base = st.session_state.filename.replace(".xlsx", "")
        st.download_button(
            label=f"📥 הורד קובץ מעובד ({len(df):,} שורות)",
            data=excel_bytes(df, stats),
            file_name=f"{base}_מעובד.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary", use_container_width=True,
        )
        st.divider()
        if st.button("🔄 עבד קובץ חדש", use_container_width=True):
            st.session_state.df = None
            st.session_state.stats = {}
            st.session_state.geocoded = False
            st.session_state.enriched = False
            _clear_state()
            goto("upload")

    # ── QA SAMPLING TAB ─────────────────────────────────────────────────────
    with tab_qa:
        import acceptance_sampling as qs

        st.markdown('<div class="step-card"><h4>דגימת קבלה — אפס פגמים</h4>'
                    '<p>בוחנת מדגם אקראי מכל רמת גאוקוד. פסיקה: ✅ קבל (0 פגמים) '
                    'או ❌ דחה (פגם ≥1). גודל המדגם מחושב לפי סיכון צרכן β=10%.</p></div>',
                    unsafe_allow_html=True)

        _qa_seed = st.number_input("זרע אקראיות (0 = כל פעם שונה)", min_value=0,
                                   max_value=99999, value=42, step=1, key="qa_seed")
        if st.button("▶ הרץ דגימת QA", type="primary", use_container_width=True):
            _qa_result = qs.run_sampling_plan(df, seed=int(_qa_seed) or None)
            st.dataframe(_center_style(_qa_result), use_container_width=True, hide_index=True)
            n_reject = int((_qa_result["פסיקה"].str.startswith("❌")).sum())
            if n_reject == 0:
                st.success("כל הרמות עברו את דגימת ה-QA")
            else:
                st.warning(f"{n_reject} רמות לא עברו את הדגימה — יש לבדוק")


# ══════════════════════════════════════════════════════════════════════════
#  VALIDATION MODE — compare pipeline output to a reference file
# ══════════════════════════════════════════════════════════════════════════

elif stage == "validate":
    import validation as vl

    st.markdown("### מצב אימות — השוואה לקובץ יחוס")
    st.markdown('<div class="step-card"><h4>מה קורה כאן?</h4>'
                '<p>העלו קובץ Excel שנבדק ידנית ("יחוס"). המערכת תצרף אותו לנתוני הצינור '
                'לפי <strong>מס׳ פניה</strong> ותציג טבלת הסכמה לכל עמודה.</p></div>',
                unsafe_allow_html=True)

    ref_file = st.file_uploader("קובץ יחוס (.xlsx)", type=["xlsx"],
                                key="ref_upload", label_visibility="visible")

    if ref_file and st.session_state.get("df") is not None:
        try:
            ref_df = pd.read_excel(ref_file)
            result = vl.compare_to_reference(st.session_state.df, ref_df)

            c1, c2, c3 = st.columns(3)
            c1.metric("שורות תואמות", f"{result['matched_rows']:,}")
            c2.metric("רק בצינור",    f"{result['only_pipeline']:,}")
            c3.metric("רק ביחוס",     f"{result['only_reference']:,}")

            st.markdown("#### הסכמה לפי עמודה")
            st.dataframe(
                _center_style(result["per_column"].sort_values("אחוז_הסכמה")),
                hide_index=True,
                column_config={
                    "עמודה":       st.column_config.TextColumn("עמודה",          width=160),
                    "הסכמה":       st.column_config.NumberColumn("הסכמה",         width=80),
                    "שונה":        st.column_config.NumberColumn("שונה",          width=80),
                    "חסר_בצינור":  st.column_config.NumberColumn("חסר בצינור",    width=100),
                    "אחוז_הסכמה":  st.column_config.NumberColumn("% הסכמה",       width=90,
                                                                  format="%.1f%%"),
                },
            )
            with st.expander("📋 פרטי שורות שונות"):
                _diff_cfg = {c: st.column_config.TextColumn(c, width=140)
                             for c in result["diff"].columns}
                st.dataframe(_center_style(result["diff"]), column_config=_diff_cfg, hide_index=True)
        except Exception as e:
            st.error(f"שגיאה בהשוואה: {e}")
    elif ref_file is None:
        if st.session_state.get("df") is None:
            st.info("טענו קובץ נתונים לצינור לפני הפעלת מצב אימות.")
    if st.button("⬅ חזור לפלט", use_container_width=True):
        goto("output")
