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
SOCIAL = {"tiktok", "instagram", "facebook", "x", "twitter", "youtube", "pinterest", "reddit", "threads", "linkedin"}
INTENT = {"alta", "media", "baja"}


def is_social(platform):
    return str(platform or "").strip().lower() in SOCIAL


def check_item(kind, i, item, errors, warnings, need_title="title"):
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
        r = e.get("reach")
        if r is not None and not isinstance(r, (int, float)):
            errors.append(f"{where}.examples[{j}]: reach debe ser número o null")
    social = [e for e in ex if is_social(e.get("platform"))]
    if len(ex) < 3:
        warnings.append(f"{where}: solo {len(ex)} ejemplos (se piden 3 a 5)")
    if ex and not social:
        warnings.append(f"{where}: ningún ejemplo es de redes sociales")
    elif len({str(e.get('platform')).lower() for e in social}) < 2 and len(ex) >= 3:
        warnings.append(f"{where}: los ejemplos de redes son de una sola plataforma")
    pi = item.get("purchase_intent")
    if pi is not None and (not isinstance(pi, dict) or pi.get("level") not in INTENT or not pi.get("evidence")):
        errors.append(f"{where}: purchase_intent necesita level (alta/media/baja) y evidence")
    m = item.get("metrics")
    if m is not None:
        for k in ("mentions", "authors", "potential_reach"):
            v = m.get(k)
            if v is not None and not isinstance(v, (int, float)):
                errors.append(f"{where}.metrics.{k}: debe ser número o null")
            if v is not None and not (m.get("source") or m.get("basis") == "muestra"):
                errors.append(f"{where}.metrics: una cifra de {k} necesita 'source' o basis 'muestra'")
        if m.get("basis") not in (None, "muestra", "fuente publicada"):
            errors.append(f"{where}.metrics.basis: debe ser 'muestra' o 'fuente publicada'")


def validate(report, warnings=None):
    errors = []
    warnings = [] if warnings is None else warnings
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
            check_item(kind, i, t, errors, warnings)
            ids[t.get("id")] = kind
    for i, t in enumerate(report.get("homecenter_trends") or []):
        if t.get("subcategory") not in SUBCATEGORIES:
            errors.append(f"homecenter_trends[{i}]: subcategory inválida ({t.get('subcategory')})")
    product_ids = set()
    for kind in ("products", "white_goods"):
        for i, p in enumerate(report.get(kind) or []):
            check_item(kind, i, p, errors, warnings, need_title="name")
            product_ids.add(p.get("id"))
            if p.get("subcategory") not in SUBCATEGORIES:
                errors.append(f"{kind}[{i}]: subcategory inválida ({p.get('subcategory')})")
            if not p.get("purchase_intent"):
                warnings.append(f"{kind}[{i}]: falta purchase_intent")
    if not report.get("white_goods"):
        warnings.append("white_goods: no hay sección de línea blanca")
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
    warnings = []
    errors = validate(report, warnings)
    if warnings:
        print("AVISOS:\n- " + "\n- ".join(warnings))
    if errors:
        print("ERRORES:\n- " + "\n- ".join(errors))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
