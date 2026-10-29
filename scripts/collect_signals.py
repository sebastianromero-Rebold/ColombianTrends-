"""Recolecta señales públicas del día y las guarda en data/raw/AAAA-MM-DD/signals.json.

Corre en GitHub Actions antes del agente (5:45 a. m. Colombia). Solo usa fuentes públicas sin login:
- Google Trends "Trending now" Colombia (RSS): búsquedas en alza con volumen aproximado.
- Tendencias de X en Colombia (trends24.in): lo que es tendencia en X hora a hora.
- Autocompletar de Google y YouTube Colombia: las preguntas y búsquedas de la gente por categoría
  (la misma fuente que usa AnswerThePublic).
- Tendencias de Mercado Libre Colombia: búsquedas que más crecen, más deseadas y más populares.
Cada fuente falla por separado: si una no responde, se anota el error y se sigue con las demás."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}

# Semillas por subcategoría de Homecenter + línea blanca. Se consultan solas y con modificadores de intención.
SEEDS = {
    "remodelación": ["remodelar cocina", "remodelar baño", "remodelar apartamento"],
    "decoración": ["decoración sala", "decoración navidad", "ideas decoración"],
    "construcción": ["pintura para", "piso para", "impermeabilizante"],
    "ferretería": ["ferretería", "tornillos para"],
    "herramientas": ["taladro", "pulidora", "herramientas"],
    "muebles": ["mueble para", "closet", "escritorio"],
    "jardinería": ["plantas de interior", "jardín vertical", "materas"],
    "DIY": ["cómo hacer", "diy"],
    "mejoramiento del hogar": ["organizador", "lámpara", "cortinas"],
    "línea blanca": ["nevera", "lavadora", "estufa", "horno", "freidora de aire", "aire acondicionado",
                     "lavavajillas", "microondas", "secadora", "congelador"],
}
INTENT = ["", "mejor ", "precio ", "cómo "]


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def google_trends():
    xml = get("https://trends.google.com/trending/rss?geo=CO")
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for item in ET.fromstring(xml).iter("item"):
        news = [{"title": n.findtext("ht:news_item_title", namespaces=ns),
                 "url": n.findtext("ht:news_item_url", namespaces=ns),
                 "source": n.findtext("ht:news_item_source", namespaces=ns)}
                for n in item.findall("ht:news_item", ns)]
        out.append({"query": item.findtext("title"),
                    "approx_traffic": item.findtext("ht:approx_traffic", namespaces=ns),
                    "started": item.findtext("pubDate"), "news": news[:3]})
    return out


def x_trends():
    html = get("https://trends24.in/colombia/")
    # La primera lista es la hora más reciente; las siguientes, horas anteriores.
    cards = re.findall(r'<ol class=trend-card__list>(.*?)</ol>', html, re.S)
    hours = []
    for card in cards[:6]:
        items = []
        for li in re.findall(r"<li>(.*?)</li>", card, re.S):
            name = re.search(r"class=trend-link>([^<]+)</a>", li)
            count = re.search(r'tweet-count[^>]*data-count="?(\d*)"?', li)
            if name:
                items.append({"name": unescape(name.group(1)).strip(),
                              "tweets": int(count.group(1)) if count and count.group(1) else None})
        hours.append(items)
    if not hours:
        raise RuntimeError("trends24 cambió su HTML: no se encontraron listas")
    # Persistencia: cuántas de las últimas horas aparece cada tendencia (señal de fuerza).
    seen = {}
    for items in hours:
        for i, t in enumerate(items):
            s = seen.setdefault(t["name"], {"name": t["name"], "hours_in_top": 0, "best_rank": 99, "tweets": None})
            s["hours_in_top"] += 1
            s["best_rank"] = min(s["best_rank"], i + 1)
            s["tweets"] = s["tweets"] or t["tweets"]
    return sorted(seen.values(), key=lambda s: (-s["hours_in_top"], s["best_rank"]))[:40]


def suggest(q, ds=""):
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&hl=es&gl=co"
           + (f"&ds={ds}" if ds else "") + "&q=" + urllib.parse.quote(q))
    return json.loads(get(url))[1]


def autocomplete():
    out = {}
    for group, seeds in SEEDS.items():
        rows = []
        for seed in seeds:
            for prefix in INTENT if group in ("línea blanca", "herramientas") else INTENT[:2]:
                q = prefix + seed
                try:
                    rows.append({"query": q, "google": suggest(q), "youtube": suggest(q, "yt")})
                except Exception as e:  # noqa: BLE001 — una consulta fallida no tumba el resto
                    rows.append({"query": q, "error": str(e)})
                time.sleep(0.4)
        out[group] = rows
    return out


def parse_views(text):
    """'1,2 M de vistas' / '35 mil vistas' / '1.234 vistas' -> número aproximado."""
    if not text:
        return None
    t = text.lower().replace("\xa0", " ")
    m = re.search(r"([\d.,]+)\s*(mil\s*m\b|mil\b|m\b|k\b)?", t)
    if not m:
        return None
    n = m.group(1)
    mult = {"milm": 1e9, "m": 1e6, "mil": 1e3, "k": 1e3}.get((m.group(2) or "").replace(" ", ""), 1)
    # Sin sufijo es un entero con separadores de miles; con sufijo, la coma o el punto es decimal.
    n = re.sub(r"[.,]", "", n) if mult == 1 else n.replace(",", ".")
    try:
        return int(float(n) * mult)
    except ValueError:
        return None


def youtube_search(query):
    """Videos de YouTube subidos esta semana para la búsqueda, con vistas y canal (sin API key)."""
    url = ("https://www.youtube.com/results?gl=CO&hl=es&sp=EgIIAw%253D%253D&search_query="
           + urllib.parse.quote_plus(query))
    req = urllib.request.Request(url, headers={**UA, "Accept-Language": "es-CO,es;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", errors="replace")
    key = "var ytInitialData = "
    data, _ = json.JSONDecoder().raw_decode(html[html.index(key) + len(key):])
    videos = []

    def walk(o):
        if isinstance(o, dict):
            v = o.get("videoRenderer")
            if v and v.get("videoId"):
                views_text = (v.get("viewCountText") or {}).get("simpleText") or ""
                videos.append({
                    "url": f"https://www.youtube.com/watch?v={v['videoId']}",
                    "title": "".join(r.get("text", "") for r in v.get("title", {}).get("runs", [])),
                    "channel": ((v.get("ownerText") or {}).get("runs") or [{}])[0].get("text"),
                    "published": (v.get("publishedTimeText") or {}).get("simpleText"),
                    "views_text": views_text, "views": parse_views(views_text)})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(data)
    return videos[:15]


YOUTUBE_QUERIES = ["remodelación apartamento", "decoración navidad", "decoración hogar", "ideas para la casa",
                   "herramientas", "hazlo tú mismo hogar", "organización hogar", "jardín plantas",
                   "homecenter", "nevera", "lavadora", "freidora de aire", "electrodomésticos"]


def youtube(trend_terms):
    out = {}
    for q in YOUTUBE_QUERIES + trend_terms:
        try:
            out[q] = youtube_search(q + " colombia" if q not in trend_terms else q)
        except Exception as e:  # noqa: BLE001
            out[q] = {"error": str(e)}
        time.sleep(0.5)
    return out


def new_suggestions(today, yesterday):
    """Sugerencias de autocompletar que no estaban ayer: búsquedas que empiezan a aparecer."""
    prev = set()
    for rows in (yesterday or {}).values():
        for r in rows:
            prev.update(r.get("google", []) + r.get("youtube", []))
    out = {}
    for group, rows in today.items():
        fresh = sorted({s for r in rows for s in r.get("google", []) + r.get("youtube", []) if s not in prev})
        if fresh:
            out[group] = fresh
    return out


def mercadolibre():
    html = get("https://tendencias.mercadolibre.com.co/")
    key = 'melidata("add","event_data",'
    i = html.find(key)
    if i < 0:
        raise RuntimeError("Mercado Libre cambió su HTML: no se encontró event_data")
    data, _ = json.JSONDecoder().raw_decode(html[i + len(key):])
    return {k: [x["keyword"] for x in v] for k, v in data.items()
            if isinstance(v, list) and v and isinstance(v[0], dict) and "keyword" in v[0]}


def main():
    now = datetime.now(timezone(timedelta(hours=-5)))
    date = sys.argv[1] if len(sys.argv) > 1 else now.strftime("%Y-%m-%d")
    result = {"date": date, "collected_at": now.isoformat(timespec="seconds"), "errors": {}}
    for name, fn in (("google_trends", google_trends), ("x_trends", x_trends),
                     ("mercadolibre", mercadolibre), ("autocomplete", autocomplete)):
        try:
            result[name] = fn()
            print(f"{name}: ok")
        except Exception as e:  # noqa: BLE001
            result["errors"][name] = str(e)
            print(f"{name}: ERROR {e}")
    # YouTube: categorías fijas + las 5 búsquedas más fuertes del día en Google y las 5 de X.
    trend_terms = [g["query"] for g in (result.get("google_trends") or [])[:5]]
    trend_terms += [x["name"] for x in (result.get("x_trends") or [])[:5]]
    result["youtube"] = youtube(trend_terms)
    print("youtube: ok")
    yesterday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_file = ROOT / "data" / "raw" / yesterday / "signals.json"
    if prev_file.exists() and result.get("autocomplete"):
        prev = json.loads(prev_file.read_text(encoding="utf-8")).get("autocomplete")
        result["autocomplete_new"] = new_suggestions(result["autocomplete"], prev)
    out = ROOT / "data" / "raw" / date
    out.mkdir(parents=True, exist_ok=True)
    (out / "signals.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Guardado en {out / 'signals.json'}")


if __name__ == "__main__":
    main()
