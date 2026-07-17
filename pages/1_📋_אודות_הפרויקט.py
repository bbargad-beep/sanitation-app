# -*- coding: utf-8 -*-
"""
Page 1 — אודות הפרויקט
Project overview: goals, context, data sources, methodology, team.
"""

import streamlit as st

st.set_page_config(
    page_title="אודות הפרויקט | הרצליה תברואה",
    page_icon="📋",
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
.section-card {
  background:#f8fafc; border-right:4px solid #2563a8; border-radius:8px;
  padding:1rem 1.3rem; margin-bottom:1rem; direction:rtl;
}
.section-card h4 { color:#1a3a5c; font-size:1rem; font-weight:600; margin:0 0 .4rem 0; }
.section-card p  { color:#475569; font-size:.9rem; margin:0; line-height:1.7; }
.placeholder {
  background:#fef9c3; border:1px dashed #f59e0b; border-radius:6px;
  padding:.7rem 1rem; color:#92400e; font-size:.88rem; direction:rtl; text-align:right;
  margin-bottom:.5rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
  <h1>📋 אודות הפרויקט</h1>
  <p>עיריית הרצליה — מערכת ניתוח פניות תברואה</p>
</div>
""", unsafe_allow_html=True)


# ── 1. רקע ומטרות ────────────────────────────────────────────────────────────
st.markdown("## 🎯 רקע ומטרות הפרויקט")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    <div class="section-card">
      <h4>הבעיה שנפתרת</h4>
      <div class="placeholder">⬜ [יש למלא: מה הבעיה שהפרויקט פותר? למשל: נתוני CRM מפוזרים, חוסר יכולת לנתח דפוסי תלונות גאוגרפית וכו׳]</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div class="section-card">
      <h4>מטרות</h4>
      <div class="placeholder">⬜ [יש למלא: מטרות ספציפיות — גאוקוד, זיהוי דפוסים, הפחתת עומס ידני וכו׳]</div>
    </div>
    """, unsafe_allow_html=True)


# ── 2. הקשר ארגוני ───────────────────────────────────────────────────────────
st.markdown("## 🏛️ הקשר ארגוני")

st.markdown("""
<div class="section-card">
  <h4>מי הזמין את הפרויקט?</h4>
  <div class="placeholder">⬜ [יש למלא: מחלקה עירונית, שם הממונה, הקשר לתחום חדשנות עירונית]</div>
</div>
<div class="section-card">
  <h4>מי ייהנה מהמערכת?</h4>
  <div class="placeholder">⬜ [יש למלא: משתמשי קצה — אנליסטים, מנהלי מחלקה, שירות שדה וכו׳]</div>
</div>
""", unsafe_allow_html=True)


# ── 3. מקורות נתונים ──────────────────────────────────────────────────────────
st.markdown("## 🗄️ מקורות נתונים")

col3, col4, col5 = st.columns(3)
with col3:
    st.markdown("""
    <div class="section-card">
      <h4>CRM 360</h4>
      <div class="placeholder">⬜ [מה כולל הייצוא, תדירות, תקופה מכוסה]</div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown("""
    <div class="section-card">
      <h4>Nominatim / OSM</h4>
      <div class="placeholder">⬜ [תיאור קצר של שימוש ב-OpenStreetMap לגאוקוד]</div>
    </div>
    """, unsafe_allow_html=True)
with col5:
    st.markdown("""
    <div class="section-card">
      <h4>פורטל GIS העירוני</h4>
      <div class="placeholder">⬜ [מה מקורו, איך משתמשים בו כ-fallback]</div>
    </div>
    """, unsafe_allow_html=True)


# ── 4. מתודולוגיה ─────────────────────────────────────────────────────────────
st.markdown("## 🔬 מתודולוגיה")

with st.expander("שלב 1 — ניקוי נתונים", expanded=False):
    st.markdown('<div class="placeholder">⬜ [יש לפרט: מה מנוקה, איך מטופלות שגיאות כתובת, מה זה auto_fix]</div>', unsafe_allow_html=True)

with st.expander("שלב 2 — גאוקוד", expanded=False):
    st.markdown('<div class="placeholder">⬜ [שלושה מעברים: Nominatim → מרכזי רחובות → GIS. כיצד נקבעת דרגת דיוק]</div>', unsafe_allow_html=True)

with st.expander("שלב 3 — העשרה", expanded=False):
    st.markdown('<div class="placeholder">⬜ [אזורי עיר, ימי פינוי, זיהוי תלונות חוזרות]</div>', unsafe_allow_html=True)

with st.expander("שלב 4 — ניתוח ופלט", expanded=False):
    st.markdown('<div class="placeholder">⬜ [מפת חום, סטטיסטיקות, קובץ Excel מסומן]</div>', unsafe_allow_html=True)


# ── 5. מגבלות ידועות ──────────────────────────────────────────────────────────
st.markdown("## ⚠️ מגבלות ידועות")

st.markdown("""
<div class="section-card">
  <h4>מה המערכת לא עושה?</h4>
  <div class="placeholder">⬜ [יש למלא: כתובות שלא ניתן לגאוקד, נתונים חסרים, עדכון real-time וכו׳]</div>
</div>
""", unsafe_allow_html=True)


# ── 6. צוות ───────────────────────────────────────────────────────────────────
st.markdown("## 👥 צוות הפרויקט")

col6, col7 = st.columns(2)
with col6:
    st.markdown("""
    <div class="section-card">
      <h4>פותחים</h4>
      <div class="placeholder">⬜ [שמות, תפקידים, קישורים]</div>
    </div>
    """, unsafe_allow_html=True)
with col7:
    st.markdown("""
    <div class="section-card">
      <h4>גורמים מלווים / בעלי עניין</h4>
      <div class="placeholder">⬜ [עיריית הרצליה, אוניברסיטה, מרצה מלווה]</div>
    </div>
    """, unsafe_allow_html=True)


# ── 7. גרסה ותאריך ────────────────────────────────────────────────────────────
st.divider()
st.caption("גרסה: v1.0 · תאריך: יולי 2026 · [⬜ יש להוסיף מידע על גרסאות ושינויים]")
