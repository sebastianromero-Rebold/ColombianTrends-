"""Regenera data/index.json y data/history.json a partir de data/reports/*.json.

history.json es la vista compacta que usa el dashboard para los rankings por semana, mes y año
(y que el agente consulta para reutilizar ids)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "data" / "reports"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_report import validate  # noqa: E402


def main():
    dates, trends, products = [], [], []
    for path in sorted(REPORTS.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        errors = validate(report)
        if errors:
            print(f"Omitiendo {path.name}: {len(errors)} errores ({errors[0]})")
            continue
        d = report["date"]
        dates.append({"date": d, "headline": report.get("headline", ""),
                      "counts": {k: len(report.get(k) or []) for k in
                                 ("national_trends", "homecenter_trends", "products", "recommendations")}})
        for kind, scope in (("national_trends", "nacional"), ("homecenter_trends", "homecenter")):
            for t in report.get(kind) or []:
                trends.append({"date": d, "id": t["id"], "scope": scope, "title": t["title"],
                               "group": t.get("subcategory") if scope == "homecenter" else t.get("topic"),
                               "strength": t["strength"], "momentum": t["momentum"],
                               "platforms": t.get("platforms") or []})
        for p in report.get("products") or []:
            products.append({"date": d, "id": p["id"], "name": p["name"], "group": p.get("subcategory"),
                             "signal": p.get("signal"), "strength": p["strength"], "momentum": p["momentum"]})
    out = ROOT / "data"
    (out / "index.json").write_text(json.dumps({"reports": dates[::-1]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "history.json").write_text(json.dumps({"trends": trends, "products": products}, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"{len(dates)} reportes, {len(trends)} registros de tendencias, {len(products)} de productos")


if __name__ == "__main__":
    main()
