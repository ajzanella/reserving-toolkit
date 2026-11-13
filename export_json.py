"""
Exporta todos os triângulos do pkl para data/triangles.json
"""
import sys, json, pickle
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, r'D:\reserving-atuarial')
from src.triangle import load_all

PKL  = r'D:\reserving-atuarial\data\processed\triangles_all.pkl'
OUT  = Path(__file__).parent / 'data' / 'triangles.json'

triangles = load_all(PKL)

result = {}
for name, tri in triangles.items():
    data_rows = []
    for i in tri.data.index:
        row = []
        for j in tri.data.columns:
            v = tri.data.loc[i, j]
            row.append(None if pd.isna(v) else float(v))
        data_rows.append(row)

    result[name] = {
        'name':    name,
        'n':       tri.n,
        'm':       tri.m,
        'origins': [str(o) for o in tri._origin_labels],
        'lags':    [int(c) for c in tri.data.columns],
        'data':    data_rows,
    }

OUT.write_text(json.dumps({'triangles': result}, separators=(',', ':')), encoding='utf-8')
size_kb = OUT.stat().st_size // 1024
print(f'Exportado: {len(result)} triângulos → {OUT} ({size_kb} KB)')
