# -*- coding: utf-8 -*-
"""
Page 2 — מדריך שימוש
Step-by-step guide: what to prepare, how to run each stage, how to interpret outputs.
"""

import streamlit as st

st.set_page_config(
    page_title="מדריך שימוש | הרצליה תברואה",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family:'Heebo',Arial,sans-serif; direction:rtl; }
.stApp { direction:rtl; }
h1,h2,h3,h4,p,div,span,label { direction:rtl; text-align:right; }
.main-header {
  background:linear-gradient(135deg,#1a3a5c 0%,#2563a8 100%); color:white;
  padding:1.6rem 2rem; border-radius:12px; margin-bottom:1.4rem; text-align:right;
}
.main-header h1 { color:white; font-size:1.8rem; font-weight:700; margin:0 0 .3rem 0; }
.main-header p  { color:#c8d9f0; font-size:.92rem; margin:0; }
.step-card {
  background:#f0f7ff; border-right:4px solid #2563a8; border-radius:8px;
  padding:1rem 1.3rem; margin-bottom:.9rem; direction:rtl;
}
.step-card h4 { color:#1a3a5c; font-size:1rem; font-weight:600; margin:0 0 .4rem 0; }
.step-card p  { color:#475569; font-size:.9rem; margin:0; line-height:1.7; }
.tip-card {
  background:#f0fdf4; border-right:4px solid #059669; border-radius:8px;
  padding:.8rem 1.2rem; margin-bottom:.7rem; direction:rtl;
}
.tip-card p { color:#065f46; font-size:.88rem; margin:0; line-height:1.6; }
.warn-card {
  background:#fef3c7; border-right:4px solid #d97706; border-radius:8px;
  padding:.8rem 1.2rem; margin-bottom:.7rem; direction:rtl;
}
.warn-card p { color:#92400e; font-size:.88rem; margin:0; line-height:1.6; }
.placeholder {
  background:#fef9c3; border:1px dashed #f59e0b; border-radius:6px;
  padding:.7rem 1rem; color:#92400e; font-size:.88rem; direction:rtl; text-align:right;
  margin-bottom:.5rem;
}
.num-badge {
  display:inline-block; background:#2563a8; color:white; border-radius:50%;
  width:28px; height:28px; line-height:28px; text-align:center;
  font-weight:700; font-size:.9rem; margin-left:8px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
  <h1>📖 מדריך שימוש</h1>
  <p>עיריית הרצליה — כיצד להפעיל את המערכת מקצה לקצה</p>
</div>
""", unsafe_allow_html=True)


# ── 0. דרישות מוקדמות ────────────────────────────────────────────────────────
st.markdown("## 🛠️ לפני שמתחילים — דרישות מוקדמות")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    <div class="step-card">
      <h4>מה צריך להכין?</h4>
      <div class="placeholder">⬜ [יש למלא: קובץ ייצוא מ-CRM 360 בפורמט .xlsx, גישה לאינטרנט לצורך גאוקוד, הרשאות פנימיות אם נדרש]</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div class="step-card">
      <h4>פורמט הקובץ</h4>
      <div class="placeholder">⬜ [יש למלא: אילו עמודות חייבות להופיע, שמות מדויקים, הערות על גרסאות שונות של ייצוא CRM]</div>
    </div>
    """, unsafe_allow_html=True)


# ── 1. העלאה ─────────────────────────────────────────────────────────────────
st.markdown("## <span class='num-badge'>1</span> שלב ההעלאה", unsafe_allow_html=True)

with st.expander("פתח הוראות", expanded=True):
    st.markdown("""
    <div class="step-card">
      <h4>כיצד להעלות?</h4>
      <div class="placeholder">⬜ [יש למלא: לחץ על כפתור "בחרו קובץ", בחר את הייצוא מ-CRM, המתן לאימות]</div>
    </div>
    <div class="tip-card"><p>💡 <strong>טיפ:</strong> [⬜ למשל: ודאו שהקובץ לא פתוח ב-Excel כשאתם מעלים אותו]</p></div>
    <div class="warn-card"><p>⚠️ <strong>שימו לב:</strong> [⬜ למשל: אם חסרות עמודות, המערכת תעצור ותציין מה חסר]</p></div>
    """, unsafe_allow_html=True)
    st.markdown("**מה המערכת עושה בשלב זה?**")
    st.markdown('<div class="placeholder">⬜ [יש לתאר: אימות עמודות, תצוגה מקדימה של 5 שורות, בדיקת אינטגריטי בסיסית]</div>', unsafe_allow_html=True)


# ── 2. ניקוי ─────────────────────────────────────────────────────────────────
st.markdown("## <span class='num-badge'>2</span> שלב הניקוי", unsafe_allow_html=True)

with st.expander("פתח הוראות", expanded=False):
    st.markdown("""
    <div class="step-card">
      <h4>קריאת תוצאות הניקוי</h4>
      <div class="placeholder">⬜ [יש למלא: הסבר על שלושת מצבי השורה — תקינה / אזהרה / חוסמת; מה כל צבע אומר]</div>
    </div>
    <div class="step-card">
      <h4>מה לעשות עם שורות חוסמות?</h4>
      <div class="placeholder">⬜ [יש למלא: הורד קובץ Excel לבדיקה, תקן בגיליון "דורשות תיקון", העלה מחדש; או לחץ "החרג"]</div>
    </div>
    <div class="step-card">
      <h4>הבנת מה השתנה (🔍 מה השתנה?)</h4>
      <div class="placeholder">⬜ [יש למלא: הסבר על ה-expander — ניתוב כתובות, מקורות קטגוריה, תיקוני רחוב, יומן auto_fix]</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="tip-card"><p>💡 <strong>טיפ:</strong> [⬜ למשל: 99% מהשגיאות נפתרות אוטומטית. בדרך כלל רק כמה עשרות שורות יצריכו תשומת לב ידנית]</p></div>', unsafe_allow_html=True)


# ── 3. גאוקוד ────────────────────────────────────────────────────────────────
st.markdown("## <span class='num-badge'>3</span> שלב הגאוקוד", unsafe_allow_html=True)

with st.expander("פתח הוראות", expanded=False):
    st.markdown("""
    <div class="step-card">
      <h4>הפעלת הגאוקוד</h4>
      <div class="placeholder">⬜ [יש למלא: לחץ "הרץ גאוקוד", המתן — עשרות אלפי שורות ייקחו כ-X דקות, ניתן להמשיך מנקודת עצירה]</div>
    </div>
    <div class="step-card">
      <h4>המשך מנקודת עצירה</h4>
      <div class="placeholder">⬜ [יש למלא: אם הדפדפן נסגר באמצע, פתח מחדש — המערכת תציע להמשיך אוטומטית]</div>
    </div>
    <div class="step-card">
      <h4>תיקון ידני של כתובות לא נפתרות</h4>
      <div class="placeholder">⬜ [יש למלא: הסבר על טבלת העריכה — לחיצה על תא, הזנת קואורדינטות, כפתור "הזנה מרוכזת"]</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="warn-card"><p>⚠️ <strong>שימו לב:</strong> [⬜ למשל: תהליך הגאוקוד דורש חיבור לאינטרנט פעיל. VPN עלול להאט]</p></div>', unsafe_allow_html=True)


# ── 4. העשרה ─────────────────────────────────────────────────────────────────
st.markdown("## <span class='num-badge'>4</span> שלב ההעשרה", unsafe_allow_html=True)

with st.expander("פתח הוראות", expanded=False):
    st.markdown("""
    <div class="step-card">
      <h4>מה מחושב בהעשרה?</h4>
      <div class="placeholder">⬜ [יש למלא: אזור עירוני, ים פינוי, תלונות חוזרות, מרחק מגבול העיר]</div>
    </div>
    <div class="step-card">
      <h4>כיצד לקרוא את הסטטיסטיקות?</h4>
      <div class="placeholder">⬜ [יש למלא: הסבר על כרטיסי הנתונים — אחוז תלונות חוזרות, יום הפינוי הנפוץ וכו׳]</div>
    </div>
    """, unsafe_allow_html=True)


# ── 5. פלט וניתוח ────────────────────────────────────────────────────────────
st.markdown("## <span class='num-badge'>5</span> פלט וניתוח", unsafe_allow_html=True)

with st.expander("פתח הוראות", expanded=False):
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("""
        <div class="step-card">
          <h4>הורדת קובץ Excel הסופי</h4>
          <div class="placeholder">⬜ [יש למלא: מה כולל הקובץ — גיליון נתונים, סיכום, יומן תיקונים; הסבר על צביעת שורות]</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown("""
        <div class="step-card">
          <h4>מפת החום</h4>
          <div class="placeholder">⬜ [יש למלא: כיצד לקרוא את המפה, מה המשמעות של אזורי ריכוז]</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="step-card">
      <h4>הגרפים הסטטיסטיים</h4>
      <div class="placeholder">⬜ [יש למלא: הסבר על כל גרף — לפי חודש, לפי נושא, לפי אזור, ימי פינוי]</div>
    </div>
    """, unsafe_allow_html=True)


# ── שאלות נפוצות ─────────────────────────────────────────────────────────────
st.markdown("## ❓ שאלות נפוצות")

faqs = [
    ("כמה זמן לוקח הגאוקוד?", "⬜ [יש למלא: זמן משוער לפי כמות שורות; כ-X שורות לדקה]"),
    ("מה קורה אם סוגרים את הדפדפן באמצע?", "⬜ [יש למלא: המערכת שומרת נקודת עצירה כל 25 שורות; בפתיחה מחדש יוצע להמשיך]"),
    ("האם ניתן לעבד כמה קבצים?", "⬜ [יש למלא: כרגע מעבד קובץ אחד בכל פעם; להתחלה חדשה יש לרענן]"),
    ("מה לעשות אם כתובת לא גאוקודדת?", "⬜ [יש למלא: ניתן להזין קואורדינטות ידנית בטבלת העריכה, או להחריג דרך יומן האיכות]"),
    ("איפה שמורות ההיסטוריה והשינויים?", "⬜ [יש למלא: בקובץ הפלט — גיליון יומן_תיקונים; כל שינוי ממוקד עם חותמת זמן]"),
]

for q, a in faqs:
    with st.expander(q):
        st.markdown(f'<div class="placeholder">⬜ {a}</div>', unsafe_allow_html=True)


# ── יצירת קשר ────────────────────────────────────────────────────────────────
st.divider()
st.markdown("## 📞 עזרה ויצירת קשר")
st.markdown('<div class="placeholder">⬜ [יש למלא: כתובת מייל תמיכה, שם איש קשר, ערוץ דיווח על תקלות]</div>', unsafe_allow_html=True)
