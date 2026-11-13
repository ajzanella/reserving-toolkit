"""
scripts/naic_cas.py — Extrai triângulos CAS Schedule P via pacote chainladder.

Fonte primária: pacote Python `chainladder` (CAS Loss Reserving Database, 1988-1997).
Fallback: casact.org CSV (URL pode estar desatualizada).

6 LOBs × pago+incorrido = 12 triângulos.
Mercado total (soma de todas as seguradoras).
Valores em USD (milhares).

Uso:
    python scripts/naic_cas.py            # imprime resumo
    python scripts/naic_cas.py --save     # salva triangles_cas.json
    python scripts/naic_cas.py --lob ppauto  # só este LOB
"""

import json
import argparse

LOB_CONFIG = {
    'othliab':  {'label': 'Other Liability (RC Geral)', 'cats': ['naic', 'liability']},
    'ppauto':   {'label': 'Private Passenger Auto',     'cats': ['naic', 'auto']},
    'comauto':  {'label': 'Commercial Auto',            'cats': ['naic', 'auto']},
    'wkcomp':   {'label': 'Workers Compensation',       'cats': ['naic', 'wkcomp']},
    'prodliab': {'label': 'Products Liability',         'cats': ['naic', 'liability']},
    'medmal':   {'label': 'Medical Malpractice',        'cats': ['naic', 'medmal', 'liability']},
}


def _df_to_triangle(df, lags):
    """
    Converte um DataFrame (index=date, cols=lags numéricos) para o formato
    triangles.json: origins (list[str]), lags (list[int]), data (lista de listas com None).
    """
    origins = []
    data = []
    n = len(df)
    for i, (idx, row) in enumerate(df.iterrows()):
        year = str(idx.year) if hasattr(idx, 'year') else str(idx)[:4]
        origins.append(year)
        row_data = []
        for j, lag in enumerate(lags):
            val = row.get(lag, None)
            import math
            if val is None or (isinstance(val, float) and math.isnan(val)):
                val = None
            elif i + j >= n:
                val = None
            else:
                val = round(float(val), 0)
            row_data.append(val)
        data.append(row_data)
    return origins, data


def process_via_chainladder(lob: str) -> dict:
    import chainladder as cl
    d = cl.load_sample('clrd')
    sub = d[d.index['LOB'] == lob].sum(axis='index')

    lags = [int(x) for x in d.development.tolist()]

    result = {}

    # Incorrido
    inc_df = sub['IncurLoss'].to_frame().reset_index().set_index('index')
    origins, data = _df_to_triangle(inc_df, lags)
    key_inc = f'CAS_{lob}_incurred'
    result[key_inc] = {
        'origins': origins, 'lags': lags, 'data': data,
        '_source': 'CAS CLRD via chainladder (1988-1997)',
        '_lob': LOB_CONFIG[lob]['label'],
        '_type': 'incurred', '_country': 'EUA',
    }

    # Pago
    paid_df = sub['CumPaidLoss'].to_frame().reset_index().set_index('index')
    _, data_paid = _df_to_triangle(paid_df, lags)
    key_paid = f'CAS_{lob}_paid'
    result[key_paid] = {
        'origins': origins, 'lags': lags, 'data': data_paid,
        '_source': 'CAS CLRD via chainladder (1988-1997)',
        '_lob': LOB_CONFIG[lob]['label'],
        '_type': 'paid', '_country': 'EUA',
    }

    # Prêmio ganho (líquido) — lag 12 = prêmio do ano de origem
    prem_df = sub['EarnedPremNet'].to_frame().reset_index().set_index('index')
    earned = {}
    for idx, row in prem_df.iterrows():
        year = str(idx.year) if hasattr(idx, 'year') else str(idx)[:4]
        val = row.get(12, None)
        import math
        if val is not None and not math.isnan(val):
            earned[year] = round(float(val), 0)
    for k in [key_inc, key_paid]:
        result[k]['earned_premiums'] = earned

    return result


def process_lob(lob: str) -> dict:
    print(f'  [{lob}] chainladder ...', end=' ', flush=True)
    result = process_via_chainladder(lob)
    for k, v in result.items():
        print(f"\n    → {k}: {len(v['origins'])}×{len(v['lags'])}", end='')
    print()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--lob', help='Só este LOB (ex: ppauto)')
    args = parser.parse_args()

    lobs = [args.lob] if args.lob else list(LOB_CONFIG.keys())
    all_triangles = {}

    for lob in lobs:
        try:
            result = process_lob(lob)
            all_triangles.update(result)
        except Exception as e:
            print(f'  ERRO {lob}: {e}')

    print(f'\nTotal: {len(all_triangles)} triângulos')

    if args.save:
        out = 'D:/reserving-web/data/triangles_cas.json'
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'triangles': all_triangles}, f, ensure_ascii=False, indent=2)
        print(f'Salvo em {out}')

    return all_triangles


if __name__ == '__main__':
    main()
