# -*- coding: utf-8 -*-
# ============================================================================
#  clean_pipeline.py
#  עיריית הרצליה — ניקוי וארגון נתוני פניות מוקד תברואה
#  Herzliya Municipality — Sanitation Complaints Cleaning Pipeline
# ============================================================================
#
#  WHAT THIS DOES
#  --------------
#  Takes a raw CRM 360 export (8 columns) and transforms it into the
#  structured analytical dataset (27 columns) used for analysis.
#
#  It automates every SYSTEMATIC rule developed during manual cleaning:
#    • Ticket-ID cleanup + suffix extraction
#    • Date/time split (date, hour, weekday, month)
#    • Category consolidation (38 sub-topics -> 16 analytical categories)
#    • Dimension columns: substance / responsibility / asset
#    • Address parsing -> street, secondary street, house number, location type
#    • Free-text signal flags (callback request, personal info)
#    • Recurring-complaint detection (structural method)
#
#  HOW TO RUN
#  ----------
#    1. Put this file in the same folder as the raw export.
#    2. Edit INPUT_FILE below to match the raw file name.
#    3. Run:  python clean_pipeline.py
#    4. Output: <name>_מנוקה.xlsx  +  a review file flagging rows
#       that need human attention.
#
#  IMPORTANT — WHAT STILL NEEDS A HUMAN (documented, not hidden):
#    • Street CANONICALIZATION against the official Herzliya street list
#      (this script fills רחוב_ראשי with the raw parsed street; matching it
#       to the official list is a separate step).
#    • Special location types (אזור חוף / מרחב ציבורי / ללא רחוב) — the script
#      assigns the best automatic guess; confirm manually.
#    • Ambiguous responsibility (משטח מלוכלך / כלי אצירה פגומים / פח נעלם)
#      default to א.מ.ל ("unknown"); refine from the free text if needed.
#  These rows are written to a separate review file so nothing is silently wrong.
# ============================================================================

import pandas as pd
import numpy as np
import re
import os

# ----------------------------------------------------------------------------
# CONFIGURATION — edit the input file name to match your raw export
# ----------------------------------------------------------------------------
INPUT_FILE = "דוח_תברואה_לשנת_2026_-_ORIGINAL_COPY.xlsx"

# ============================================================================
#  LOOKUP TABLES  (extracted from the verified cleaned dataset)
# ============================================================================

# --- 1) Category consolidation: original sub-topic  ->  analytical category --
CATEGORY_MAP = {
    "אי פינוי אשפה ביתית": "אי פינוי",
    "אי פינוי גזם": "אי פינוי",
    "אי פינוי מכולה": "אי פינוי",
    "גזם עירוני שלא פונה": "אי פינוי",
    "פח אשפה שלא הוחזר": "תלונה על ביצוע הפינוי",
    "אשפה מפוזרת לאחר פינוי ": "תלונה על ביצוע הפינוי",
    "איסוף אשפה בשעה מוקדמת": "תלונה על ביצוע הפינוי",
    "רחוב מלוכלך": "משטח מלוכלך",
    "מדרכה מלוכלכת": "משטח מלוכלך",
    "מגרש מלוכלך": "משטח מלוכלך",
    "ניקיון מקלטים": "משטח מלוכלך",
    "שירותים ציבוריים": "משטח מלוכלך",
    "ערמת פסולת": "פסולת לא מורשית",
    "אשפה מפוזרת": "פסולת לא מורשית",
    "פסולת חריגה - זכוכיות": "פסולת לא מורשית",
    "פסולת חריגה": "פסולת לא מורשית",
    "ערמת קרטונים": "פסולת לא מורשית",
    "בור גזם": "פסולת לא מורשית",
    "כלי אצירה פגומים": "כלי אצירה פגומים",
    "תקלה בטמוני קרקע": "כלי אצירה פגומים",
    "אשפתון מלא": "כלי אצירה מלא",
    "טמוני קרקע מלאים": "כלי אצירה מלא",
    "מיכל אשפה עילי מלא": "כלי אצירה מלא",
    "פגר חתול": "פגר",
    "פגר בעלי כנף": "פגר",
    "פגר עכבר/קיפוד": "פגר",
    "פגר חיה": "פגר",
    "פח שנעלם": "פח נעלם",
    "שקיות איסוף צואת כלבים": "בקשת ציוד ציבורי",
    "צואת כלבים": "צואת כלבים",
    "עשבים במדרכה": "פלישת צומח",
    "גראפיטי": "גראפיטי",
    "סחף אדמה": "סחף אדמה",
    "פינוי אשפה חריג": "בקשה מיוחדת לפינוי",
    "פינוי פח 3700": "בקשה מיוחדת לפינוי",
    "פינוי אשפה בבית חדש": "בקשה מיוחדת לפינוי",
    "ריקון אשפה לפחים אחרים": "בקשה מיוחדת לפינוי",
    "טופס דיווח על גרימת נזק בשל פינוי אשפה": "תביעת נזק",
}

# --- 2) Substance: original sub-topic  ->  substance dimension ---------------
SUBSTANCE_MAP = {
    "אי פינוי אשפה ביתית": "אשפה ביתית",
    "אי פינוי גזם": "גזם",
    "אי פינוי מכולה": "פסולת גושית",
    "איסוף אשפה בשעה מוקדמת": "אשפה ביתית",
    "אשפה מפוזרת": "אשפה ביתית",
    "אשפה מפוזרת לאחר פינוי ": "אשפה ביתית",
    "אשפתון מלא": "אשפה ביתית",
    "בור גזם": "גזם",
    "גזם עירוני שלא פונה": "גזם",
    "גראפיטי": "לא רלוונטי",
    "טופס דיווח על גרימת נזק בשל פינוי אשפה": "לא רלוונטי",
    "טמוני קרקע מלאים": "אשפה ביתית",
    "כלי אצירה פגומים": "לא רלוונטי",
    "מגרש מלוכלך": "כללי",
    "מדרכה מלוכלכת": "כללי",
    "מיכל אשפה עילי מלא": "אשפה ביתית",
    "ניקיון מקלטים": "כללי",
    "סחף אדמה": "לא רלוונטי",
    "ערמת פסולת": "כללי",
    "ערמת קרטונים": "קרטונים",
    "עשבים במדרכה": "לא רלוונטי",
    "פגר בעלי כנף": "עוף",
    "פגר חיה": "חיה",
    "פגר חתול": "חתול",
    "פגר עכבר/קיפוד": "מכרסם",
    "פח אשפה שלא הוחזר": "אשפה ביתית",
    "פח שנעלם": "לא רלוונטי",
    "פינוי אשפה בבית חדש": "אשפה ביתית",
    "פינוי אשפה חריג": "אשפה ביתית",
    "פינוי פח 3700": "אשפה ביתית",
    "פסולת חריגה": "פסולת גושית",
    "פסולת חריגה - זכוכיות": "זכוכית",
    "צואת כלבים": "צואת כלבים",
    "רחוב מלוכלך": "כללי",
    "ריקון אשפה לפחים אחרים": "אשפה ביתית",
    "שירותים ציבוריים": "כללי",
    "שקיות איסוף צואת כלבים": "לא רלוונטי",
    "תקלה בטמוני קרקע": "לא רלוונטי",
}

# --- 3) Asset: original sub-topic  ->  affected asset dimension --------------
ASSET_MAP = {
    "אי פינוי אשפה ביתית": "פח",
    "אי פינוי גזם": "לא ידוע",
    "אי פינוי מכולה": "מכולה",
    "איסוף אשפה בשעה מוקדמת": "לא ידוע",
    "אשפה מפוזרת": "רחוב",
    "אשפה מפוזרת לאחר פינוי ": "רחוב",
    "אשפתון מלא": "אשפתון ציבורי",
    "בור גזם": "לא ידוע",
    "גזם עירוני שלא פונה": "לא ידוע",
    "גראפיטי": "לא ידוע",
    "טופס דיווח על גרימת נזק בשל פינוי אשפה": "לא ידוע",
    "טמוני קרקע מלאים": "טמון קרקע",
    "כלי אצירה פגומים": "פח",
    "מגרש מלוכלך": "מגרש",
    "מדרכה מלוכלכת": "מדרכה",
    "מיכל אשפה עילי מלא": "מיכל עילי",
    "ניקיון מקלטים": "מקלט",
    "סחף אדמה": "מדרכה",
    "ערמת פסולת": "רחוב",
    "ערמת קרטונים": "רחוב",
    "עשבים במדרכה": "מדרכה",
    "פגר בעלי כנף": "רחוב",
    "פגר חיה": "רחוב",
    "פגר חתול": "רחוב",
    "פגר עכבר/קיפוד": "רחוב",
    "פח אשפה שלא הוחזר": "פח",
    "פח שנעלם": "פח",
    "פינוי אשפה בבית חדש": "לא ידוע",
    "פינוי אשפה חריג": "לא ידוע",
    "פינוי פח 3700": "פח",
    "פסולת חריגה": "רחוב",
    "פסולת חריגה - זכוכיות": "רחוב",
    "צואת כלבים": "מדרכה",
    "רחוב מלוכלך": "רחוב",
    "ריקון אשפה לפחים אחרים": "פח",
    "שירותים ציבוריים": "שירותים ציבוריים",
    "תקלה בטמוני קרקע": "טמון קרקע",
}

# --- 4) Responsibility: analytical category -> responsibility dimension ------
# Ambiguous categories are intentionally set to א.מ.ל ("unknown") because the
# true responsibility can only be told from the free text (refine manually).
RESPONSIBILITY_MAP = {
    "אי פינוי": "כשל עירוני",
    "תלונה על ביצוע הפינוי": "כשל עירוני",
    "כלי אצירה מלא": "כשל עירוני",
    "כלי אצירה פגומים": "א.מ.ל",   # ambiguous -> unknown
    "תביעת נזק": "כשל עירוני",
    "משטח מלוכלך": "א.מ.ל",        # ambiguous -> unknown
    "פח נעלם": "א.מ.ל",            # ambiguous -> unknown
    "פסולת לא מורשית": "התנהגות אזרח",
    "צואת כלבים": "התנהגות אזרח",
    "גראפיטי": "התנהגות אזרח",
    "פגר": "טבעי",
    "סחף אדמה": "טבעי",
    "פלישת צומח": "טבעי",
    "בקשה מיוחדת לפינוי": "לא רלוונטי",
    "בקשת ציוד ציבורי": "לא רלוונטי",
}

# Keywords for smart responsibility resolution of א.מ.ל categories.
# If תיאור contains any keyword in a group, the responsibility is assigned.
_RESP_KEYWORDS = {
    "כשל עירוני": [
        # Collection crew damaged/lost the bin
        "שברו", "שבור", "דרסו", "נשבר", "החזירו", "לא החזירו", "הוחזר",
        "לא הוחזר", "לקחו", "נלקח", "נעלם אחרי פינוי", "נעלם לאחר פינוי",
        "היום בפינוי", "אחרי הפינוי", "לאחר הפינוי", "בפינוי",
        # Street cleaning crew failure
        "מנקה רחובות", "אוטו ניקוי", "לא ניקו", "לא עברו עם", "לא עבר מנקה",
        "השאיר זבל", "השאיר ערמת", "מטאטא", "מפוח", "לא ניקה",
        # General municipal failure
        "כבר שבועיים", "כבר שבועות", "כבר ימים", "הזנחה", "לא טופל",
    ],
    "התנהגות אזרח": [
        "פיזרו", "זרקו", "אנשים", "שכנים", "דיירים", "מישהו",
        "גנבו", "גנב", "נגנב", "עקרו", "פרצו",
        # Pet waste — the owner is responsible, not "nature"
        "כלב", "כלבים", "צואת כלבים", "בעל הכלב", "בעלי כלבים", "צואת כלב",
    ],
    "טבעי": [
        "גשם", "רוח", "עלים", "שלכת", "ענפים", "שיטפון",
        "חצץ שזורם", "סחף", "עצים נפלו",
        # Wild bird/animal waste — dirty surfaces caused by nature, not humans
        "יונים", "יונה", "ציפורים", "ציפור", "עורב", "עורבים",
        "צואת יונים", "צואת ציפורים", "בעלי כנף", "פרחים נשרו",
        "חתולים", "חתול",
    ],
}


def resolve_responsibility(category: str, description: str) -> str:
    """
    For א.מ.ל categories, attempt to resolve responsibility from תיאור keywords.
    Returns the resolved responsibility or א.מ.ל if unresolvable.
    """
    base = RESPONSIBILITY_MAP.get(category, "א.מ.ל")
    if base != "א.מ.ל":
        return base
    if not description or pd.isna(description):
        return "א.מ.ל"
    text = str(description)
    for resp, keywords in _RESP_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return resp
    return "א.מ.ל"

# --- 5) Weekday number (Mon=0) -> Hebrew day name ---------------------------
# Fallback: main topic → analytical category when sub-topic is blank in CRM export
TOPIC_MAP = {
    "פינוי אשפה":             "אי פינוי",
    "פינוי גזם ופסולת גושית":  "אי פינוי",
    "תקלות בכלי אצירה":       "כלי אצירה פגומים",
    "פינוי פגר":              "פגר",
    "ניקיון":                 "משטח מלוכלך",
}
TOPIC_MAP = {k.strip(): v for k, v in TOPIC_MAP.items()}

WEEKDAY_MAP = {0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי",
               4: "שישי", 5: "שבת", 6: "ראשון"}

# Normalize all lookup keys (strip stray whitespace) so a trailing space in the
# raw export — e.g. "אשפה מפוזרת לאחר פינוי " — still matches correctly.
CATEGORY_MAP   = {k.strip(): v for k, v in CATEGORY_MAP.items()}
SUBSTANCE_MAP  = {k.strip(): v for k, v in SUBSTANCE_MAP.items()}
ASSET_MAP      = {k.strip(): v for k, v in ASSET_MAP.items()}

# --- Keyword signals for the callback-request flag (בקשת_חזרה) --------------
CALLBACK_KEYWORDS = [
    "שיצרו איתה קשר", "שיצרו איתו קשר", "שיצרו קשר", "מבקש שיצרו",
    "מבקשת שיצרו", "שיתקשרו", "שיחזרו אלי", "שיחזרו אליה", "שיחזרו אליו",
    "לחזור אלי", "מבקש שיחזרו", "מבקשת שיחזרו", "ליצור קשר", "צרו קשר",
]

# ============================================================================
#  HELPER FUNCTIONS
# ============================================================================

def clean_text(s):
    """Decode common HTML entities and trim whitespace."""
    if pd.isna(s):
        return ""
    s = str(s)
    s = s.replace("&#039;", "'").replace("&quot;", '"').replace("&amp;", "&")
    s = s.replace("&#39;", "'").replace("&gt;", ">").replace("&lt;", "<")
    return s.strip()


def parse_ticket(value):
    """'  2178241-ב' -> ('2178241', 'ב').  Returns (clean_id, suffix_or_None)."""
    s = str(value).strip()
    m = re.search(r"-\s*([א-ת])\s*$", s)
    suffix = m.group(1) if m else None
    clean_id = re.match(r"\s*(\d+)", s)
    clean_id = clean_id.group(1) if clean_id else s
    return clean_id, suffix


def parse_datetime(value):
    """Split the opening timestamp into date / hour / weekday / month."""
    if pd.isna(value):
        return None, None, None, None
    dt = pd.to_datetime(value)
    return (dt.strftime("%Y-%m-%d"),
            int(dt.hour),
            WEEKDAY_MAP[dt.weekday()],
            int(dt.month))


def parse_address(raw):
    """
    Parse the free-text address column into structured parts.
    Returns a dict with the structured location fields.

    Location types produced automatically:
       כתובת      = street + house number
       צומת       = intersection (two streets)
       טווח בתים  = a range of house numbers
       ציון דרך   = landmark / no clear house number
    (אזור חוף / מרחב ציבורי / ללא רחוב require manual confirmation.)
    """
    out = {"רחוב_ראשי": None, "רחוב_משני": None, "מספר_בית": None,
           "סוג_מיקום": None, "הערת_מיקום": None, "הערת_כתובת": None,
           "רחוב": None, "_needs_review": False}

    addr = clean_text(raw)
    out["רחוב"] = addr
    if not addr:
        out["סוג_מיקום"] = "ללא רחוב"
        out["_needs_review"] = True
        return out

    # 1) pull out a parenthetical note, e.g. "(גן הגאולה)"
    paren = re.search(r"\(([^)]*)\)", addr)
    if paren:
        out["הערת_כתובת"] = "(" + paren.group(1).strip() + ")"
        addr = (addr[:paren.start()] + " " + addr[paren.end():]).strip()

    # 2) intersection markers: פינת / פינה / פ' / פ.
    inter = re.split(r"\s+(?:פינת|פינה|פ['\.])\s*", addr, maxsplit=1)
    if len(inter) == 2 and inter[1].strip():
        out["רחוב_ראשי"] = inter[0].strip()
        out["רחוב_משני"] = inter[1].strip()
        out["סוג_מיקום"] = "צומת"
        return out

    # 3) range of house numbers, e.g. "הגבורה 8-12"
    rng = re.match(r"^(.+?)\s+(\d+\s*[-–]\s*\d+)\s*$", addr)
    if rng:
        nums = re.sub(r"\s*", "", rng.group(2))
        out["רחוב_ראשי"] = rng.group(1).strip()
        out["מספר_בית"] = nums
        out["הערת_מיקום"] = "בתים: " + nums
        out["סוג_מיקום"] = "טווח בתים"
        return out

    # ── Directional suffix stripping ──────────────────────────────────────
    # Many CRM addresses append navigation text after the real street name,
    # e.g. "גיבורי עציון ליד בית פוסטר", "זבוטינסקי בין הנדיב לאלתרמן".
    # We strip these suffixes to get the canonical street name for geocoding,
    # storing the full original in הערת_מיקום for human context.
    _DIR_PATTERN = re.compile(
        r"\s+(?:"
        r"ליד\b|מול\b|סמוך\s+ל|בין\b|לכיוון\b|לכיון\b|בכיוון\b"
        r"|עד\b|לפני\b|אחרי\b|מאחורי\b|מעבר\s+ל|מול\s+ה"
        r"|בכניסה\s+ל|ממול\b|בסמוך\b|ברחבת\b|בגינת\b"
        r"|ליד\s+ה|מול\s+בית|בצד\b|בקרבת\b|בפינת\b"
        r"|מתחת\s+ל|מעל\b|בצמוד\s+ל|בין\s+ה|ב?כיכר\b"
        r"|עד\s+סוף|מהבריגדה\b|לאורך\b|בחלק\b"
        r")",
        re.UNICODE
    )
    dir_match = _DIR_PATTERN.search(addr)
    if dir_match:
        canonical = addr[:dir_match.start()].strip()
        direction_note = addr[dir_match.start():].strip()
        if canonical:
            addr = canonical
            if direction_note:
                out["הערת_מיקום"] = (out["הערת_מיקום"] or "") + " | " + direction_note
                out["הערת_מיקום"] = out["הערת_מיקום"].strip(" | ")

    # 4) standard "street number"
    std = re.match(r"^(.+?)\s+(\d+)\s*$", addr)
    if std:
        out["רחוב_ראשי"] = std.group(1).strip()
        out["מספר_בית"] = std.group(2)
        out["סוג_מיקום"] = "כתובת"
        return out

    # 4b) street + number + Hebrew building suffix, e.g. "הרב קוק 43א" / "בני בנימין 9ב"
    #     / "פורצי הדרך 49 ג'" / "הפועל 61 ב'" — suffix is a distinct building label
    apt = re.match(r"^(.+?)\s+(\d+)\s*([א-ת]{1,2}[\'\u05f3]?)\s*$", addr)
    if apt:
        out["רחוב_ראשי"] = apt.group(1).strip()
        out["מספר_בית"] = apt.group(2) + apt.group(3).rstrip("\'")  # e.g. "43א"
        out["סוג_מיקום"] = "כתובת"
        return out

    # 4c) street + number range with + or & separator, e.g. "בן שלום 9+11"
    multi = re.match(r"^(.+?)\s+(\d+\s*[+&]\s*\d+)\s*$", addr)
    if multi:
        out["רחוב_ראשי"] = multi.group(1).strip()
        out["מספר_בית"] = multi.group(2).replace(" ", "")
        out["סוג_מיקום"] = "טווח בתים"
        return out

    # 5) no resolvable house number -> treat as landmark
    out["רחוב_ראשי"] = addr.strip()
    out["סוג_מיקום"] = "ציון דרך"
    out["_needs_review"] = True
    return out


def detect_callback(desc):
    """1 if the description asks the municipality to call the resident back."""
    if pd.isna(desc):
        return 0
    text = str(desc)
    return int(any(kw in text for kw in CALLBACK_KEYWORDS))


def detect_personal_info(desc):
    """1 if the description contains a phone number (05X-XXXXXXX style)."""
    if pd.isna(desc):
        return 0
    return int(bool(re.search(r"05\d[-\s]?\d{6,7}", str(desc))))


# ============================================================================
#  MAIN PIPELINE
# ============================================================================

def clean_dataframe(df_raw: pd.DataFrame) -> tuple:
    """
    Clean a raw CRM 360 export DataFrame into the structured analytical dataset.

    This is the single authoritative clean path — both the app and the CLI
    use this function. Returns (df_clean, stats).

    Provenance columns added:
      סיווג_מקור    — how the category was determined (map / topic_fallback / passthrough)
      אחריות_מקור   — how responsibility was determined (map / keyword:<resp> / unresolved)
      מסלול_כתובת   — which address-parsing branch matched (intersection / range / std /
                      apt_suffix / multi / landmark / empty)
    """
    rows = []
    for _, r in df_raw.iterrows():
        clean_id, suffix = parse_ticket(r.get("מס' פניה", ""))
        date, hour, weekday, month = parse_datetime(r.get("תאריך ושעת פתיחה"))

        orig_sub = clean_text(r.get("תת נושא"))

        # Category classification with provenance
        if orig_sub and orig_sub in CATEGORY_MAP:
            new_cat = CATEGORY_MAP[orig_sub]
            cat_source = "map"
        elif not orig_sub:
            main_topic = clean_text(r.get("נושא", ""))
            new_cat = TOPIC_MAP.get(main_topic, "לא מסווג")
            cat_source = "topic_fallback"
        else:
            new_cat = orig_sub
            cat_source = "passthrough"

        substance = SUBSTANCE_MAP.get(orig_sub, "לא ידוע")
        asset = ASSET_MAP.get(orig_sub, "לא ידוע")

        # Responsibility with keyword resolution and provenance
        resp = resolve_responsibility(new_cat, r.get("תיאור", ""))
        base_resp = RESPONSIBILITY_MAP.get(new_cat, "א.מ.ל")
        if base_resp != "א.מ.ל":
            resp_source = "map"
        elif resp != "א.מ.ל":
            resp_source = f"keyword:{resp}"
        else:
            resp_source = "unresolved"

        # Address parsing with route provenance
        loc = parse_address(r.get("כתובת ואתר/מוסד", ""))
        loc_type = loc["סוג_מיקום"] or ""
        if loc_type == "צומת":
            addr_route = "intersection"
        elif loc_type == "טווח בתים":
            addr_route = "range"
        elif loc_type == "כתובת" and loc["מספר_בית"]:
            # Check if it's an apt-suffix or multi match
            raw_addr = clean_text(r.get("כתובת ואתר/מוסד", ""))
            if re.search(r"\d+\s*[+&]\s*\d+\s*$", raw_addr):
                addr_route = "multi"
            elif re.search(r"\d+\s*[א-ת]{1,2}[\'׳]?\s*$", raw_addr):
                addr_route = "apt_suffix"
            else:
                addr_route = "std"
        elif loc_type in ("ציון דרך", ""):
            addr_route = "landmark"
        elif loc_type == "ללא רחוב":
            addr_route = "empty"
        else:
            addr_route = "landmark"

        # ── Confidence scoring ────────────────────────────────────────────────
        # Each classification gets a tier: high / medium / low.
        # "high"   = deterministic rule, no ambiguity
        # "medium" = heuristic/fallback, likely correct but worth a spot-check
        # "low"    = could not be resolved confidently, needs human judgement
        _tier = {"low": 0, "medium": 1, "high": 2}
        conf_details = []

        # Category
        if cat_source == "map":
            cat_conf = "high"
            conf_details.append(f"קטגוריה:מיפוי ישיר — {orig_sub} ← {new_cat}:high")
        elif cat_source == "topic_fallback":
            cat_conf = "medium"
            main_t = clean_text(r.get("נושא", ""))
            conf_details.append(f"קטגוריה:נגזרה מנושא — {main_t} ← {new_cat}:medium")
        else:
            cat_conf = "low"
            conf_details.append(f"קטגוריה:תת-נושא לא מזוהה — {orig_sub}:low")

        # Responsibility
        if resp_source == "map":
            resp_conf = "high"
            conf_details.append(f"אחריות:מיפוי ישיר — {new_cat} ← {resp}:high")
        elif resp_source.startswith("keyword:"):
            resp_conf = "medium"
            conf_details.append(f"אחריות:הוסקה ממילות מפתח — {resp}:medium")
        else:
            resp_conf = "low"
            conf_details.append(f"אחריות:לא נפתרה — נותרת א.מ.ל:low")

        # Address
        if addr_route in ("std", "intersection", "range"):
            addr_conf = "high"
            _route_he = {"std": "כתובת רגילה", "intersection": "צומת", "range": "טווח בתים"}
            conf_details.append(f"כתובת:{_route_he.get(addr_route, addr_route)} — {loc.get('רחוב_ראשי', '')} {loc.get('מספר_בית', '')}:high")
        elif addr_route in ("apt_suffix", "multi"):
            addr_conf = "medium"
            _route_he2 = {"apt_suffix": "עם סיומת דירה/קומה", "multi": "מספרים מרובים"}
            conf_details.append(f"כתובת:{_route_he2.get(addr_route, addr_route)} — {loc.get('רחוב_ראשי', '')}:medium")
        elif addr_route == "landmark":
            if loc.get("רחוב_ראשי"):
                addr_conf = "medium"
                conf_details.append(f"כתובת:ציון דרך (ללא מספר בית) — {loc['רחוב_ראשי']}:medium")
            else:
                addr_conf = "low"
                conf_details.append(f"כתובת:ציון דרך — לא זוהה רחוב ברור:low")
        else:  # empty
            addr_conf = "low"
            raw_addr = clean_text(r.get("כתובת ואתר/מוסד", ""))
            conf_details.append(f"כתובת:ריקה/לא ניתנת לפרסור — {raw_addr[:40] if raw_addr else 'ריק'}:low")

        overall_conf = min([cat_conf, resp_conf, addr_conf], key=lambda x: _tier[x])

        rows.append({
            "מס' פניה": clean_id, "תאריך": date, "שעה": hour, "יום": weekday, "חודש": month,
            "סטטוס פנייה": r.get("סטטוס פנייה"), "נושא": r.get("נושא"),
            "תת_נושא_חדש": new_cat, "חומר": substance, "אחריות": resp, "נכס": asset,
            "רחוב_ראשי": loc["רחוב_ראשי"], "רחוב_משני": loc["רחוב_משני"],
            "מספר_בית": loc["מספר_בית"], "סוג_מיקום": loc["סוג_מיקום"],
            "תיאור": r.get("תיאור"), "הערת_מיקום": loc["הערת_מיקום"],
            "תלונה_חוזרת": None, "בקשת_חזרה": detect_callback(r.get("תיאור")),
            "מידע_אישי": detect_personal_info(r.get("תיאור")), "סיומת_פניה": suffix,
            "כתובת ואתר/מוסד": r.get("כתובת ואתר/מוסד"), "רחוב": loc["רחוב"],
            "הערת_כתובת": loc["הערת_כתובת"], "מחלקה": r.get("מחלקה"),
            "תת נושא מקורי": orig_sub, "מספר_חזרה": None,
            "סיווג_מקור": cat_source, "אחריות_מקור": resp_source, "מסלול_כתובת": addr_route,
            "תוקן_אוטומטית": False,
            "_confidence": overall_conf,
            "_confidence_details": " | ".join(conf_details),
        })

    out = pd.DataFrame(rows)
    out["_date"] = pd.to_datetime(out["תאריך"], errors="coerce")
    out = out.sort_values("_date").reset_index(drop=True)
    out["מספר_חזרה"] = out.groupby(["רחוב_ראשי", "מספר_בית", "תת_נושא_חדש"]).cumcount() + 1
    out["תלונה_חוזרת"] = (out["מספר_חזרה"] > 1).astype(int)
    out = out.drop(columns=["_date"])
    out["מס' פניה"] = out["מס' פניה"].astype(str).str.replace(r"\.0$", "", regex=True)

    conf_counts = out["_confidence"].value_counts().to_dict() if "_confidence" in out.columns else {}
    stats = {
        "rows": len(out),
        "recurring_rate": round(out["תלונה_חוזרת"].mean() * 100, 1) if len(out) else 0,
        "unknown_resp_rate": round((out["אחריות"] == "א.מ.ל").mean() * 100, 1) if len(out) else 0,
        "conf_high":   conf_counts.get("high",   0),
        "conf_medium": conf_counts.get("medium", 0),
        "conf_low":    conf_counts.get("low",    0),
    }

    return out, stats


# ============================================================================
#  CLUSTER DETECTION & USER-ANSWER RESOLUTION
# ============================================================================

KNOWN_CATEGORIES_LIST = sorted(RESPONSIBILITY_MAP.keys())
KNOWN_RESPONSIBILITIES = ["כשל עירוני", "התנהגות אזרח", "טבעי", "לא רלוונטי"]

# Common Hebrew function words + boilerplate that carry no cause signal.
# Removed before discovering which *content* words recur in the free text.
_HEB_STOPWORDS = {
    "של", "על", "את", "לא", "עם", "יש", "זה", "זו", "זאת", "גם", "אני", "הוא",
    "היא", "כי", "אבל", "או", "כמו", "אחרי", "לפני", "בין", "כבר", "מאוד", "פה",
    "שם", "ליד", "מול", "רחוב", "רח", "בית", "כתובת", "אזור", "מקום", "בבקשה",
    "תודה", "שלום", "פנייה", "פניה", "פונה", "מבקש", "מבקשת", "מבקשים", "צריך",
    "צריכה", "וגם", "אנא", "כאן", "היום", "אתמול", "שוב", "הרבה", "כל", "כמה",
    "מה", "יותר", "עדיין", "בגלל", "נמצא", "נמצאת", "וכן", "אחד", "אחת", "שני",
    "שתי", "הזה", "הזאת", "להיות", "גורם", "מספר", "דירה", "קומה", "כניסה",
    "בניין", "ברחוב", "וכו", "שכתובת", "גבי", "אך", "רק", "אם", "כדי", "כן",
    "לכן", "אשר", "היה", "היתה", "הייתה", "יהיה", "איזה", "איזו", "מתי", "למה",
    "לנו", "להם", "אלי", "אליו", "אליה", "שלנו", "שלהם", "שלי", "שלו", "שלה",
    "עדין", "מאד", "ליום", "בימים", "בשעה", "בשעות", "אחה", "בוקר", "ערב",
}


def _tokenize_heb(text) -> list:
    """Split Hebrew free-text into content tokens (2+ Hebrew letters, no stopwords)."""
    toks = re.findall(r"[א-ת]{2,}", str(text))
    return [t for t in toks if t not in _HEB_STOPWORDS]


def _discover_patterns(desc_list: list, min_count: int = 5, max_groups: int = 4):
    """
    Data-driven pattern discovery: find the content words that recur most often
    across a set of free-text descriptions, and form one answerable group per
    recurring word. This lets the app generate its OWN questions ("calls that
    mention X — who is responsible?") instead of relying only on a fixed
    keyword list.

    Returns (groups, used_row_positions) where groups is a list of
    {"term": str, "count": int, "row_idxs": [positions into desc_list]} and
    groups are made disjoint (each row assigned to its strongest term) so the
    reviewer never answers about the same call twice.
    """
    from collections import Counter
    counts: Counter = Counter()
    per_term_rows: dict = {}
    for i, d in enumerate(desc_list):
        for t in set(_tokenize_heb(d)):
            counts[t] += 1
            per_term_rows.setdefault(t, []).append(i)

    groups = []
    used: set = set()
    for term, _cnt in counts.most_common():
        if _cnt < min_count:
            break
        rows = [i for i in per_term_rows[term] if i not in used]
        if len(rows) < min_count:
            continue
        groups.append({"term": term, "count": len(rows), "row_idxs": rows})
        used.update(rows)
        if len(groups) >= max_groups:
            break
    return groups, used


def find_clusters(df: pd.DataFrame) -> dict:
    """
    Find groups of uncertain rows that a user answer can resolve.

    Design principle — every generated question must be:
      • ANSWERABLE  — shows a concrete, homogeneous group with real samples
      • NON-CIRCULAR — labelled by what is OBSERVED in the text, never by the
                       answer we want (we never ask "who is responsible for the
                       'municipal-failure' calls?")
      • WORTH ASKING — only rows still genuinely unresolved after auto-cleaning
                       (keyword/map matches are already assigned, so we don't
                       re-ask about them)

    For each ambiguous category we take only the rows whose responsibility is
    still unknown, then discover which content words recur in their free text
    and turn each into a question. A single default question covers the rest.

    Returns:
      {"unknown_subtopics": [{value, count, examples}],
       "unresolved_resp":   [{category, total, unresolved,
                              pattern_groups: [{observation, count, desc_samples}],
                              remainder, default_guess}]}
    """
    clusters: dict = {"unknown_subtopics": [], "unresolved_resp": []}

    if "סיווג_מקור" in df.columns and "תת נושא מקורי" in df.columns:
        passthrough = df[df["סיווג_מקור"] == "passthrough"]
        for val, grp in passthrough.groupby("תת נושא מקורי"):
            val_str = str(val).strip()
            if val_str and val_str not in ("nan", "None", ""):
                examples = [
                    str(r.get("תיאור", ""))[:60]
                    for _, r in grp.head(2).iterrows()
                    if str(r.get("תיאור", "")).strip()
                ]
                clusters["unknown_subtopics"].append(
                    {"value": val_str, "count": len(grp), "examples": examples}
                )
        clusters["unknown_subtopics"].sort(key=lambda x: -x["count"])

    # Ambiguous-responsibility categories — ask ONLY about still-unresolved rows
    _AMBIGUOUS_CATS = {cat for cat, resp in RESPONSIBILITY_MAP.items() if resp == "א.מ.ל"}
    if "תת_נושא_חדש" in df.columns and "תיאור" in df.columns:
        import random as _rnd
        _rng = _rnd.Random(42)
        has_src = "אחריות_מקור" in df.columns

        for cat in sorted(_AMBIGUOUS_CATS):
            cat_rows = df[df["תת_נושא_חדש"] == cat]
            if len(cat_rows) < 3:
                continue

            # Rows still genuinely unknown (keyword/map matches already resolved)
            if has_src:
                unresolved = cat_rows[cat_rows["אחריות_מקור"] == "unresolved"]
            else:
                unresolved = cat_rows[cat_rows["אחריות"] == "א.מ.ל"]
            if len(unresolved) < 5:
                continue

            desc_list = unresolved["תיאור"].fillna("").astype(str).tolist()
            min_count = max(5, len(unresolved) // 50)
            groups, used = _discover_patterns(desc_list, min_count=min_count, max_groups=4)

            pattern_groups = []
            for g in groups:
                pool = [desc_list[i] for i in g["row_idxs"] if desc_list[i].strip()]
                samp_idx = _rng.sample(range(len(pool)), min(2, len(pool))) if pool else []
                samples = [pool[i][:120] for i in samp_idx]
                pattern_groups.append({
                    "observation":  g["term"],
                    "count":        g["count"],
                    "desc_samples": samples,
                })

            remainder = len(unresolved) - len(used)

            # Soft default suggestion = the responsibility most common among the
            # rows in this category that WERE resolved automatically.
            default_guess = None
            if has_src:
                resolved = cat_rows[cat_rows["אחריות_מקור"] != "unresolved"]
                if len(resolved):
                    vc = resolved["אחריות"].value_counts()
                    vc = vc[~vc.index.isin(["א.מ.ל"])]
                    if len(vc):
                        default_guess = str(vc.index[0])

            clusters["unresolved_resp"].append({
                "category":       cat,
                "total":          len(cat_rows),
                "unresolved":     len(unresolved),
                "pattern_groups": pattern_groups,
                "remainder":      remainder,
                "default_guess":  default_guess,
            })

        clusters["unresolved_resp"].sort(key=lambda x: -x["unresolved"])

    return clusters


def apply_user_answers(df: pd.DataFrame, answers: dict) -> pd.DataFrame:
    """
    Apply user-provided answers to cluster questions and recompute confidence.
    answer keys:
      "subtopic:X"  → category assignment for unknown sub-topic X
      "resp:Y"      → responsibility assignment for category Y
      "street:ORIG" → canonical replacement for street name ORIG
    Skipped answers have value "__skip__" or empty string.
    """
    df = df.copy()
    _tier = {"low": 0, "medium": 1, "high": 2}

    # First pass: re-run auto keyword resolution on currently-unresolved rows
    # (picks up newly-added keywords like bird/pigeon without requiring user input)
    if "אחריות_מקור" in df.columns and "תת_נושא_חדש" in df.columns:
        unresolved_mask = df["אחריות_מקור"] == "unresolved"
        for idx in df[unresolved_mask].index:
            cat  = str(df.at[idx, "תת_נושא_חדש"])
            desc = str(df.at[idx, "תיאור"]) if "תיאור" in df.columns else ""
            new_resp = resolve_responsibility(cat, desc)
            if new_resp != "א.מ.ל":
                df.at[idx, "אחריות"] = new_resp
                df.at[idx, "אחריות_מקור"] = f"keyword:{new_resp}"

    # Second pass: apply explicit user answers
    for key, answer in answers.items():
        if not answer or str(answer).strip() in ("__skip__", "", "nan"):
            continue

        if key.startswith("subtopic:"):
            orig_sub = key[len("subtopic:"):]
            if "תת נושא מקורי" in df.columns:
                mask = df["תת נושא מקורי"] == orig_sub
                if mask.any():
                    df.loc[mask, "תת_נושא_חדש"] = answer
                    df.loc[mask, "סיווג_מקור"] = "user_map"
                    for idx in df[mask].index:
                        desc = df.at[idx, "תיאור"] if "תיאור" in df.columns else ""
                        new_resp = resolve_responsibility(answer, desc)
                        df.at[idx, "אחריות"] = new_resp
                        base_r = RESPONSIBILITY_MAP.get(answer, "א.מ.ל")
                        if base_r != "א.מ.ל":
                            df.at[idx, "אחריות_מקור"] = "map"
                        elif new_resp != "א.מ.ל":
                            df.at[idx, "אחריות_מקור"] = f"keyword:{new_resp}"

        elif key.startswith("resp_term:"):
            # "resp_term:{category}:{observed_word}" — applies to still-unresolved
            # rows of the category whose free text contains that discovered word.
            parts = key.split(":", 2)
            if len(parts) == 3:
                _, category, term = parts
                if term and "תת_נושא_חדש" in df.columns and "תיאור" in df.columns:
                    mask = df["תת_נושא_חדש"] == category
                    if "אחריות_מקור" in df.columns:
                        mask &= (df["אחריות_מקור"] == "unresolved")
                    else:
                        mask &= (df["אחריות"] == "א.מ.ל")
                    mask &= df["תיאור"].apply(
                        lambda d: term in str(d) if pd.notna(d) else False)
                    if mask.any():
                        df.loc[mask, "אחריות"] = answer
                        df.loc[mask, "אחריות_מקור"] = "user_resp_term"

        elif key.startswith("resp_default:"):
            # "resp_default:{category}" — applies to every remaining unresolved
            # row of the category (the reviewer's default for the leftovers).
            category = key[len("resp_default:"):]
            if "תת_נושא_חדש" in df.columns:
                mask = df["תת_נושא_חדש"] == category
                if "אחריות_מקור" in df.columns:
                    mask &= (df["אחריות_מקור"] == "unresolved")
                else:
                    mask &= (df["אחריות"] == "א.מ.ל")
                if mask.any():
                    df.loc[mask, "אחריות"] = answer
                    df.loc[mask, "אחריות_מקור"] = "user_resp_default"

        elif key.startswith("resp_sub:"):
            # Legacy: "resp_sub:{category}:{keyword_group_label}"
            parts = key.split(":", 2)
            if len(parts) == 3:
                _, category, kw_group = parts
                keywords_for_group = _RESP_KEYWORDS.get(kw_group, [])
                if keywords_for_group and "תת_נושא_חדש" in df.columns and "תיאור" in df.columns:
                    cat_mask = df["תת_נושא_חדש"] == category
                    kw_mask = df["תיאור"].apply(
                        lambda d: any(kw in str(d) for kw in keywords_for_group) if pd.notna(d) else False
                    )
                    mask = cat_mask & kw_mask
                    if mask.any():
                        df.loc[mask, "אחריות"] = answer
                        df.loc[mask, "אחריות_מקור"] = "user_resp_kw"

        elif key.startswith("resp_unmatched:"):
            # Legacy: "resp_unmatched:{category}"
            category = key[len("resp_unmatched:"):]
            if "תת_נושא_חדש" in df.columns and "תיאור" in df.columns:
                cat_mask = df["תת_נושא_חדש"] == category
                all_kws = [kw for kws in _RESP_KEYWORDS.values() for kw in kws]
                no_kw_mask = ~df["תיאור"].apply(
                    lambda d: any(kw in str(d) for kw in all_kws) if pd.notna(d) else False
                )
                mask = cat_mask & no_kw_mask
                if mask.any():
                    df.loc[mask, "אחריות"] = answer
                    df.loc[mask, "אחריות_מקור"] = "user_resp_unmatched"

        elif key.startswith("resp:"):
            # Legacy key — applies to all unresolved rows of this category
            category = key[len("resp:"):]
            if "תת_נושא_חדש" in df.columns and "אחריות" in df.columns:
                mask = (df["תת_נושא_חדש"] == category) & (df["אחריות"] == "א.מ.ל")
                if mask.any():
                    df.loc[mask, "אחריות"] = answer
                    df.loc[mask, "אחריות_מקור"] = "user_resp"

        elif key.startswith("street:"):
            orig_street = key[len("street:"):]
            if "רחוב_ראשי" in df.columns:
                mask = df["רחוב_ראשי"] == orig_street
                if mask.any():
                    df.loc[mask, "רחוב_ראשי"] = answer

    def _recompute(row):
        cat_src  = str(row.get("סיווג_מקור", ""))
        resp_src = str(row.get("אחריות_מקור", ""))
        addr_r   = str(row.get("מסלול_כתובת", ""))
        cat_conf  = ("high"   if cat_src in ("map", "user_map") else
                     "medium" if cat_src == "topic_fallback" else "low")
        resp_conf = ("high"   if resp_src in ("map", "user_resp", "user_resp_kw", "user_resp_unmatched",
                                              "user_resp_term", "user_resp_default") else
                     "medium" if resp_src.startswith("keyword:") else "low")
        if addr_r in ("std", "intersection", "range"):
            addr_conf = "high"
        elif addr_r in ("apt_suffix", "multi"):
            addr_conf = "medium"
        elif addr_r == "landmark":
            addr_conf = "medium" if row.get("רחוב_ראשי") else "low"
        else:
            addr_conf = "low"
        return min([cat_conf, resp_conf, addr_conf], key=lambda x: _tier[x])

    df["_confidence"] = df.apply(_recompute, axis=1)
    return df


def run(input_file=INPUT_FILE):
    """CLI wrapper — delegates to clean_dataframe(), writes output files."""
    print(f"Loading raw export: {input_file}")
    df_raw = pd.read_excel(input_file)
    print(f"  {len(df_raw):,} rows loaded.")

    out, stats = clean_dataframe(df_raw)

    base = os.path.splitext(input_file)[0]
    main_path = base + "_מנוקה.xlsx"
    out.to_excel(main_path, index=False)

    print("\n── Done ─────────────────────────────────────")
    print(f"  Structured file : {main_path}  ({stats['rows']:,} rows)")
    print(f"  Recurring rate  : {stats['recurring_rate']}%")
    print(f"  Unknown resp.   : {stats['unknown_resp_rate']}%")
    print("─────────────────────────────────────────────")


if __name__ == "__main__":
    run()
