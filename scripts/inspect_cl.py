import chainladder as cl
import json

d = cl.load_sample('clrd')
print('LOBs:', d.index['LOB'].unique().tolist())
print('Origens:', d.origin.tolist())
print('Devs:', d.development.tolist())
print('Colunas:', d.columns.tolist())

# Aggregate across companies for one LOB
lobs = d.index['LOB'].unique().tolist()
for lob in lobs:
    sub = d[d.index['LOB'] == lob].sum(axis='index')
    inc = sub['IncurLoss']
    paid = sub['CumPaidLoss']
    prem = sub['EarnedPremDIR']
    print(f'\n--- {lob} ---')
    print('IncurLoss shape:', inc.shape)
    # Try to get values as 2D
    try:
        arr = inc.to_frame().reset_index()
        print(arr.head(5).to_string())
    except Exception as e:
        print('to_frame error:', e)
    try:
        vals = inc.values
        print('values shape:', vals.shape if hasattr(vals, 'shape') else type(vals))
    except Exception as e:
        print('values error:', e)
