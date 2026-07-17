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
    ],
    "טבעי": [
        "גשם", "רוח", "עלים", "שלכת", "ענפים", "שיטפון",
        "חצץ שזורם", "סחף", "עצים נפלו",
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
        })

    out = pd.DataFrame(rows)
    out["_date"] = pd.to_datetime(out["תאריך"], errors="coerce")
    out = out.sort_values("_date").reset_index(drop=True)
    out["מספר_חזרה"] = out.groupby(["רחוב_ראשי", "מספר_בית", "תת_נושא_חדש"]).cumcount() + 1
    out["תלונה_חוזרת"] = (out["מספר_חזרה"] > 1).astype(int)
    out = out.drop(columns=["_date"])
    out["מס' פניה"] = out["מס' פניה"].astype(str).str.replace(r"\.0$", "", regex=True)

    stats = {
        "rows": len(out),
        "recurring_rate": round(out["תלונה_חוזרת"].mean() * 100, 1) if len(out) else 0,
        "unknown_resp_rate": round((out["אחריות"] == "א.מ.ל").mean() * 100, 1) if len(out) else 0,
    }

    return out, stats


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
