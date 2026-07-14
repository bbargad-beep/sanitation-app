"""
Run this while the Streamlit app is still running and showing the geocode results.
It reads the session state pickle and saves the geocoded df to a safe location.
"""
import pickle
import pandas as pd
import os

src = r'C:\Users\Benjamin\AppData\Local\Temp\herzliya_sanitation_app_state.pkl'

if not os.path.exists(src):
    print("ERROR: state file not found at", src)
    exit(1)

d = pickle.load(open(src, 'rb'))
df = d['df']
print(f"stage: {d['stage']}")
print(f"geocoded flag: {d['geocoded']}")
print(f"rows: {len(df)}")

if 'קו_רוחב' in df.columns:
    n = df['קו_רוחב'].notna().sum()
    print(f"rows with coordinates: {n}")
else:
    print("WARNING: no קו_רוחב column — geocoding not yet in this snapshot")

# Save to a safe named file in the app folder
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geocoded_state_backup.pkl')
pickle.dump(d, open(out, 'wb'))
print(f"\nSaved to: {out}")
print("You can now safely replace app.py")
