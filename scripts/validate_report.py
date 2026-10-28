"""Valida un reporte diario del radar. Uso: python scripts/validate_report.py data/reports/AAAA-MM-DD.json"""
import json
import re
import sys
from pathlib import Path

SUBCATEGORIES = {"mejoramiento del hogar", "construcción", "remodelación", "decoración", "ferretería",
                 "herramientas", "muebles", "electrodomésticos", "jardinería", "DIY"}
MOMENTUM = {"subiendo", "pico", "estable", "bajando"}
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
URL = re.compile(r"^https?://[^\s]+\.[^\s]+")


def check_item(kind, i, item, errors, need_title="title"):
    where = f"{kind}[{i}]"
    if not SLUG.match(str(item.get("id", ""))):
        errors.append(f"{where}: id debe ser un slug (minúsculas y guiones)")
    if not item.get(need_title):
        errors.append(f"{where}: falta {need_title}")
    s = item.get("strength")
    if not isinstance(s, int) or not 1 <= s <= 5:
        errors.append(f"{where}: strength debe ser entero 1-5")
    if item.get("momentum") not in MOMENTUM:
        errors.append(f"{where}: momentum inválido ({item.get('momentum')})")
    ex = item.get("examples") or []
    if not ex:
        errors.append(f"{where}: necesita al menos 1 ejemplo con enlace")
    if len(ex) > 5:
        errors.append(f"{where}: máximo 5 ejemplos")
    for j, e in enumerate(ex):
        if not URL.match(str(e.get("url", ""))):
            errors.append(f"{where}.examples[{j}]: url inválida")
    m = item.get("metrics")
    if m is not None:
        for k in ("mentions", "authors", "potential_reach"):
            v = m.get(k)
            if v is not None and not isinstance(v, (int, float)):
                errors.append(f"{where}.metrics.{k}: debe ser número o null")
            if v is not None and not m.get("source"):
                errors.append(f"{where}.metrics: una cifra de {k} necesita 'source'")


def validate(report):
    errors = []
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(report.get("date", ""))):
        errors.append("date debe ser AAAA-MM-DD")
    if not report.get("headline"):
        errors.append("falta headline")
    for kind, minimum in (("national_trends", 3), ("homecenter_trends", 3), ("products", 3), ("recommendations", 3)):
        if len(report.get(kind) or []) < minimum:
            errors.append(f"{kind}: se esperan al menos {minimum}")
    ids = {}
    for kind in ("national_trends", "homecenter_trends"):
        for i, t in enumerate(report.get(kind) or []):
            check_item(kind, i, t, errors)
            ids[t.get("id")] = kind
    for i, t in enumerate(report.get("homecenter_trends") or []):
        if t.get("subcategory") not in SUBCATEGORIES:
            errors.append(f"homecenter_trends[{i}]: subcategory inválida ({t.get('subcategory')})")
    product_ids = set()
    for i, p in enumerate(report.get("products") or []):
        check_item("products", i, p, errors, need_title="name")
        product_ids.add(p.get("id"))
        if p.get("subcategory") not in SUBCATEGORIES:
            errors.append(f"products[{i}]: subcategory inválida ({p.get('subcategory')})")
    for i, r in enumerate(report.get("recommendations") or []):
        if not r.get("title") or not r.get("description"):
            errors.append(f"recommendations[{i}]: falta title o description")
        for tid in r.get("trend_ids") or []:
            if tid not in ids:
                errors.append(f"recommendations[{i}]: trend_id '{tid}' no existe en el reporte")
        for pid in r.get("product_ids") or []:
            if pid not in product_ids:
                errors.append(f"recommendations[{i}]: product_id '{pid}' no existe en el reporte")
    return errors


def main():
    path = Path(sys.argv[1])
    report = json.loads(path.read_text(encoding="utf-8"))
    if path.stem != report.get("date"):
        print(f"ERROR: el nombre del archivo ({path.stem}) no coincide con date ({report.get('date')})")
        sys.exit(1)
    errors = validate(report)
    if errors:
        print("ERRORES:\n- " + "\n- ".join(errors))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
