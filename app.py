# -*- coding: utf-8 -*-
# SYNC TEST 3 - 2026-07-25
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
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
    _AGGRID_OK = True
except ImportError:
    _AGGRID_OK = False
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
import importlib
sys.path.insert(0, ".")
# Force-evict any stale cached module from a prior Streamlit Cloud deploy
for _mod in ("clean_pipeline", "geocode_pipeline", "enrich_pipeline",
             "flags", "heatmap", "audit_log"):
    sys.modules.pop(_mod, None)
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
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {
    overflow-x: auto !important;
    max-width: 100% !important;
}
[data-testid="stDataFrame"] [role="columnheader"],
[data-testid="stDataFrame"] [role="gridcell"] {
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    direction: rtl !important;
    text-align: right !important;
    padding-right: 8px !important;
    padding-left: 4px !important;
    unicode-bidi: plaintext !important;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    min-width: 80px !important;
}
.stDataFrame > div { overflow-x: auto !important; overflow-y: auto !important; }
/* data_editor same treatment */
[data-testid="stDataEditor"] [role="gridcell"] {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext !important;
}

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

# Bump when the persisted shape changes in a way older files cannot satisfy.
STATE_SCHEMA_VERSION = 2

# Session keys that must survive a reconnect.  Anything omitted here is
# silently lost on restore, which previously desynchronised the Q&A undo
# buffer and the enrichment fingerprint from the DataFrame they describe.
_PERSIST_KEYS = [
    "stage", "df", "filename", "stats", "run_id",
    "_clean_stats", "_context_resolved", "_df_before_qa", "_qa_applied",
    "enrich_fingerprint",
]


def _derive_geocoded(df) -> bool:
    """Infer geocode completion from the data itself, not a stored flag."""
    if df is None or "קו_רוחב" not in df.columns:
        return False
    return bool(pd.to_numeric(df["קו_רוחב"], errors="coerce").notna().any())


def _derive_enriched(df) -> bool:
    """Infer enrichment completion from the data itself, not a stored flag."""
    if df is None:
        return False
    return any(c in df.columns for c in ("תלונה_חוזרת", "תלונה_ביום_פינוי"))


def _save_state():
    """Persist session state to disk, stamped with schema version + columns."""
    try:
        df = st.session_state.get("df")
        state = {k: st.session_state.get(k) for k in _PERSIST_KEYS}
        state["stage"] = st.session_state.get("stage", "upload")
        state["filename"] = st.session_state.get("filename", "")
        state["stats"] = st.session_state.get("stats", {})
        state["_schema_version"] = STATE_SCHEMA_VERSION
        state["_columns"] = list(df.columns) if df is not None else []
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
    except Exception:
        st.session_state["_restore_error"] = "קובץ המצב פגום ולא ניתן לשחזור."
        return

    df = state.get("df")
    if df is None or len(df) == 0:
        return

    ver = state.get("_schema_version", 1)
    if ver != STATE_SCHEMA_VERSION:
        # Restore anyway — the data is still usable — but say so, because
        # features that depend on newer columns will be degraded.
        st.session_state["_restore_stale"] = (
            f"הקובץ המשוחזר נשמר בגרסה ישנה יותר של המערכת (גרסה {ver}). "
            "הנתונים נטענו, אך ייתכן שחלק מהמידע על אופן העיבוד חסר."
        )

    for k, v in state.items():
        if k.startswith("_schema") or k == "_columns":
            continue
        st.session_state.setdefault(k, v)

    # Stage-completion flags are derived, never trusted from the pickle.
    st.session_state["geocoded"] = _derive_geocoded(df)
    st.session_state["enriched"] = _derive_enriched(df)
    st.session_state["_just_restored"] = True

    # Bring pre-2026-08 responsibility labels onto the current vocabulary so
    # restored files chart and filter alongside newly-processed ones.
    try:
        _df = st.session_state.get("df")
        if _df is not None and "אחריות" in _df.columns:
            _df["אחריות"] = _df["אחריות"].map(
                lambda v: cp.LEGACY_RESPONSIBILITIES.get(str(v).strip(), v)
            )
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
    ss.setdefault("run_id", al.new_run_id())

_init_state()

# app.py force-evicts pipeline modules from sys.modules on every rerun, so the
# audit log's module-level run id must be re-applied from session state here.
al.set_run(st.session_state["run_id"])

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
    Find street names whose raw forms differ in spelling (not just whitespace/numbers).

    Groups raw forms by their normalized key. A group is shown only when there
    are genuinely different spellings — trailing spaces and appended house numbers
    are NOT considered different spellings.

    Returns list of:
      {"canonical": str, "total": int, "variants": [{"raw": str, "count": int}],
       "registry_match": str|None}
    sorted by total occurrences descending, capped at 15 groups.
    """
    try:
        import re as _re
        import unicodedata as _ud
        from collections import defaultdict as _dd
        import geocode_pipeline as _gp

        _prefix = _re.compile(r"^(רחוב|רח[׳'״]|ר[׳'״]|ה?רחוב)\s+", _re.UNICODE)
        # A trailing house-number token: leading separator, digits, optional
        # apartment letter, optional /sub-number — e.g. " 14", " 14א", " 14/2", ", 3"
        _house = _re.compile(r"[\s,./\-]+\d{1,4}\s*[א-ת]?(?:\s*/\s*\d+)?\s*$", _re.UNICODE)
        _trailing_punct = _re.compile(r"[\s,\.;׳״'\"־\-]+$", _re.UNICODE)

        def _clean_raw(s: str) -> str:
            """
            Reduce a raw street value to its bare NAME: drop the רחוב prefix,
            then repeatedly strip trailing house numbers and punctuation. House
            numbers are NOT part of the street name and must never make two rows
            look like different spellings.
            """
            s = str(s).strip()
            s = _prefix.sub("", s)
            prev = None
            while prev != s:
                prev = s
                stripped = _house.sub("", s).strip()
                # Never strip away the whole name (guard streets that end in a digit)
                if stripped and _re.search(r"[א-ת]", stripped):
                    s = stripped
                s2 = _trailing_punct.sub("", s).strip()
                if s2 and _re.search(r"[א-ת]", s2):
                    s = s2
            return s.strip()

        def _norm_key(s: str) -> str:
            """NFC-normalize so ״/" quote variants of the same name collapse."""
            return _ud.normalize("NFC", _clean_raw(s))

        streets = df["רחוב_ראשי"].dropna().astype(str) if "רחוב_ראשי" in df.columns else pd.Series(dtype=str)
        streets = streets[streets.str.strip() != ""]

        # Count occurrences of each cleaned raw form (deduplicates trailing-space variants)
        cleaned_counts: dict = {}
        for raw in streets:
            cleaned = _clean_raw(raw)
            if cleaned:
                cleaned_counts[cleaned] = cleaned_counts.get(cleaned, 0) + 1

        # Group cleaned → normalized-key
        norm_groups: dict = _dd(lambda: _dd(int))
        for cleaned, cnt in cleaned_counts.items():
            norm_groups[_norm_key(cleaned)][cleaned] += cnt

        results = []
        for norm_key, cleaned_cnt_map in norm_groups.items():
            total = sum(cleaned_cnt_map.values())
            if total < 4:
                continue
            all_cleaned = sorted(cleaned_cnt_map, key=lambda k: -cleaned_cnt_map[k])
            canonical = all_cleaned[0]
            # Variants = every OTHER cleaned spelling (numbers already stripped, so
            # anything remaining is a genuine spelling difference). Show up to 6.
            variants = [{"raw": r, "count": cleaned_cnt_map[r]} for r in all_cleaned[1:]][:6]

            # Check registry for the official canonical spelling
            reg_canon, _ = _gp._registry_resolve(norm_key)
            if reg_canon is None:
                reg_canon, _ = _gp._registry_resolve(canonical)

            # Surface a group if there are competing spellings in the data, OR the
            # data's spelling differs from the official municipal registry.
            if variants or (reg_canon and reg_canon != canonical):
                results.append({
                    "canonical": canonical,
                    "normalized": norm_key,
                    "total": total,
                    "variants": variants,
                    "registry_match": reg_canon,
                })

        return sorted(results, key=lambda x: -x["total"])[:30]
    except Exception:
        return []


# ── Colour maps for semantic columns ────────────────────────────────────────
_RESP_BG = {
    "עירייה":          "#dbeafe",
    "התנהגות אזרח":   "#ffedd5",
    "טבעי":            "#d1fae5",
    "בקשה מהעירייה":  "#f1f5f9",
    # legacy labels — kept for backward compatibility with older pickles
    "כשל עירוני":      "#dbeafe",
    "לא רלוונטי":      "#f1f5f9",
    "א.מ.ל":           "#fef9c3",
}
_CONF_BG = {"high": "#d1fae5", "medium": "#dbeafe", "low": "#ffedd5"}
_FLAG_BG = {"block": "#fee2e2", "warn": "#fef3c7", "":  ""}

# Pretty column headers (internal name → display label)
_COL_LABELS = {
    "מס' פניה": "מס׳ פניה", "תאריך": "תאריך", "תת_נושא_חדש": "קטגוריה",
    "אחריות": "אחריות", "רחוב_ראשי": "רחוב", "מספר_בית": "מס׳ בית",
    "סוג_מיקום": "סוג מיקום", "geocode_method": "גאוקוד",
    "_flag_labels": "בעיות", "_confidence": "ביטחון",
    "כתובת ואתר/מוסד": "כתובת מקורית", "תת נושא": "נושא מקורי",
    "תיאור": "תיאור", "סוג בעיה": "סוג בעיה", "שורות": "שורות",
    "רובע": "רובע", "מספר פניות": "מספר פניות",
    "רחוב": "רחוב", "מס׳ בית": "מס׳ בית", "קטגוריה": "קטגוריה",
    "עמודה": "עמודה", "אחוז_הסכמה": "% הסכמה", "הסכמות": "הסכמות",
    "חילוקים": "חילוקים",
}


def _style_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """
    Apply semantic row/cell colouring to a DataFrame and return a Styler.
    Colours responsibility, confidence, and flag-severity columns; leaves
    everything else white. All cells are centred and RTL.
    """
    styled = df.style.set_properties(**{
        "text-align": "center", "direction": "rtl",
        "font-size": "0.84rem", "padding": "5px 10px",
    }).set_table_styles([{
        "selector": "th",
        "props": [("text-align", "center"), ("direction", "rtl"),
                  ("font-size", "0.82rem"), ("background", "#f8fafc"),
                  ("font-weight", "600"), ("padding", "6px 10px")],
    }])

    def _cell_color(val, col):
        bg = ""
        if col == "אחריות":
            bg = _RESP_BG.get(str(val), "")
        elif col == "_confidence":
            bg = _CONF_BG.get(str(val), "")
        elif col == "_flag_severity":
            bg = _FLAG_BG.get(str(val), "")
        elif col == "_flag_labels" and str(val).strip():
            bg = "#fff7ed"
        return f"background:{bg};" if bg else ""

    for col in df.columns:
        if col in ("אחריות", "_confidence", "_flag_severity", "_flag_labels"):
            styled = styled.map(lambda v, c=col: _cell_color(v, c), subset=[col])

    return styled


def _col_cfg(df: pd.DataFrame) -> dict:
    """Build column_config dict with labelled, width-appropriate columns."""
    cfg = {}
    for c in df.columns:
        label = _COL_LABELS.get(c, c)
        if c in ("תיאור", "כתובת ואתר/מוסד", "_flag_labels"):
            cfg[c] = st.column_config.TextColumn(label, width="large")
        elif c in ("מס' פניה", "תאריך", "מספר_בית", "מס׳ בית", "שורות", "מספר פניות"):
            cfg[c] = st.column_config.TextColumn(label, width="small")
        elif c in ("אחוז_הסכמה",):
            cfg[c] = st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.1f%%")
        else:
            cfg[c] = st.column_config.TextColumn(label, width="medium")
    return cfg


def _table(df: pd.DataFrame, *, search: bool = False, max_rows: int = 2000,
           height: int | None = None, caption: str = "", use_container_width: bool = True):
    """
    Unified interactive table renderer used everywhere in the app.

    • Semantic colour-coding on responsibility, confidence, and flag columns
    • Optional live search bar that filters all text columns simultaneously
    • Auto-height based on row count (capped at 800 px)
    • 'Show more' caption when rows are truncated
    • מס' פניה always first column (renders rightmost in RTL)
    """
    display = df.copy()
    display = display[[c for c in display.columns if not c.startswith("_flag_severity")]]

    # Ensure ticket ID is first column (rightmost in RTL display)
    if "מס' פניה" in display.columns:
        cols = ["מס' פניה"] + [c for c in display.columns if c != "מס' פניה"]
        display = display[cols]

    if search and len(display) > 5:
        _q = st.text_input("🔍 חיפוש בטבלה", key=f"_tbl_search_{id(df)}",
                           placeholder="הקלד לסינון שורות...", label_visibility="collapsed")
        if _q:
            mask = display.apply(
                lambda col: col.astype(str).str.contains(_q, case=False, na=False)
            ).any(axis=1)
            display = display[mask]
            if display.empty:
                st.caption(f"אין תוצאות עבור \"{_q}\"")
                return

    total = len(display)
    display = display.head(max_rows)
    h = height or min(800, max(60, len(display) * 36 + 44))

    st.dataframe(
        _style_table(display),
        column_config=_col_cfg(display),
        hide_index=True,
        height=h,
        use_container_width=use_container_width,
    )
    parts = []
    if caption:
        parts.append(caption)
    if total > max_rows:
        parts.append(f"מוצגות {max_rows:,} שורות ראשונות מתוך {total:,}")
    if parts:
        st.caption(" · ".join(parts))


def _center_style(df: pd.DataFrame):
    """Legacy alias — kept so call sites not yet migrated still work."""
    return _style_table(df)


def _render_flagged_table(df: pd.DataFrame, max_rows: int = 500):
    """Render the flag-detail table (blocking / review rows)."""
    KEEP = ["מס' פניה", "תאריך", "כתובת ואתר/מוסד", "רחוב_ראשי",
            "מספר_בית", "סוג_מיקום", "geocode_method", "_flag_labels"]
    display = df[[c for c in KEEP if c in df.columns]].copy()
    _table(display, search=True, max_rows=max_rows)


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


def _render_stepper_nav(current: str):
    """Render the stepper as clickable Streamlit buttons (one per completed/active stage)."""
    order = [s[0] for s in STAGES]
    ci = order.index(current)
    has_data = st.session_state.get("df") is not None
    cols = st.columns(len(STAGES))
    for i, (key, label) in enumerate(STAGES):
        is_active = key == current
        is_done   = i < ci
        is_next   = i > ci
        # Can navigate to: any done stage, or current stage (no-op), or next stage if data exists
        reachable = (is_done or is_active) and has_data
        with cols[len(STAGES) - 1 - i]:   # RTL: reverse column order
            if is_active:
                st.button(f"{'✓ ' if is_done else ''}{i+1}. {label}", disabled=True,
                          use_container_width=True, key=f"_step_{key}")
            elif reachable:
                if st.button(f"✓ {i+1}. {label}", use_container_width=True, key=f"_step_{key}"):
                    goto(key)
            else:
                st.button(f"{i+1}. {label}", disabled=True, use_container_width=True,
                          key=f"_step_{key}")


# ══════════════════════════════════════════════════════════════════════════
#  PROVENANCE + CACHING HELPERS
# ══════════════════════════════════════════════════════════════════════════

# Columns written by clean_pipeline that record *how* each decision was made.
# Files produced before these existed cannot be audited — absence of the
# columns means "unknown", never "nothing was corrected".
PROVENANCE_COLS = ["סיווג_מקור", "אחריות_מקור", "מסלול_כתובת"]


def _provenance_status(df: pd.DataFrame) -> tuple:
    """
    Return (level, missing) where level is:
      "full"    — all provenance columns present
      "partial" — some present
      "none"    — none present (legacy file; nothing can be audited)
    """
    if df is None:
        return "none", list(PROVENANCE_COLS)
    missing = [c for c in PROVENANCE_COLS if c not in df.columns]
    if not missing:
        return "full", []
    if len(missing) == len(PROVENANCE_COLS):
        return "none", missing
    return "partial", missing


def _provenance_notice(level: str, missing: list) -> str:
    """Human explanation for a degraded provenance state."""
    if level == "none":
        return ("קובץ זה נטען לפני שהמערכת התחילה לתעד את מקור ההחלטות, "
                "ולכן <strong>לא ניתן להציג מה תוקן אוטומטית</strong>. "
                "אין משמעות הדבר שלא בוצעו תיקונים — רק שאין דרך לבדוק אותם. "
                "כדי לקבל יומן מלא, יש להעלות את הקובץ המקורי מחדש ולהריץ את שלב הניקוי.")
    return ("חלק מנתוני המקור חסרים בקובץ זה (" + ", ".join(missing) + "), "
            "ולכן היומן להלן חלקי ואינו מכסה את כל התיקונים שבוצעו.")


@st.cache_data(show_spinner=False, max_entries=4)
def _detect_flags_cached(df: pd.DataFrame, dmin: str, dmax: str, stage: str):
    """Cached wrapper around flags.detect_flags — re-runs only when df changes."""
    return fl.detect_flags(df, dmin, dmax, stage=stage)


# ══════════════════════════════════════════════════════════════════════════
#  CAPABILITY PROBE
#  Several geocoding sources are optional at import time and degrade silently
#  when their dependency is missing.  Probe them once per session and show the
#  result, so a degraded run is visible rather than merely slower.
# ══════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=3600)
def _probe_capabilities() -> dict:
    """Return {key: (ok: bool, detail: str)} for each optional subsystem."""
    caps = {}

    # ── Local municipal address DB (geopandas + shapefile) ──────────────
    try:
        import geopandas  # noqa: F401
        shp = gp.LOCAL_ADDRESS_SHP
        if not os.path.exists(shp):
            caps["local_db"] = (False, "קובץ הכתובות העירוני חסר מהפריסה")
        else:
            gp._load_local_db()
            n = len(gp._LOCAL_ADDR_IDX)
            if n == 0:
                caps["local_db"] = (False, "קובץ הכתובות נטען אך ריק")
            else:
                caps["local_db"] = (True, f"{n:,} כתובות")
    except ImportError:
        caps["local_db"] = (False, "geopandas לא מותקן")
    except Exception as e:
        caps["local_db"] = (False, f"שגיאת טעינה: {type(e).__name__}")

    # ── GIS portal rescue (Playwright + Chromium binary) ────────────────
    try:
        from playwright.sync_api import sync_playwright
        exe = None
        try:
            with sync_playwright() as p:
                exe = p.chromium.executable_path
        except Exception:
            pass
        if exe and os.path.exists(exe):
            caps["gis"] = (True, "דפדפן זמין")
        else:
            caps["gis"] = (False, "דפדפן Chromium לא הותקן בשרת")
    except ImportError:
        caps["gis"] = (False, "playwright לא מותקן")
    except Exception as e:
        caps["gis"] = (False, f"לא זמין: {type(e).__name__}")

    # ── Interactive table renderer ──────────────────────────────────────
    caps["aggrid"] = (
        (True, "טבלה אינטראקטיבית")
        if _AGGRID_OK else
        (False, "streamlit-aggrid לא מותקן — טבלה בסיסית")
    )

    return caps


_CAP_LABELS = {
    "local_db": "מאגר כתובות עירוני",
    "gis":      "פורטל GIS",
    "aggrid":   "תצוגת טבלה",
}


def _render_capability_banner():
    """One-line status strip for the optional subsystems."""
    try:
        caps = _probe_capabilities()
    except Exception:
        return

    degraded = [k for k, (ok, _) in caps.items() if not ok]
    parts = []
    for key, (ok, detail) in caps.items():
        icon = "🟢" if ok else "🔴"
        parts.append(f"{icon} {_CAP_LABELS.get(key, key)} — {detail}")
    line = " &nbsp;·&nbsp; ".join(parts)

    if degraded:
        note = ""
        if "local_db" in degraded or "gis" in degraded:
            note = ("<br><span style='font-size:.85em'>מקורות גאוקוד חסרים — "
                    "האיתור יסתמך על שירות חיצוני איטי יותר ופחות מדויק. "
                    "התוצאות עדיין תקפות, אך הכיסוי עשוי להיות נמוך יותר.</span>")
        st.markdown(
            f'<div class="banner-warn">⚠️ <strong>חלק מהמקורות אינם פעילים</strong><br>{line}{note}</div>',
            unsafe_allow_html=True)
    else:
        with st.expander("🟢 כל המקורות פעילים", expanded=False):
            st.markdown(line.replace(" &nbsp;·&nbsp; ", "  \n"))


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

_render_capability_banner()

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

_restore_err = st.session_state.pop("_restore_error", None)
if _restore_err:
    st.markdown(f'<div class="banner-error">⚠️ {_restore_err}</div>', unsafe_allow_html=True)

_restore_stale = st.session_state.get("_restore_stale")
if _restore_stale:
    st.markdown(f'<div class="banner-warn">ℹ️ {_restore_stale}</div>', unsafe_allow_html=True)

_render_stepper_nav(st.session_state.stage)
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
                _table(df_raw[_preview_cols], max_rows=5)
                if st.button("▶ התחל עיבוד — נקה נתונים", type="primary", use_container_width=True):
                    # A new source file is a new run: give it its own audit log.
                    st.session_state["run_id"] = al.set_run(al.new_run_id())
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

    # ── Run multi-column auto-resolution on first visit ────────────────────
    if not st.session_state.get("_context_resolved"):
        df = cp.auto_resolve_from_context(df)
        st.session_state.df = df
        st.session_state["_context_resolved"] = True
        _ccs = st.session_state.get("_clean_stats", {}).copy()
        _ccs["conf_high"]   = int((df["_confidence"] == "high").sum()   if "_confidence" in df.columns else 0)
        _ccs["conf_medium"] = int((df["_confidence"] == "medium").sum() if "_confidence" in df.columns else 0)
        _ccs["conf_low"]    = int((df["_confidence"] == "low").sum()    if "_confidence" in df.columns else 0)
        st.session_state["_clean_stats"] = _ccs

    flagged = _detect_flags_cached(df, DATE_MIN, DATE_MAX, "clean")
    n_block = fl.count_blocking(flagged)
    n_warn  = fl.count_warnings(flagged)

    # ── Confidence tier counts ──────────────────────────────────────────────
    _cs = st.session_state.get("_clean_stats", {})
    n_high   = _cs.get("conf_high",   int((df.get("_confidence", pd.Series()) == "high").sum())   if "_confidence" in df.columns else 0)
    n_medium = _cs.get("conf_medium", int((df.get("_confidence", pd.Series()) == "medium").sum()) if "_confidence" in df.columns else 0)
    n_low    = _cs.get("conf_low",    int((df.get("_confidence", pd.Series()) == "low").sum())    if "_confidence" in df.columns else 0)
    n_auto = n_high + n_medium

    st.markdown("### שלב 2 — ניקוי: סקירת תיקונים ועדכון ידני")

    # ── Section anchors for in-page navigation ───────────────────────────────
    st.markdown(
        '<div style="display:flex;flex-direction:row-reverse;gap:.6rem;margin-bottom:1rem;">'
        '<a href="#section-summary" style="text-decoration:none;background:#e0f2fe;border:1px solid #7dd3fc;'
        'padding:.35rem .8rem;border-radius:6px;font-size:.82rem;color:#0369a1;">📊 סיכום</a>'
        '<a href="#section-corrections" style="text-decoration:none;background:#f0fdf4;border:1px solid #86efac;'
        'padding:.35rem .8rem;border-radius:6px;font-size:.82rem;color:#166534;">📋 יומן תיקונים</a>'
        '<a href="#section-qa" style="text-decoration:none;background:#eff6ff;border:1px solid #bfdbfe;'
        'padding:.35rem .8rem;border-radius:6px;font-size:.82rem;color:#1e40af;">🙋 שאלות</a>'
        '<a href="#section-download" style="text-decoration:none;background:#f8fafc;border:1px solid #e2e8f0;'
        'padding:.35rem .8rem;border-radius:6px;font-size:.82rem;color:#475569;">📤 הורדה</a>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Success banner after Q&A apply ────────────────────────────────────────
    if st.session_state.pop("_qa_applied", False):
        st.success(
            "✅ **התשובות הוחלו בהצלחה.** הנתונים עודכנו. "
            "הורד את קובץ ה-Excel למטה לבדיקת השורות שנותרו לבירור ידני, "
            "ואז המשך לגאוקוד.",
            icon="✅",
        )

    # ── Undo last Q&A apply ─────────────────────────────────────────────────
    if st.session_state.get("_df_before_qa") is not None:
        if st.button("↩️ בטל את התשובות האחרונות שהוחלו", key="_undo_qa"):
            st.session_state.df = st.session_state.pop("_df_before_qa")
            df = st.session_state.df
            st.session_state.pop("_context_resolved", None)
            st.rerun()

    # ── Count correction types for summary breakdown ─────────────────────────
    # NB: when a provenance column is absent we must render "—" (unknown),
    # never 0, which would assert that no corrections were made.
    _prov_level, _prov_missing = _provenance_status(df)

    _n_cat_corrections = None
    _n_resp_corrections = None
    if "סיווג_מקור" in df.columns:
        _n_cat_corrections = int((df["סיווג_מקור"] == "map").sum())
    if "אחריות_מקור" in df.columns:
        _resp_src_col = df["אחריות_מקור"].astype(str)
        _n_resp_corrections = int(
            (_resp_src_col == "map").sum() +
            _resp_src_col.str.startswith("keyword:").sum() +
            (_resp_src_col == "context_resolve").sum()
        )

    _cat_txt  = f"{_n_cat_corrections:,} קטגוריה"  if _n_cat_corrections  is not None else "— קטגוריה"
    _resp_txt = f"{_n_resp_corrections:,} אחריות" if _n_resp_corrections is not None else "— אחריות"
    if _prov_level == "none":
        _breakdown_txt = "פירוט לא זמין לקובץ זה"
    else:
        _breakdown_txt = f"{_cat_txt} · {_resp_txt}"

    # ── Summary cards (3 cards: auto-processed, awaiting input, structural) ─
    st.markdown('<div id="section-summary"></div>', unsafe_allow_html=True)
    _pct_auto = round(n_auto / len(df) * 100) if len(df) else 0
    # Without _confidence there is no basis for the auto-processed count, so it
    # must read as unknown rather than as zero.
    _conf_known = ("_confidence" in df.columns) or bool(_cs.get("conf_high") or _cs.get("conf_medium"))
    _auto_big   = f"{n_auto:,}" if _conf_known else "—"
    _auto_line  = (
        f'✅ <strong>{_pct_auto}%</strong> מהשורות ({n_auto:,}) עובדו אוטומטית — '
        f'ניתן לעיין ביומן התיקונים ולתקן.'
        if _conf_known else
        'ℹ️ לא ניתן לדעת כמה שורות עובדו אוטומטית בקובץ זה — נתוני רמת הביטחון אינם נשמרו בו. '
        'העלו את הקובץ המקורי והריצו את שלב הניקוי כדי לקבל נתון זה.'
    )
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
    .cc-orange {{background:#ffedd5;border:1px solid #fdba74;}}
    .cc-orange .cn {{color:#9a3412;}}
    .cc-gray   {{background:#f1f5f9;border:1px solid #cbd5e1;}}
    .cc-gray .cn   {{color:#334155;}}
    </style>
    <div class="conf-row">
      <div class="conf-card cc-green">
        <div class="cn">{_auto_big}</div>
        <div class="cl">✅ עובדו אוטומטית</div>
        <div class="cs">{_breakdown_txt}</div>
      </div>
      <div class="conf-card cc-orange">
        <div class="cn">{n_low:,}</div>
        <div class="cl">🙋 ממתינות לקלט</div>
        <div class="cs">ענו על השאלות למטה או הורידו לבדיקה ב-Excel</div>
      </div>
      <div class="conf-card cc-gray">
        <div class="cn">{n_block:,}</div>
        <div class="cl">⛔ שגיאות מבניות</div>
        <div class="cs">נתון חסר/שגוי · חוסם המשך</div>
      </div>
    </div>
    <div style="text-align:right;color:#475569;font-size:.84rem;margin-bottom:1rem;">
      {_auto_line}
      {f"🙋 <strong>{n_low:,}</strong> שורות ממתינות לקלט שלך." if n_low > 0 else ""}
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    #  CORRECTION LOG — transparent view of all auto-changes
    # ════════════════════════════════════════════════════════

    _SOURCE_LABELS = {
        "map": "מילון מיפוי",
        "context_resolve": "הקשר אוטומטי",
        "user_override": "תיקון ידני",
        "user_qa": "תשובת משתמש",
        "user_resp_term": "תשובת משתמש",
        "user_resp_default": "תשובת משתמש (ברירת מחדל)",
        "manual_review": "סימון לבדיקה",
    }

    @st.cache_data(show_spinner=False, max_entries=3)
    def _build_correction_log(df: pd.DataFrame) -> pd.DataFrame:
        """One row per correction. Includes type, method, and original CRM context.

        Cached: this is a full Python-level pass over every row, and without
        caching it re-ran on every widget interaction in the stage.
        """
        route_labels = {"std": "כתובת", "intersection": "צומת",
                        "range": "טווח", "apt_suffix": "סיומת דירה",
                        "multi": "מרובה", "landmark": "ציון דרך"}
        _col = {c: i for i, c in enumerate(df.columns)}
        rows = []
        for row in df.itertuples(index=False, name=None):
            def _g(col, default=""):
                i = _col.get(col)
                if i is None:
                    return default
                v = row[i]
                return str(v).strip() if pd.notna(v) else default

            ticket     = _g("מס' פניה")
            street     = _g("רחוב_ראשי")
            house      = _g("מספר_בית")
            desc       = _g("תיאור")[:80]
            orig_topic = _g("נושא")
            orig_sub   = _g("תת נושא")
            new_cat    = _g("תת_נושא_חדש")
            cat_src    = _g("סיווג_מקור")
            resp       = _g("אחריות")
            resp_src   = _g("אחריות_מקור")
            raw_addr   = _g("כתובת ואתר/מוסד")
            addr_route = _g("מסלול_כתובת")
            status     = _g("סטטוס פנייה")
            date_col   = _g("תאריך")
            substance  = _g("חומר")
            asset      = _g("נכס")

            has_cat  = bool(orig_sub and new_cat and orig_sub != new_cat and cat_src == "map")
            has_resp = (resp_src in ("map",) and resp not in ("א.מ.ל", "")) or \
                       resp_src.startswith("keyword:") or resp_src == "context_resolve"
            _real_routes = {"std", "intersection", "range", "apt_suffix", "multi", "landmark"}
            has_addr = bool(addr_route in _real_routes and street and raw_addr and len(raw_addr) > 2)

            if not (has_cat or has_resp or has_addr):
                continue

            _base = {
                "מס' פניה":    ticket,
                "תאריך":       date_col,
                "נושא":        orig_topic,
                "תת נושא":     orig_sub,
                "חומר":        substance,
                "נכס":         asset,
                "רחוב":        street,
                "בית":         house,
                "סטטוס":       status,
                "תיאור":       desc,
            }

            if has_cat:
                _method = _SOURCE_LABELS.get(cat_src, cat_src)
                _mahut = f'תת-נושא "{orig_sub}" שויך לקטגוריה "{new_cat}" לפי טבלת המיפוי'
                rows.append({
                    **_base,
                    "סוג תיקון":   "קטגוריה",
                    "לפני":        orig_sub,
                    "אחרי":        new_cat,
                    "מהות התיקון": _mahut,
                })
            if has_resp:
                if resp_src == "map":
                    _mahut = f'אחריות נקבעה כ"{resp}" — כל פניות הקטגוריה "{new_cat}" מסווגות כך'
                elif resp_src.startswith("keyword:"):
                    _kw = resp_src.split(":", 1)[1]
                    _mahut = f'אחריות נקבעה כ"{resp}" בגלל מילת המפתח "{_kw}" שנמצאה בתיאור'
                elif resp_src == "context_resolve":
                    _mahut = f'אחריות נקבעה כ"{resp}" מהקשר: הפנייה טופלה והקטגוריה מצביעה על כשל בציוד'
                else:
                    _mahut = f'אחריות נקבעה כ"{resp}"'
                rows.append({
                    **_base,
                    "סוג תיקון":   "אחריות",
                    "לפני":        "לא מסווג",
                    "אחרי":        resp,
                    "מהות התיקון": _mahut,
                })
            if has_addr:
                _route_he = route_labels.get(addr_route, addr_route)
                _mahut = f'כתובת "{raw_addr[:50]}" נוּתחה: רחוב "{street}", בית {house} (סוג: {_route_he})'
                rows.append({
                    **_base,
                    "סוג תיקון":   "כתובת",
                    "לפני":        raw_addr[:60],
                    "אחרי":        f"{street} {house}".strip(),
                    "מהות התיקון": _mahut,
                })

        cols = ["מס' פניה", "תאריך", "נושא", "תת נושא", "חומר", "נכס",
                "רחוב", "בית", "סטטוס", "תיאור",
                "סוג תיקון", "לפני", "אחרי", "מהות התיקון"]
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

    # Only meaningful when the provenance columns exist; otherwise the loop
    # would return an empty frame and we would render "0 corrections", which
    # is a false claim rather than a missing one.
    _corr_log = (_build_correction_log(df) if _prov_level != "none"
                 else pd.DataFrame())

    # Count by correction type
    _corr_n_total = len(_corr_log)
    _corr_n_tickets = _corr_log["מס' פניה"].nunique() if not _corr_log.empty else 0
    _type_counts = _corr_log["סוג תיקון"].value_counts().to_dict() if not _corr_log.empty else {}
    _corr_has_cat  = _type_counts.get("קטגוריה", 0)
    _corr_has_resp = _type_counts.get("אחריות", 0)
    _corr_has_addr = _type_counts.get("כתובת", 0)

    st.markdown('<div id="section-corrections"></div>', unsafe_allow_html=True)
    _corr_title = (
        "📋 יומן תיקונים אוטומטיים — לא זמין לקובץ זה"
        if _prov_level == "none" else
        f"📋 יומן תיקונים אוטומטיים — {_corr_n_tickets:,} כרטיסים, {_corr_n_total:,} תיקונים"
        + ("  ⚠️ חלקי" if _prov_level == "partial" else "")
    )
    with st.expander(_corr_title, expanded=False):
        if _prov_level != "full":
            st.markdown(
                f'<div class="banner-warn">ℹ️ {_provenance_notice(_prov_level, _prov_missing)}</div>',
                unsafe_allow_html=True)

        if _prov_level == "none":
            pass  # nothing can be shown; the notice above explains why
        elif _corr_log.empty:
            st.info("לא בוצעו תיקונים אוטומטיים.")
        else:
            _stats_parts = []
            if _corr_has_cat:  _stats_parts.append(f"{_corr_has_cat:,} קטגוריה")
            if _corr_has_resp: _stats_parts.append(f"{_corr_has_resp:,} אחריות")
            if _corr_has_addr: _stats_parts.append(f"{_corr_has_addr:,} כתובת")
            st.markdown(
                f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;'
                f'padding:.6rem 1rem;font-size:.85rem;direction:rtl;margin-bottom:.8rem;">'
                f'סה"כ {_corr_n_tickets:,} כרטיסים · {" · ".join(_stats_parts)}'
                f'</div>', unsafe_allow_html=True,
            )

            # AG Grid has per-column filters so the multiselect is redundant when AG Grid is available
            _filtered_log = _corr_log

            if _AGGRID_OK and not _filtered_log.empty:
                _rtl_cols = list(reversed(_filtered_log.columns.tolist()))
                _rtl_df = _filtered_log[_rtl_cols]
                _gb = GridOptionsBuilder.from_dataframe(_rtl_df)
                _gb.configure_default_column(
                    filterable=True, sortable=True, resizable=True,
                    wrapText=False, autoHeight=False, minWidth=80,
                )
                _gb.configure_column("מס' פניה", pinned="right", width=90, suppressSizeToFit=True)
                _gb.configure_column("סוג תיקון", width=100, suppressSizeToFit=True)
                _gb.configure_column("מהות התיקון", width=320)
                _gb.configure_column("לפני", width=130, suppressSizeToFit=True)
                _gb.configure_column("אחרי", width=130, suppressSizeToFit=True)
                _gb.configure_column("תיאור", width=200)
                _gb.configure_grid_options(
                    enableRtl=True,
                    domLayout="normal",
                    rowHeight=32,
                    headerHeight=36,
                    suppressColumnVirtualisation=False,
                    defaultColDef={"floatingFilter": True},
                )
                _gb.configure_pagination(enabled=False)
                _gb.configure_selection("single")
                _grid_resp = AgGrid(
                    _rtl_df,
                    gridOptions=_gb.build(),
                    height=560,
                    update_mode=GridUpdateMode.NO_UPDATE,
                    allow_unsafe_jscode=False,
                    key="_corr_aggrid",
                )
            else:
                _grid_resp = None
                _table(_filtered_log, search=True, max_rows=2000, height=600)

            # Export correction log as Excel
            _corr_buf = io.BytesIO()
            _filtered_log.to_excel(_corr_buf, index=False, engine="xlsxwriter")
            st.download_button(
                "📥 הורד יומן תיקונים כ-Excel",
                _corr_buf.getvalue(),
                file_name="יומן_תיקונים.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="_dl_corr_log",
            )

            # Override mechanism — select a row in the grid OR type a ticket ID
            st.markdown("---")
            _selected_ticket = ""
            if _AGGRID_OK and _grid_resp is not None:
                _sel_rows = _grid_resp.get("selected_rows", None)
                if _sel_rows is not None and len(_sel_rows) > 0:
                    _sel_row = _sel_rows[0] if isinstance(_sel_rows, list) else _sel_rows.iloc[0]
                    _selected_ticket = str(_sel_row.get("מס' פניה", ""))

            if _selected_ticket:
                st.markdown(
                    f'<div style="background:#dbeafe;border:1px solid #93c5fd;border-radius:8px;'
                    f'padding:.6rem 1rem;font-size:.84rem;direction:rtl;margin-bottom:.6rem;">'
                    f'✏️ <strong>נבחר כרטיס {_selected_ticket}</strong> — '
                    f'בחר עמודה לתיקון והזן ערך חדש:</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;'
                    'padding:.6rem 1rem;font-size:.84rem;direction:rtl;margin-bottom:.6rem;">'
                    '✏️ <strong>מצאת שגיאה?</strong> לחץ על שורה בטבלה, או הקלד מספר פניה:</div>',
                    unsafe_allow_html=True,
                )

            _ov_c1, _ov_c2, _ov_c3 = st.columns([1, 1, 2])
            with _ov_c1:
                _ov_ticket = st.text_input(
                    "מס' פניה לתיקון", key="_ov_ticket",
                    value=_selected_ticket,
                    placeholder="לדוגמה: 2178241",
                )
            with _ov_c2:
                _ov_col = st.selectbox("עמודה", ["תת_נושא_חדש", "אחריות", "רחוב_ראשי", "מספר_בית"],
                                       key="_ov_col")
            with _ov_c3:
                _ov_val = st.text_input("ערך חדש", key="_ov_val")

            _ov_b1, _ov_b2 = st.columns(2)
            with _ov_b1:
                if st.button("✏️ החל תיקון", key="_ov_apply", use_container_width=True):
                    if _ov_ticket and _ov_val:
                        _mask = df["מס' פניה"].astype(str) == str(_ov_ticket).strip()
                        if _mask.any():
                            _old_v = df.loc[_mask, _ov_col].iloc[0]
                            df.loc[_mask, _ov_col] = _ov_val
                            if _ov_col == "אחריות":
                                df.loc[_mask, "אחריות_מקור"] = "user_override"
                            elif _ov_col == "תת_נושא_חדש":
                                df.loc[_mask, "סיווג_מקור"] = "user_override"
                            al.log_correction(_ov_ticket, _ov_col, _old_v, _ov_val, "user_override")
                            st.session_state.df = df
                            _save_state()
                            st.rerun()
                        else:
                            st.warning(f"לא נמצאה פניה עם מספר {_ov_ticket}")
                    else:
                        st.warning("נא למלא מספר פניה וערך חדש")
            with _ov_b2:
                if st.button("📋 סמן לבדיקה ב-Excel", key="_ov_manual", use_container_width=True):
                    if _ov_ticket:
                        _mask = df["מס' פניה"].astype(str) == str(_ov_ticket).strip()
                        if _mask.any():
                            df.loc[_mask, "_confidence"] = "low"
                            if "אחריות_מקור" in df.columns:
                                df.loc[_mask, "אחריות_מקור"] = "manual_review"
                            st.session_state.df = df
                            _save_state()
                            st.rerun()

    # ════════════════════════════════════════════════════════
    #  Q&A — resolve uncertain rows before export
    # ════════════════════════════════════════════════════════
    _clusters  = cp.find_clusters(df)
    _st_vars   = _find_street_variants(df)
    _has_questions = bool(_clusters["unknown_subtopics"] or _clusters["unresolved_resp"] or _st_vars)

    _TIP_RESP = _tip(
        "<strong>עירייה</strong> — העירייה לא ביצעה את עבודתה: "
        "פינוי לא תקין, ניקוי שלא נעשה, ציוד שהתקלקל, עובדי ניקוי שלא הגיעו<br><br>"
        "<strong>התנהגות אזרח</strong> — אזרח גרם לבעיה: "
        "זרק אשפה, פיזר פסולת, גנב ציוד, גרם נזק<br><br>"
        "<strong>טבעי</strong> — הטבע הוא הגורם: "
        "גשם, רוח, עלים נשרו, ציפורים, בעלי חיים<br><br>"
        "<strong>בקשה מהעירייה</strong> — בקשת שירות או תחזוקה: "
        "מילוי שקיות כלבים, פינוי חריג, ציוד ציבורי"
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

    st.markdown('<div id="section-qa"></div>', unsafe_allow_html=True)
    if _has_questions:
        st.markdown("---")
        _total_q_rows = (
            sum(c["count"] for c in _clusters["unknown_subtopics"]) +
            sum(c["unresolved"] for c in _clusters["unresolved_resp"]) +
            sum(v["total"] for v in _st_vars)
        )
        _total_q_count = (
            len(_st_vars) +
            len(_clusters["unknown_subtopics"]) +
            sum(len(c.get("pattern_groups", [])) for c in _clusters["unresolved_resp"])
        )
        st.markdown(
            f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;'
            f'padding:.8rem 1.1rem;font-size:.9rem;direction:rtl;margin-bottom:1rem;">'
            f'🙋 <strong>נדרש קלט ממך</strong> — {_total_q_count} שאלות על {_total_q_rows:,} פניות. '
            f'ענה על השאלות הבאות כדי שהמערכת תסווג אותן אוטומטית. '
            f'לכל שאלה יש כפתור ❓ עם הסבר — רחף מעליו לפני שאתה עונה.'
            f'</div>',
            unsafe_allow_html=True,
        )

        _qa_answers: dict = {}
        _q_num = 0

        # ── Type 1: Street name variants ──────────────────────────────────
        if _st_vars:
            st.markdown(
                f'**🗺️ שמות רחובות בכתיבות שונות ({len(_st_vars)} שאלות)** {_TIP_STREET}',
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
                _q_num += 1
                _can  = _sv["canonical"]
                _tot  = _sv["total"]
                _reg  = _sv.get("registry_match")
                _vars = _sv["variants"]
                _vars_text = ", ".join(f'"{v["raw"]}" ({v["count"]}×)' for v in _vars[:4])
                _reg_note = (
                    f'<br><small style="color:#065f46;">✅ שם רשמי ב-GIS: <strong>{_reg}</strong></small>'
                ) if _reg and _reg != _can else ""
                # Sample full addresses for context
                _addr_samples = []
                if "כתובת ואתר/מוסד" in df.columns and "רחוב_ראשי" in df.columns:
                    _all_raw = [_can] + [v["raw"] for v in _vars]
                    _sample_mask = df["רחוב_ראשי"].isin(_all_raw)
                    _addr_samples = (df.loc[_sample_mask, "כתובת ואתר/מוסד"]
                                     .dropna().astype(str).unique()[:3].tolist())
                _addr_html = ""
                if _addr_samples:
                    _addr_html = (
                        '<br><small style="color:#64748b;font-size:.79rem;">'
                        '<em>דוגמאות כתובות:</em> '
                        + " · ".join(f'"{a}"' for a in _addr_samples) + '</small>'
                    )
                st.markdown(
                    f'<div style="background:#f0fdf4;border-right:3px solid #4ade80;'
                    f'padding:.55rem .9rem;border-radius:6px;direction:rtl;margin:.5rem 0 .2rem;">'
                    f'<strong>שאלה {_q_num}/{_total_q_count}: האם אלה אותו רחוב?</strong><br>'
                    f'"{_can}" ({_tot - sum(v["count"] for v in _vars)}×)'
                    f'{f", {_vars_text}" if _vars_text else ""}'
                    f'{_reg_note}{_addr_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                _all_forms = list(dict.fromkeys([_can] + [v["raw"] for v in _vars]))
                _seen = set()
                _deduped = []
                for _f in _all_forms:
                    _fk = _f.strip()
                    if _fk not in _seen:
                        _seen.add(_fk)
                        _deduped.append(_f)
                _street_opts = ["השאר כמו שיש"] + (
                    [_reg] if _reg and _reg not in _deduped else []
                ) + _deduped
                _street_opts = list(dict.fromkeys(_street_opts))
                _ans = st.selectbox(
                    f'מה הכתיב הנכון של "{_can}"?',
                    _street_opts, key=f"qa_street_{_can}",
                    index=1 if _reg and _reg not in _deduped else 0,
                    help="בחר את הכתיב הנכון. כל הכתיבות האחרות יאוחדו לכתיב שתבחר.",
                )
                # Accept any choice that isn't "leave as-is" — even if the answer
                # equals _can, we still need to remap all other variants to it.
                if _ans != "השאר כמו שיש":
                    for _raw_v in _deduped:
                        if _raw_v != _ans:
                            _qa_answers[f"street:{_raw_v}"] = _ans

        # ── Type 2: Unknown sub-topics ────────────────────────────────────
        if _clusters["unknown_subtopics"]:
            st.markdown(
                f'**📋 תת-נושאים שלא מוכרים למערכת ({len(_clusters["unknown_subtopics"])} שאלות)** {_TIP_CAT}',
                unsafe_allow_html=True,
            )
            for _cl in _clusters["unknown_subtopics"]:
                _q_num += 1
                _sub = _cl["value"]
                _cnt = _cl["count"]
                _ex  = " • ".join(_cl.get("examples", [])[:2])
                st.markdown(
                    f'<div style="background:#fff7ed;border-right:3px solid #fb923c;'
                    f'padding:.55rem .9rem;border-radius:6px;direction:rtl;margin:.5rem 0 .2rem;">'
                    f'<strong>שאלה {_q_num}/{_total_q_count}: "{_sub}"</strong> — {_cnt:,} פניות'
                    f'{f"<br><small style=color:#78716c;font-size:.8rem>{_ex}</small>" if _ex else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                _opts = ["השאר לבדיקה ב-Excel"] + cp.KNOWN_CATEGORIES_LIST
                _ans = st.selectbox(
                    f'לאיזו קטגוריה שייכות פניות "{_sub}"?',
                    _opts, key=f"qa_sub_{_sub}",
                    help="בחר את הקטגוריה המתאימה.",
                )
                if _ans != "השאר לבדיקה ב-Excel":
                    _qa_answers[f"subtopic:{_sub}"] = _ans

        # ── Type 3: Ambiguous responsibility — context-rich questions ─────
        if _clusters["unresolved_resp"]:
            st.markdown(
                f'**📋 פניות שדורשות הכרעה** {_TIP_RESP}',
                unsafe_allow_html=True,
            )
            _RESP_HELP = (
                "לפי תוכן הפנייה, מי גרם לבעיה?\n\n"
                "1. **עירייה** — העירייה לא ביצעה (פינוי/ניקוי שלא נעשה, ציוד שהתקלקל)\n\n"
                "2. **התנהגות אזרח** — אדם גרם לבעיה (זרק אשפה, פיזר פסולת)\n\n"
                "3. **טבעי** — הטבע גרם (גשם, רוח, עלים, ציפורים)\n\n"
                "4. **בקשה מהעירייה** — בקשת שירות או תחזוקה\n\n"
                "אם לא בטוח — השאר 'לא ידוע'."
            )
            _RESP_OPTS = ["— לא ידוע —"] + cp.KNOWN_RESPONSIBILITIES

            for _cl in _clusters["unresolved_resp"]:
                _cat      = _cl["category"]
                _unres    = _cl.get("unresolved", 0)
                _pgroups  = _cl.get("pattern_groups", [])
                _remain   = _cl.get("remainder", 0)
                _rem_smpl = _cl.get("remainder_samples", [])

                with st.expander(f'📂 "{_cat}" — {_unres:,} פניות לבירור', expanded=True):
                    for _pg in _pgroups:
                        _q_num += 1
                        _obs    = _pg["observation"]
                        _pg_cnt = _pg["count"]
                        _smpl   = _pg.get("desc_samples", [])
                        _ctx    = _pg.get("context_sentence", "")

                        _smpl_html = ""
                        if _smpl:
                            _smpl_html = (
                                '<br><small style="color:#78716c;font-size:.79rem;">'
                                '<em>דוגמאות מתוך הפניות:</em><br>'
                                + "<br>".join(f"• {s}" for s in _smpl) + "</small>"
                            )
                        st.markdown(
                            f'<div style="background:#f8fafc;border-right:3px solid #6366f1;'
                            f'padding:.5rem .85rem;border-radius:6px;direction:rtl;margin:.45rem 0 .15rem;">'
                            f'<strong>שאלה {_q_num}/{_total_q_count}:</strong> '
                            f'{_ctx if _ctx else f"{_pg_cnt:,} פניות בקטגוריה \"{_cat}\" מזכירות \"{_obs}\""}'
                            f'{_smpl_html}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        _ans_pg = st.selectbox(
                            f'לפי התיאורים — מי גרם לבעיה? ({_pg_cnt} פניות)',
                            _RESP_OPTS, key=f"qa_rterm_{_cat}_{_obs}", help=_RESP_HELP,
                        )
                        if _ans_pg != _RESP_OPTS[0]:
                            _qa_answers[f"resp_term:{_cat}:{_obs}"] = _ans_pg

                    # Remainder — goes to manual review in Excel
                    if _remain > 0:
                        _rem_smpl_html = ""
                        if _rem_smpl:
                            _rem_smpl_html = (
                                '<br><small style="color:#78716c;font-size:.78rem;">'
                                '<em>דוגמאות:</em><br>'
                                + "<br>".join(f"• {s}" for s in _rem_smpl) + "</small>"
                            )
                        st.markdown(
                            f'<div style="background:#fafaf5;border:1px dashed #cbd5e1;'
                            f'padding:.5rem .85rem;border-radius:6px;direction:rtl;margin:.6rem 0 .2rem;">'
                            f'<strong>📎 {_remain:,} פניות נוספות</strong> — '
                            f'לא נמצאה תבנית ברורה. יסומנו לבדיקה ידנית ב-Excel.'
                            f'{_rem_smpl_html}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

        # Progress bar
        st.markdown("")
        _n_answered = len(_qa_answers)
        _pct_answered = round(_n_answered / max(_total_q_count, 1) * 100)
        st.progress(min(_pct_answered, 100) / 100,
                    text=f"📊 ענית על {_n_answered} מתוך {_total_q_count} שאלות ({_pct_answered}%)")

        _btn_label = f"✅ החל תשובות ({_n_answered} תשובות)" if _n_answered else "✅ החל תשובות"
        if st.button(_btn_label, type="primary", use_container_width=True,
                     disabled=(_n_answered == 0)):
            with st.spinner("מעבד תשובות ומעדכן נתונים..."):
                st.session_state["_df_before_qa"] = df.copy()
                _updated_df = cp.apply_user_answers(df, _qa_answers)
                st.session_state.df = _updated_df
                _ccs = st.session_state.get("_clean_stats", {}).copy()
                _ccs["conf_high"]   = int((_updated_df["_confidence"] == "high").sum()   if "_confidence" in _updated_df.columns else 0)
                _ccs["conf_medium"] = int((_updated_df["_confidence"] == "medium").sum() if "_confidence" in _updated_df.columns else 0)
                _ccs["conf_low"]    = int((_updated_df["_confidence"] == "low").sum()    if "_confidence" in _updated_df.columns else 0)
                st.session_state["_clean_stats"] = _ccs
                al.log_correction("batch", "_cluster_qa", "pending", str(list(_qa_answers.keys())), "user_qa")
                st.session_state["_qa_applied"] = True
            st.rerun()

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
                _table(_flag_breakdown(flagged, "block"))
        with col_bd2:
            if n_warn > 0:
                st.markdown("**🟡 פירוט אזהרות:**")
                _table(_flag_breakdown(flagged, "warn"))

        if _tsumm["blocking"] > 0:
            with st.expander(f"🔴 חוסמות ({_tsumm['blocking']:,})", expanded=True):
                _render_flagged_table(_triage["blocking"])
        if _tsumm["review"] > 0:
            with st.expander(f"🟡 לסקירה ({_tsumm['review']:,})", expanded=False):
                _render_flagged_table(_triage["review"])

    # ── Download review Excel ───────────────────────────────────────────────
    st.markdown('<div id="section-download"></div>', unsafe_allow_html=True)
    st.markdown("---")

    def _review_excel(df: pd.DataFrame, flagged: pd.DataFrame,
                      corr_log: pd.DataFrame) -> bytes:
        export = df.copy()
        severity    = flagged["_flag_severity"].tolist()
        flag_labels = flagged["_flag_labels"].tolist()
        conf_col    = export.get("_confidence", pd.Series([""] * len(export))).tolist() \
                      if "_confidence" in export.columns else [""] * len(export)
        det_col     = export.get("_confidence_details", pd.Series([""] * len(export))).tolist() \
                      if "_confidence_details" in export.columns else [""] * len(export)

        export.insert(0, "פירוט_החלטה",    det_col)
        export.insert(0, "רמת_ביטחון",     conf_col)
        export.insert(0, "אזהרה_בלבד",     [s == "warn"  for s in severity])
        export.insert(0, "דורש_תיקון",     [s == "block" for s in severity])
        export.insert(0, "תיאור_בעיה",     flag_labels)
        export = export.drop(columns=[c for c in export.columns if c.startswith("_")],
                             errors="ignore")

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            wb = writer.book
            fmt_hdr    = wb.add_format({"bold": True, "bg_color": "#1a3a5c",
                                        "font_color": "white", "align": "right", "border": 1})
            fmt_block  = wb.add_format({"bg_color": "#fecaca", "border": 1})
            fmt_warn   = wb.add_format({"bg_color": "#fef08a", "border": 1})
            fmt_ok     = wb.add_format({"bg_color": "#ffffff", "border": 1})
            fmt_lo     = wb.add_format({"bg_color": "#fecaca", "bold": True, "border": 1})

            # Sheet 1 — full dataset
            export.to_excel(writer, index=False, sheet_name="כל הנתונים")
            ws = writer.sheets["כל הנתונים"]
            for j, col in enumerate(export.columns):
                ws.write(0, j, col, fmt_hdr)
            for i, sev in enumerate(severity):
                row_fmt = fmt_block if sev == "block" else (fmt_warn if sev == "warn" else fmt_ok)
                ws.set_row(i + 1, None, row_fmt)
            ws.set_column(0, 0, 40); ws.set_column(1, 4, 14); ws.set_column(5, len(export.columns), 18)
            ws.freeze_panes(1, 0)

            # Sheet 2 — correction log (what changed, how, why)
            if not corr_log.empty:
                corr_log.to_excel(writer, index=False, sheet_name="תיקונים אוטומטיים")
                ws_corr = writer.sheets["תיקונים אוטומטיים"]
                for j, col in enumerate(corr_log.columns):
                    ws_corr.write(0, j, col, fmt_hdr)
                ws_corr.set_column(0, len(corr_log.columns), 18)
                ws_corr.freeze_panes(1, 0)

            # Sheet 3 — rows needing manual review
            _low_mask = [c == "low" for c in conf_col]
            if any(_low_mask):
                _low_rows = export.iloc[[i for i, m in enumerate(_low_mask) if m]]
                _low_rows.to_excel(writer, index=False, sheet_name="לבירור ידני")
                ws2 = writer.sheets["לבירור ידני"]
                for j, col in enumerate(_low_rows.columns):
                    ws2.write(0, j, col, fmt_hdr)
                for i in range(len(_low_rows)):
                    ws2.set_row(i + 1, None, fmt_lo)
                ws2.set_column(0, 0, 40); ws2.set_column(5, len(_low_rows.columns), 18)
                ws2.freeze_panes(1, 0)

            # Sheet 4 — blocking structural issues
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

            # Sheet 5 — summary
            _low_cnt  = sum(_low_mask)
            _med_cnt  = sum(c == "medium" for c in conf_col)
            _hi_cnt   = sum(c == "high"   for c in conf_col)
            pd.DataFrame([
                ("סה״כ שורות",              len(export)),
                ("סווגו ודאית",              _hi_cnt),
                ("סווגו בחלקיות",            _med_cnt),
                ("לבירור ידני",              _low_cnt),
                ("שגיאות מבניות",            n_block),
                ("אזהרות מבניות",            n_warn),
                ("תיקונים אוטומטיים",       len(corr_log)),
            ], columns=["מדד", "ערך"]).to_excel(writer, index=False, sheet_name="סיכום")
            ws4 = writer.sheets["סיכום"]
            ws4.set_column("A:A", 30); ws4.set_column("B:B", 14)
            for j, h in enumerate(["מדד", "ערך"]):
                ws4.write(0, j, h, fmt_hdr)

        return buf.getvalue()

    base = st.session_state.filename.replace(".xlsx", "")

    # Warn if Q&A questions exist but weren't answered
    if _has_questions and not st.session_state.get("_qa_applied"):
        st.markdown(
            '<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;'
            'padding:.6rem 1rem;font-size:.84rem;direction:rtl;margin-bottom:.6rem;">'
            '⚠️ <strong>יש שאלות שלא נענו למעלה.</strong> '
            'מומלץ לענות עליהן לפני ההורדה — כל תשובה מפחיתה את כמות השורות לבירור ידני.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("#### 📤 שלב הבא — הורדה ובדיקה ידנית")
    st.markdown(
        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
        f'padding:.8rem 1.1rem;font-size:.88rem;direction:rtl;margin-bottom:.8rem;">'
        f'הקובץ כולל 5 גיליונות:<br>'
        f'• <strong>כל הנתונים</strong> — כל {len(df):,} שורות, צבועות לפי רמת ביטחון<br>'
        f'• <strong>תיקונים אוטומטיים</strong> — כל תיקון שבוצע: מה שונה, לפני/אחרי, ובאיזו שיטה<br>'
        f'• <strong>לבירור ידני</strong> — {n_low:,} שורות שהמערכת לא הצליחה לסווג<br>'
        f'• <strong>דורשות תיקון</strong> — שגיאות מבניות שחוסמות המשך<br>'
        f'• <strong>סיכום</strong> — סטטיסטיקה כללית</div>',
        unsafe_allow_html=True,
    )
    _dl_col1, _dl_col2 = st.columns([3, 1])
    with _dl_col1:
        st.download_button(
            label=f"📥 הורד Excel לבדיקה — {len(df):,} שורות ({n_low:,} לבירור ידני)",
            data=_review_excel(df, flagged, _corr_log),
            file_name=f"{base}_לבדיקה.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )
    with _dl_col2:
        # Must honour the same blocking-error gate as the CTA at the bottom of
        # the stage; previously this button skipped it entirely.
        if n_block > 0:
            st.button(f"➡️ המשך לגאוקוד ({n_block:,} חוסמות)",
                      use_container_width=True, disabled=True,
                      help="יש שגיאות מבניות. תקנו אותן, או השתמשו ב\"עבור הלאה בכל זאת\" בתחתית העמוד.")
        elif st.button("➡️ המשך לגאוקוד", use_container_width=True,
                       help="לאחר שהורדת ובדקת את הקובץ — לחץ להמשיך"):
            goto("geocode")

    # ── Re-upload corrected file ────────────────────────────────────────────
    with st.expander("📤 העלה קובץ מתוקן לבדיקה חוזרת", expanded=(n_block > 0)):
        st.markdown(
            "תיקנת שורות ב-Excel? העלה כאן את **הקובץ המתוקן** (הגיליון 'כל הנתונים' או 'לבירור ידני'). "
            "המערכת תרוץ שוב על הנתונים המתוקנים ותעדכן את הסיכום."
        )
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
        flagged = _detect_flags_cached(df, DATE_MIN, DATE_MAX, "geocode")
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
        _table(zc)

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
            muni  = (d["אחריות"].isin(["עירייה", "כשל עירוני"])).mean()*100 if "אחריות" in d else 0
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
                cmap = {"עירייה":BLUE,"התנהגות אזרח":AMBER,"טבעי":GREEN,
                        "בקשה מהעירייה":GRAY,
                        # legacy
                        "כשל עירוני":BLUE,"לא רלוונטי":GRAY,"א.מ.ל":RED}
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
                _table(hot, search=True)
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
            _table(_qa_result, search=True)
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
            _table(result["per_column"].sort_values("אחוז_הסכמה"))
            with st.expander("📋 פרטי שורות שונות"):
                _table(result["diff"], search=True, max_rows=200)
        except Exception as e:
            st.error(f"שגיאה בהשוואה: {e}")
    elif ref_file is None:
        if st.session_state.get("df") is None:
            st.info("טענו קובץ נתונים לצינור לפני הפעלת מצב אימות.")
    if st.button("⬅ חזור לפלט", use_container_width=True):
        goto("output")
