# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
f = os.path.join(APP_DIR, "geocode_pipeline.py")

with open(f, 'r', encoding='utf-8') as fh:
    txt = fh.read()

# The file stores ׳ (geresh) as a literal 6-char escape: ׳
GERESH_ESCAPED = r'׳'
TARGET_GIS = "    'יצחק נגר':                  'נג" + GERESH_ESCAPED + "ר יצחק',"
REPLACEMENT_GIS = TARGET_GIS + "\n    'נגר יצחק':                  'נג" + GERESH_ESCAPED + "ר יצחק',"

if TARGET_GIS in txt:
    txt = txt.replace(TARGET_GIS, REPLACEMENT_GIS, 1)
    print("GIS_MANUAL_MAP: added 'נגר יצחק' entry OK")
else:
    idx = txt.find('יצחק נגר')
    print("GIS_MANUAL_MAP target not found — context:", repr(txt[idx-4:idx+80]) if idx != -1 else "no match at all")

with open(f, 'w', encoding='utf-8') as fh:
    fh.write(txt)

print("Done — geocode_pipeline.py updated")
