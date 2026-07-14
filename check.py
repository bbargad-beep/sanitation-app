import pandas as pd

d = pd.read_pickle(r'C:\Users\Benjamin\AppData\Local\Temp\herzliya_sanitation_app_state.pkl')
df = d['df']

ids = ['2082731','2082361','2083015','2084841','2085108','2087175','2082862','2082878']
mask = df["מס' פניה"].astype(str).isin(ids)
cols = [c for c in ["מס' פניה","רחוב_ראשי","מספר_בית","סוג_מיקום","geocode_method"] if c in df.columns]
print(df[mask][cols].to_string())
