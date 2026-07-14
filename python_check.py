import pandas as pd
import glob

files = glob.glob('*לבדיקה*.xlsx')
df = pd.read_excel(files[0], sheet_name='כל הנתונים')
for cat in ['משטח מלוכלך', 'פח נעלם']:
    print(f'\n=== {cat} ===')
    print(df[df['תת_נושא_חדש']==cat][['תיאור','אחריות']].head(25).to_string())