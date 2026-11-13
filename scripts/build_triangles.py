"""
scripts/build_triangles.py — Script principal do pipeline de triângulos.

Combina:
  1. Triângulos já existentes em data/triangles.json
  2. Triângulos CAS/NAIC (baixados de casact.org)
  3. Triângulos SUSEP/Brasil (embutidos + API)
  4. Triângulos internacionais (embutidos da literatura)

Saída: data/triangles.json atualizado

Uso:
    # Só internacionais + SUSEP embutido (sem internet necessária para esses)
    python scripts/build_triangles.py --embed-only

    # Tudo: baixa CAS da internet + SUSEP + internacionais
    python scripts/build_triangles.py --all

    # Só CAS (requer internet)
    python scripts/build_triangles.py --cas

    # Ver o que vai ser adicionado sem salvar
    python scripts/build_triangles.py --dry-run --all

Opções:
    --all           Roda todos os módulos (padrão)
    --embed-only    Só triângulos embutidos (sem downloads)
    --cas           Só CAS/NAIC
    --susep         Só SUSEP
    --international Só triângulos internacionais
    --dry-run       Mostra o que seria adicionado sem salvar
    --backup        Faz backup do triangles.json atual antes de sobrescrever
"""

import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

DATA_DIR     = Path(__file__).parent.parent / "data"
TRIANGLES_JSON = DATA_DIR / "triangles.json"


def load_existing() -> dict:
    with open(TRIANGLES_JSON, encoding="utf-8") as f:
        return json.load(f)


def normalize_triangle(tri: dict) -> dict:
    """
    Garante que o triângulo tem a estrutura mínima esperada pelo index.html:
      - origins: list[str]
      - lags: list[int|str]
      - data: list[list[float|None]]
    Remove campos privados (_source, _lob, etc.) do output final (opcionais).
    """
    origins = [str(o) for o in tri["origins"]]
    lags = tri["lags"]
    data = tri["data"]
    out = {
        "origins": origins,
        "lags":    lags,
        "data":    data,
        "n":       len(origins),
        "m":       len(lags),
    }
    # Preservar prêmios ganhos se disponíveis (usados pelo BF/Cape Cod)
    if "earned_premiums" in tri:
        out["earned_premiums"] = tri["earned_premiums"]
    # Preservar metadados opcionais
    for k in ["_source", "_lob", "_type", "_unit", "_country"]:
        if k in tri:
            out[k] = tri[k]
    return out


def build_meta_js_snippet(new_keys: list, triangles: dict) -> str:
    """
    Gera o bloco JavaScript para adicionar ao TRIANGLE_META em index.html.
    Imprime no console para o usuário copiar.
    """
    lines = ["// ── Novos triângulos — adicionar ao TRIANGLE_META em index.html ──"]
    for k in new_keys:
        t = triangles.get(k, {})
        lob     = t.get("_lob", k)
        country = t.get("_country", "Internacional")
        typ     = t.get("_type", "incurred")
        source  = t.get("_source", "")
        n       = len(t.get("origins", []))
        m       = len(t.get("lags", []))
        has_prem = "earned_premiums" in t

        # Categorias
        cats = []
        if country == "Brasil":               cats.append("brasil")
        elif country == "Austrália":          cats.append("australia")
        elif country == "Alemanha":           cats.append("germany")
        elif country == "Reino Unido":        cats.append("uk")
        elif country == "França":             cats.append("france")
        elif "Lloyd" in country:              cats.append("lloyds")

        if "CAS_" in k:                       cats.append("naic")
        if "auto" in k.lower() or "kfz" in k.lower() or "motor" in k.lower(): cats.append("auto")
        if "rc" in k.lower() or "haft" in k.lower() or "liability" in k.lower(): cats.append("liability")
        if "wkcomp" in k.lower():             cats.append("wkcomp")
        if "medmal" in k.lower():             cats.append("medmal")
        if "prodliab" in k.lower():           cats.append("liability")
        if "marine" in k.lower():             cats.append("marine")
        if "dpvat" in k.lower():              cats.append("auto")
        if typ == "paid":                     cats.append("paid")
        elif typ == "incurred":               cats.append("incurred")

        tail = "Longa"
        tail_cls = "long"
        if any(x in k.lower() for x in ["ppauto", "auto", "kfz", "motor"]): tail="Curta";     tail_cls="short"
        if any(x in k.lower() for x in ["wkcomp", "dpvat"]):                tail="Média";     tail_cls="medium"
        if any(x in k.lower() for x in ["medmal", "prodliab", "marine"]):   tail="Muito Longa"; tail_cls="vlong"

        chars = [
            f"{n} anos de origem × {m} lags anuais",
            f"Fonte: {source[:80]}" if source else "",
            f"Prêmios ganhos disponíveis para Cape Cod ELR" if has_prem else "",
        ]
        chars = [c for c in chars if c]

        lines.append(f"  '{k}': {{")
        lines.append(f"    lob: '{lob}',")
        lines.append(f"    tail: '{tail}', tc: '{tail_cls}',")
        lines.append(f"    source: '{source[:100]}',")
        lines.append(f"    chars: {json.dumps(chars, ensure_ascii=False)},")
        lines.append(f"    use: 'Triângulo de {country} — {lob}.',")
        lines.append(f"    cats: {json.dumps(cats)},")
        lines.append(f"  }},")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build triangles.json")
    parser.add_argument("--all",           action="store_true")
    parser.add_argument("--embed-only",    action="store_true")
    parser.add_argument("--cas",           action="store_true")
    parser.add_argument("--susep",         action="store_true")
    parser.add_argument("--international", action="store_true")
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("--backup",        action="store_true", default=True)
    args = parser.parse_args()

    # Quais módulos rodar (padrão: tudo exceto CAS)
    run_embed = args.embed_only
    run_all   = args.all or (not args.cas and not args.susep and not args.international and not args.embed_only)
    run_cas   = args.cas   or (run_all and not run_embed)
    run_susep = args.susep or run_all or run_embed
    run_intl  = args.international or run_all or run_embed

    print("═" * 60)
    print("  Reserving Toolkit — Triangle Builder")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("═" * 60)

    # Carrega existentes
    print(f"\nCarregando {TRIANGLES_JSON.name} ...")
    existing = load_existing()
    triangles = dict(existing.get("triangles", {}))
    print(f"  Existentes: {len(triangles)} triângulos")

    new_triangles = {}

    # ── 1. CAS / NAIC ─────────────────────────────────────────────────────
    if run_cas:
        print("\n[1/3] CAS Reserve Data (requer internet) ...")
        try:
            import sys as _sys, os
            _sys.path.insert(0, str(Path(__file__).parent))
            from naic_cas import process_lob, LOB_CONFIG
            for lob in LOB_CONFIG:
                try:
                    result = process_lob(lob)
                    for k, v in result.items():
                        new_triangles[k] = normalize_triangle(v)
                except Exception as e:
                    print(f"  AVISO: {lob} falhou — {e}")
        except Exception as e:
            print(f"  ERRO no módulo CAS: {e}")
    else:
        print("\n[1/3] CAS — pulado (use --cas ou --all para baixar)")

    # ── 2. SUSEP / Brasil ─────────────────────────────────────────────────
    if run_susep:
        print("\n[2/3] SUSEP / Brasil ...")
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent))
            from susep import EMBEDDED_TRIANGLES
            for k, v in EMBEDDED_TRIANGLES.items():
                new_triangles[k] = normalize_triangle(v)
            print(f"  → {len(EMBEDDED_TRIANGLES)} triângulos SUSEP/Brasil adicionados")
        except Exception as e:
            print(f"  ERRO: {e}")
    else:
        print("\n[2/3] SUSEP — pulado")

    # ── 3. Internacionais ─────────────────────────────────────────────────
    if run_intl:
        print("\n[3/3] Triângulos internacionais ...")
        try:
            from international import INTERNATIONAL_TRIANGLES
            for k, v in INTERNATIONAL_TRIANGLES.items():
                new_triangles[k] = normalize_triangle(v)
            print(f"  → {len(INTERNATIONAL_TRIANGLES)} triângulos internacionais adicionados")
        except Exception as e:
            print(f"  ERRO: {e}")
    else:
        print("\n[3/3] Internacionais — pulado")

    # ── Merge ─────────────────────────────────────────────────────────────
    added_keys = [k for k in new_triangles if k not in triangles]
    updated_keys = [k for k in new_triangles if k in triangles]
    triangles.update(new_triangles)

    print(f"\n{'─'*60}")
    print(f"  Novos:        {len(added_keys)}")
    print(f"  Atualizados:  {len(updated_keys)}")
    print(f"  Total final:  {len(triangles)}")
    print(f"{'─'*60}")

    if added_keys:
        print("\nNovos triângulos:")
        for k in added_keys:
            t = triangles[k]
            n = len(t.get("origins", []))
            m = len(t.get("lags", []))
            country = t.get("_country", "")
            print(f"  + {k:45s} {n:2}×{m:2}  {country}")

    # ── Dry-run ou salvar ─────────────────────────────────────────────────
    if args.dry_run:
        print("\n[DRY-RUN] Nenhum arquivo foi modificado.")
    else:
        if args.backup and TRIANGLES_JSON.exists():
            backup = TRIANGLES_JSON.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            shutil.copy(TRIANGLES_JSON, backup)
            print(f"\nBackup: {backup.name}")

        out = {"triangles": triangles}
        with open(TRIANGLES_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        size_kb = TRIANGLES_JSON.stat().st_size / 1024
        print(f"Salvo: {TRIANGLES_JSON}  ({size_kb:.0f} KB)")

        # Gera snippet JS para TRIANGLE_META
        if added_keys:
            print("\n" + "═"*60)
            print("TRIANGLE_META — adicionar ao index.html (bloco JS):")
            print("═"*60)
            print(build_meta_js_snippet(added_keys, triangles))

    print("\nPronto.")


if __name__ == "__main__":
    main()
