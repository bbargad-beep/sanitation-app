# -*- coding: utf-8 -*-
# SYNC TEST - 2026-07-16
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
    initial_sidebar_state="collapsed",
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
    """Run clean_pipeline logic in memory, return cleaned df (no review split)."""
    rows = []
    for _, r in df_raw.iterrows():
        clean_id, suffix = cp.parse_ticket(r.get("מס' פניה", ""))
        date, hour, weekday, month = cp.parse_datetime(r.get("תאריך ושעת פתיחה"))
        orig_sub  = cp.clean_text(r.get("תת נושא"))
        if orig_sub and orig_sub in cp.CATEGORY_MAP:
            new_cat = cp.CATEGORY_MAP[orig_sub]
        elif not orig_sub:
            main_topic = cp.clean_text(r.get("נושא", ""))
            new_cat = cp.TOPIC_MAP.get(main_topic, "לא מסווג")
        else:
            new_cat = orig_sub
        substance = cp.SUBSTANCE_MAP.get(orig_sub, "לא ידוע")
        asset     = cp.ASSET_MAP.get(orig_sub, "לא ידוע")
        resp      = cp.resolve_responsibility(new_cat, r.get("תיאור", ""))
        loc = cp.parse_address(r.get("כתובת ואתר/מוסד", ""))
        rows.append({
            "מס' פניה": clean_id, "תאריך": date, "שעה": hour, "יום": weekday, "חודש": month,
            "סטטוס פנייה": r.get("סטטוס פנייה"), "נושא": r.get("נושא"),
            "תת_נושא_חדש": new_cat, "חומר": substance, "אחריות": resp, "נכס": asset,
            "רחוב_ראשי": loc["רחוב_ראשי"], "רחוב_משני": loc["רחוב_משני"],
            "מספר_בית": loc["מספר_בית"], "סוג_מיקום": loc["סוג_מיקום"],
            "תיאור": r.get("תיאור"), "הערת_מיקום": loc["הערת_מיקום"],
            "תלונה_חוזרת": None, "בקשת_חזרה": cp.detect_callback(r.get("תיאור")),
            "מידע_אישי": cp.detect_personal_info(r.get("תיאור")), "סיומת_פניה": suffix,
            "כתובת ואתר/מוסד": r.get("כתובת ואתר/מוסד"), "רחוב": loc["רחוב"],
            "הערת_כתובת": loc["הערת_כתובת"], "מחלקה": r.get("מחלקה"),
            "תת נושא מקורי": orig_sub, "מספר_חזרה": None,
        })
    out = pd.DataFrame(rows)
    out["_date"] = pd.to_datetime(out["תאריך"], errors="coerce")
    out = out.sort_values("_date").reset_index(drop=True)
    out["מספר_חזרה"] = out.groupby(["רחוב_ראשי", "מספר_בית", "תת_נושא_חדש"]).cumcount() + 1
    out["תלונה_חוזרת"] = (out["מספר_חזרה"] > 1).astype(int)
    out = out.drop(columns=["_date"])
    out["מס' פניה"] = out["מס' פניה"].astype(str).str.replace(r"\.0$", "", regex=True)
    return out


_JUNK_STREET_RE = re.compile(r"^[\d\s\.\,\-\_\!\?\(\)״׳'\"]+$")

# Raw address strings that parse_address cannot resolve to a street —
# pulled directly from geocode_pipeline.FLAG_DESCRIPTIONS and GIS_MANUAL_MAP
# (entries with value None). These should become "ציון דרך" so flags.py
# treats them as advisory (warn) rather than blocking.
_KNOWN_UNRESOLVABLE = {
    'חוף-הים', 'חוף-הים - מרינה)', 'חוף-הים -רשות החופים)',
    'חוף-הים .-רשות החופים)', 'חוף-הים 0-רשות החופים)',
    'כביש החוף בחלק של גב ים !!!', 'כביש החוף תחנת דלק פז רונית',
    'הרכבת בטיילת שליד קפה גן', 'הרכבת בעליה לגשר הולכי רגל',
    'השונית עד מלון דניאל',
    'כנפי נשרים מאלתרמן עד הבריגדה אונברסיטה',
    'כנפי נשרים מאלתרמן עד הבריגדה בכניסה לחניה של שדה התעופה',
    'שמעון לביא בגינת לביא ליד הספסל',
    'אייבי נתן מיכל המיחזור האלקטרוני',
    'משה חניון צחי',
    'כיכר הציונות',
    'אלט נויילנד',
    'חיים גרשון',
    'רפי וקנין',
    'חוף הים',
    'חוף ים',
}

# Raw address prefixes/substrings that reliably indicate a non-street location.
# These are matched against the raw כתובת ואתר/מוסד column only when
# רחוב_ראשי comes out blank or as pure junk — never applied to rows that
# already have a real parsed street.
_DESCRIPTIVE_PREFIXES = (
    'חוף', 'פארק ', 'גן הגאולה', 'גן העירוני', 'גן לאומי', 'שמורת',
    'טיילת', 'מרינה', 'שפת הים', 'חניון ', 'מגרש משחקים', 'גינת',
)


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
    df = df.copy()

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


def excel_bytes(df: pd.DataFrame, stats: dict) -> bytes:
    """Single Excel output: color-flagged data sheet + Hebrew summary sheet."""
    df = df.copy()
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
    return buf.getvalue()


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
                st.dataframe(df_raw.head(5), use_container_width=True)
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
#  STAGE 2 — CLEAN (review via download + gate)
# ══════════════════════════════════════════════════════════════════════════

elif stage == "clean":
    df = st.session_state.df
    flagged = fl.detect_flags(df, DATE_MIN, DATE_MAX, stage="clean")
    n_block = fl.count_blocking(flagged)
    n_warn  = fl.count_warnings(flagged)
    n_clean = len(df) - n_block - n_warn

    st.markdown("### שלב 2 — בדיקת ניקוי")

    st.markdown(f"""
    <div class="stat-row">
      <div class="stat-card good"><div class="num">{n_clean:,}</div><div class="lbl">שורות תקינות</div></div>
      <div class="stat-card alert"><div class="num">{n_block:,}</div><div class="lbl">דורשות תיקון</div></div>
      <div class="stat-card warn"><div class="num">{n_warn:,}</div><div class="lbl">אזהרות בלבד</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Flag breakdown ──────────────────────────────────────────────────────
    col_bd1, col_bd2 = st.columns(2)
    with col_bd1:
        if n_block > 0:
            breakdown_b = _flag_breakdown(flagged, "block")
            st.markdown("**🔴 פירוט בעיות חוסמות:**")
            st.dataframe(breakdown_b, use_container_width=True, hide_index=True)
    with col_bd2:
        if n_warn > 0:
            breakdown_w = _flag_breakdown(flagged, "warn")
            st.markdown("**🟡 פירוט אזהרות:**")
            st.dataframe(breakdown_w, use_container_width=True, hide_index=True)

    # ── Download-first review Excel ─────────────────────────────────────────
    st.markdown('<div class="step-card"><h4>קובץ לבדיקה ידנית</h4>'
                '<p>הורידו את הקובץ לעיון ותיקון ב-Excel. '
                'כל שורה מסומנת בעמודות בוליאניות (<strong>דורש_תיקון</strong> / <strong>אזהרה_בלבד</strong>) '
                'ובצבע שורה (אדום / צהוב). '
                'לאחר תיקון ידני של השורות החוסמות בקובץ המקורי, העלו מחדש.</p></div>',
                unsafe_allow_html=True)

    # Build review Excel with boolean columns + row coloring
    def _review_excel(df: pd.DataFrame, flagged: pd.DataFrame) -> bytes:
        export = df.copy()
        severity   = flagged["_flag_severity"].tolist()
        flag_labels = flagged["_flag_labels"].tolist()

        # Boolean flag columns — added FIRST so they're visible immediately
        export.insert(0, "אזהרה_בלבד",   [s == "warn"  for s in severity])
        export.insert(0, "דורש_תיקון",   [s == "block" for s in severity])
        export.insert(0, "תיאור_בעיה",   flag_labels)

        # Drop internal cols
        export = export.drop(columns=[c for c in export.columns if c.startswith("_")],
                             errors="ignore")

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            wb = writer.book
            fmt_hdr   = wb.add_format({"bold": True, "bg_color": "#1a3a5c",
                                       "font_color": "white", "align": "right",
                                       "border": 1})
            fmt_block = wb.add_format({"bg_color": "#fecaca", "border": 1})  # red-200
            fmt_warn  = wb.add_format({"bg_color": "#fef08a", "border": 1})  # yellow-200
            fmt_ok    = wb.add_format({"bg_color": "#ffffff", "border": 1})
            fmt_bool_t = wb.add_format({"bg_color": "#fecaca", "bold": True,
                                        "align": "center", "border": 1})
            fmt_bool_f = wb.add_format({"bg_color": "#dcfce7", "bold": True,
                                        "align": "center", "border": 1})

            # ── Sheet 1: All data with flags ──────────────────────────────
            export.to_excel(writer, index=False, sheet_name="כל הנתונים")
            ws = writer.sheets["כל הנתונים"]
            ncols = len(export.columns)

            # Header row
            for j, col in enumerate(export.columns):
                ws.write(0, j, col, fmt_hdr)

            # Row coloring + boolean cell formatting
            for i, sev in enumerate(severity):
                row_fmt = fmt_block if sev == "block" else (fmt_warn if sev == "warn" else fmt_ok)
                ws.set_row(i + 1, None, row_fmt)
                # Color the boolean columns explicitly
                ws.write(i + 1, 0, flag_labels[i])           # תיאור_בעיה
                ws.write(i + 1, 1, sev == "block",           # דורש_תיקון
                         fmt_bool_t if sev == "block" else fmt_bool_f)
                ws.write(i + 1, 2, sev == "warn",            # אזהרה_בלבד
                         fmt_bool_t if sev == "warn" else fmt_bool_f)

            # Column widths
            ws.set_column(0, 0, 40)   # תיאור_בעיה
            ws.set_column(1, 2, 14)   # boolean cols
            ws.set_column(3, ncols, 18)
            ws.freeze_panes(1, 0)

            # ── Sheet 2: Blocking rows only ───────────────────────────────
            block_rows = export[[s == "block" for s in severity]]
            block_sev  = [s for s in severity if s == "block"]
            if not block_rows.empty:
                block_rows.to_excel(writer, index=False, sheet_name="דורשות תיקון")
                ws2 = writer.sheets["דורשות תיקון"]
                for j, col in enumerate(block_rows.columns):
                    ws2.write(0, j, col, fmt_hdr)
                for i in range(len(block_rows)):
                    ws2.set_row(i + 1, None, fmt_block)
                ws2.set_column(0, 0, 40)
                ws2.set_column(1, 2, 14)
                ws2.set_column(3, len(block_rows.columns), 18)
                ws2.freeze_panes(1, 0)

            # ── Sheet 3: Summary ──────────────────────────────────────────
            summary_rows = [
                ("סה״כ שורות",           len(df)),
                ("שורות תקינות",          n_clean),
                ("דורשות תיקון (חוסמות)", n_block),
                ("אזהרות בלבד",           n_warn),
            ]
            pd.DataFrame(summary_rows, columns=["מדד", "ערך"]).to_excel(
                writer, index=False, sheet_name="סיכום")
            ws3 = writer.sheets["סיכום"]
            ws3.set_column("A:A", 30)
            ws3.set_column("B:B", 14)
            for j, h in enumerate(["מדד", "ערך"]):
                ws3.write(0, j, h, fmt_hdr)

        return buf.getvalue()

    review_bytes = _review_excel(df, flagged)
    base = st.session_state.filename.replace(".xlsx", "")
    st.download_button(
        label=f"📥 הורד קובץ לבדיקה ({len(df):,} שורות | {n_block:,} חוסמות | {n_warn:,} אזהרות)",
        data=review_bytes,
        file_name=f"{base}_לבדיקה.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.divider()

    # ── Re-upload corrected file ────────────────────────────────────────────
    with st.expander("📤 העלה קובץ מתוקן לבדיקה חוזרת", expanded=(n_block > 0)):
        st.markdown("לאחר תיקון ידני ב-Excel — העלו כאן את הקובץ המקורי המתוקן (לא קובץ הבדיקה) לבדיקה חוזרת.")
        reupload = st.file_uploader("קובץ מתוקן (.xlsx)", type=["xlsx"],
                                     key="reupload", label_visibility="collapsed")
        if reupload:
            try:
                df_fixed = pd.read_excel(reupload)
                # Drop any review columns if worker accidentally re-uploaded the review file
                df_fixed = df_fixed.drop(columns=['תיאור_בעיה','דורש_תיקון','אזהרה_בלבד'],
                                          errors='ignore')
                with st.spinner("מנקה ובודק שוב..."):
                    df_fixed = run_clean_in_memory(df_fixed)
                    df_fixed = auto_fix(df_fixed)
                flagged_new = fl.detect_flags(df_fixed, DATE_MIN, DATE_MAX, stage="clean")
                nb_new = fl.count_blocking(flagged_new)
                nw_new = fl.count_warnings(flagged_new)
                st.markdown(f'<div class="banner-success">✅ קובץ מתוקן נטען: '
                            f'<strong>{nb_new}</strong> חוסמות, <strong>{nw_new}</strong> אזהרות</div>',
                            unsafe_allow_html=True)
                if st.button("✅ אמץ קובץ מתוקן זה", type="primary", use_container_width=True):
                    st.session_state.df = df_fixed
                    st.session_state.filename = reupload.name
                    st.rerun()
            except Exception as e:
                st.markdown(f'<div class="banner-error">❌ שגיאה: {e}</div>',
                            unsafe_allow_html=True)

    if n_block > 0:
        st.markdown(
            f'<div class="banner-warn">⚠️ נותרו <strong>{n_block:,}</strong> שורות חוסמות. '
            f'הורידו את קובץ הבדיקה, תקנו את הגיליון <strong>"דורשות תיקון"</strong> '
            f'בקובץ המקורי, והעלו מחדש למעלה. '
            f'לחלופין — לחצו "המשך בכל זאת" אם הבעיות ידועות ואינן מונעות גאוקוד.</div>',
            unsafe_allow_html=True)

    cta1, cta2, cta3 = st.columns([1, 1, 1])
    with cta1:
        if st.button("⬅ חזור להעלאה", use_container_width=True):
            st.session_state.df = None
            goto("upload")
    with cta2:
        if n_block == 0:
            if st.button("▶ המשך לגאוקוד", type="primary", use_container_width=True):
                goto("geocode")
        else:
            st.button(f"▶ המשך לגאוקוד ✓", type="primary",
                      disabled=True, use_container_width=True)
    with cta3:
        if n_block > 0:
            if st.button("▶ המשך בכל זאת (התעלם מחוסמות)", use_container_width=True):
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
            st.markdown(
                f'<div class="banner-warn">⚠️ נמצא קובץ המשך מריצה קודמת — '
                f'<strong>{rows_done:,}</strong> שורות כבר גאוקודדו. '
                f'לחצו "המשך" להמשך מאותה נקודה, או "התחל מחדש" למחיקת ההתקדמות.</div>',
                unsafe_allow_html=True,
            )
            cr1, cr2 = st.columns(2)
            with cr1:
                if st.button("▶ המשך מנקודת עצירה", type="primary", use_container_width=True):
                    st.session_state.df = checkpoint
                    _clear_checkpoint(st.session_state.filename)
                    st.rerun()
            with cr2:
                if st.button("🗑️ התחל מחדש", use_container_width=True):
                    _clear_checkpoint(st.session_state.filename)
                    st.rerun()
        else:
            already = ("קו_רוחב" in df.columns and df["קו_רוחב"].notna().any())
            if already:
                st.markdown('<div class="banner-warn">⚠️ חלק מהשורות כבר מכילות קואורדינטות — '
                            'הגאוקוד ירוץ רק על שורות חסרות.</div>', unsafe_allow_html=True)

            if st.button("▶ הרץ גאוקוד", type="primary", use_container_width=True):
                prog = st.progress(0.0, text="מתחיל גאוקוד...")
                _checkpoint_counter = [0]
                _df_ref = [df]  # mutable container so cb can access the live df

                def cb(pass_name, current, total, geocoded, failed):
                    if total > 0:
                        names = {"nominatim": "Nominatim", "gis": "פורטל GIS", "status": "מכין"}
                        label = names.get(pass_name, pass_name)
                        prog.progress(min(current / total, 1.0),
                                      text=f"{label}: {current:,}/{total:,} — נפתרו {geocoded:,}")
                        # Save checkpoint every 50 rows
                        _checkpoint_counter[0] += 1
                        if _checkpoint_counter[0] % 50 == 0:
                            _save_checkpoint(_df_ref[0], st.session_state.filename)

                df_geo, gstats = gp.geocode_dataframe(df, progress_cb=cb)
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
                if st.button("▶ המשך בכל זאת (התעלם מחוסמות)", use_container_width=True):
                    goto("enrich")


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 4 — ENRICH (zones + gate)
# ══════════════════════════════════════════════════════════════════════════

elif stage == "enrich":
    df = st.session_state.df
    st.markdown("### שלב 4 — העשרה (שיוך רובעי פינוי)")

    if not st.session_state.enriched:
        st.markdown('<div class="step-card"><h4>מה קורה כאן?</h4><p>כל פנייה משויכת לרובע פינוי '
                    'לפי הקואורדינטות שלה, ומקבלת את יום הפינוי של אותו רובע. בנוסף מסומן אם '
                    'התלונה הוגשה ביום הפינוי עצמו.</p></div>', unsafe_allow_html=True)
        if st.button("▶ הרץ העשרה", type="primary", use_container_width=True):
            with st.spinner("משייך רובעים..."):
                df_en, estats = ep.enrich_dataframe(df)
                st.session_state.df = df_en
                st.session_state.enriched = True
                st.session_state.stats.update({
                    "in_city": estats["in_city"],
                    "same_day": estats["same_day"],
                    "same_day_pct": f"{estats['same_day_pct']}%",
                })
                _save_state()
            st.rerun()
    else:
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
        st.dataframe(zc, use_container_width=True, hide_index=True)

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

    tab_map, tab_analytics, tab_download = st.tabs(["🗺️ מפת חום", "📈 ניתוח", "⬇️ הורדה"])

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
                st.dataframe(hot, use_container_width=True, hide_index=True)
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
