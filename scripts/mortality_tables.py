"""
scripts/mortality_tables.py — Download e parse de tábuas de mortalidade do HLD (lifetable.de).

Fonte: Human Life-Table Database (lifetable.de) — gratuito, sem login.
Gera data/mortality_tables.json com tábuas por país/sexo.

Uso:
    python scripts/mortality_tables.py          # baixa e gera o JSON
    python scripts/mortality_tables.py --dry    # mostra o que faria sem salvar
"""

import json
import csv
import urllib.request
import urllib.error
import ssl
import io
import argparse
from pathlib import Path

# Windows often lacks root certs for urllib; disable verification for public data
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ── Configuração de tábuas ────────────────────────────────────────────────────
TABLES = [
    {"id": "BRA", "name": "Brasil",        "year": "2022",    "url": "https://www.lifetable.de/File/GetDocument/data/BRA/BRA000020222022CU1.txt"},
    {"id": "JPN", "name": "Japão",         "year": "2022",    "url": "https://www.lifetable.de/File/GetDocument/data/JPN/JPN000020222022CU1.txt"},
    {"id": "USA", "name": "EUA",           "year": "2021",    "url": "https://www.lifetable.de/File/GetDocument/data/USA/USA000020212021CU1.txt"},
    {"id": "GBR", "name": "Reino Unido",   "year": "2020-22", "url": "https://www.lifetable.de/File/GetDocument/data/GBR/GBR000020202022CU1.txt"},
    {"id": "AUS", "name": "Austrália",     "year": "2020-22", "url": "https://www.lifetable.de/File/GetDocument/data/AUS/AUS000020202022CU1.txt"},
    {"id": "DEU", "name": "Alemanha",      "year": "2020-22", "url": "https://www.lifetable.de/File/GetDocument/data/DEU/DEU000020202022CU1.txt"},
    {"id": "FRA", "name": "França",        "year": "2020-22", "url": "https://www.lifetable.de/File/GetDocument/data/FRA/FRA000020202022CU1.txt"},
    {"id": "MEX", "name": "México",        "year": "2010",    "url": "https://www.lifetable.de/File/GetDocument/data/MEX/MEX000020102010AU1.txt"},
    {"id": "ZAF", "name": "África do Sul", "year": "2006-08", "url": "https://www.lifetable.de/File/GetDocument/data/ZAF/ZAF000020062008CU1.txt"},
]

SEX_MAP = {"1": "M", "2": "F"}
SEX_LABEL = {"M": "Masculino", "F": "Feminino"}

# Colunas do HLD (0-indexed):
# 0=Country, 1=Region, 2=Residence, 3=Ethnicity, 4=SocDem, 5=Version,
# 6=Ref-ID, 7=Year1, 8=Year2, 9=TypeLT, 10=Sex, 11=Age, 12=AgeInt,
# 13=m(x), 14=q(x), 15=l(x), 16=d(x), 17=L(x), 18=T(x), 19=e(x), 20=e(x)Orig


def parse_float(s):
    try:
        v = float(s.strip())
        return round(v, 6)
    except (ValueError, AttributeError):
        return None


def parse_table(content: str, country_name: str, year: str, iso3: str) -> dict:
    """Parse HLD txt content, returns dict keyed by table_id (e.g. BRA_M, BRA_F)."""
    result = {}
    by_sex = {}  # sex -> {ages:[], qx:[], lx:[], dx:[], ex:[]}

    reader = csv.reader(io.StringIO(content))
    header_skipped = False
    for row in reader:
        if not header_skipped:
            # First row is header
            if row and row[0].strip().lower() in ('country', 'cntr', iso3.lower()):
                header_skipped = True
            elif row and not row[0].strip().startswith('#'):
                # Some files have no explicit header, try to detect
                # If first col looks like a country code, it's data
                if len(row) >= 20 and row[0].strip().isalpha() and len(row[0].strip()) == 3:
                    header_skipped = True
                else:
                    header_skipped = True
                    continue
            else:
                header_skipped = True
                continue

        if len(row) < 20:
            continue
        sex_raw = row[10].strip()
        sex = SEX_MAP.get(sex_raw)
        if not sex:
            continue

        age_raw = row[11].strip()
        # Some tables use '+' for open interval (e.g. '90+')
        if age_raw.endswith('+'):
            age = int(age_raw[:-1])
        else:
            try:
                age = int(age_raw)
            except ValueError:
                continue

        qx = parse_float(row[14])
        lx = parse_float(row[15])
        dx = parse_float(row[16])
        ex = parse_float(row[19])

        if sex not in by_sex:
            by_sex[sex] = {"ages": [], "qx": [], "lx": [], "dx": [], "ex": []}
        by_sex[sex]["ages"].append(age)
        by_sex[sex]["qx"].append(qx)
        by_sex[sex]["lx"].append(lx)
        by_sex[sex]["dx"].append(dx)
        by_sex[sex]["ex"].append(ex)

    for sex, data in by_sex.items():
        if not data["ages"]:
            continue
        table_id = f"{iso3}_{sex}"
        e0 = data["ex"][0] if data["ex"] else None
        result[table_id] = {
            "id": table_id,
            "name": f"{country_name} {year} — {SEX_LABEL[sex]}",
            "country": country_name,
            "iso3": iso3,
            "year": year,
            "sex": sex,
            "sex_label": SEX_LABEL[sex],
            "e0": round(e0, 2) if e0 else None,
            "max_age": max(data["ages"]),
            "ages": data["ages"],
            "qx": data["qx"],
            "lx": data["lx"],
            "dx": data["dx"],
            "ex": data["ex"],
        }

    return result


def download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ReservingToolkit/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        raw = resp.read()
        # Try UTF-8, fallback to latin-1
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    all_tables = {}
    for cfg in TABLES:
        iso3 = cfg["id"]
        print(f"  [{iso3}] {cfg['name']} {cfg['year']} ...", end=" ", flush=True)
        try:
            content = download(cfg["url"])
            tables = parse_table(content, cfg["name"], cfg["year"], iso3)
            for k, v in tables.items():
                print(f"  → {k} ({v['max_age']+1} idades, e0={v['e0']})", end="")
            all_tables.update(tables)
            print()
        except Exception as e:
            print(f"ERRO: {e}")

    print(f"\nTotal: {len(all_tables)} tábuas ({len(TABLES)} países × 2 sexos)")

    if args.dry:
        print("[DRY-RUN] Nenhum arquivo salvo.")
        return

    out = Path(__file__).parent.parent / "data" / "mortality_tables.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"tables": all_tables}, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = out.stat().st_size / 1024
    print(f"Salvo: {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
