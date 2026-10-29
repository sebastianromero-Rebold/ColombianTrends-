"""Programa (o envía) el radar del día en Slack, al canal y por DM a las personas de config/slack.json.

Uso: python scripts/slack_send.py [AAAA-MM-DD] [--force] [--dry-run]
Requiere la variable SLACK_BOT_TOKEN (scopes: chat:write, chat:write.public, im:write).
Colombia no tiene horario de verano, así que la hora local es siempre UTC-5."""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOGOTA = timezone(timedelta(hours=-5))
LOG = ROOT / "data" / "slack_log.json"
DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
ARROW = {"subiendo": "↗ subiendo", "pico": "▲ en pico", "estable": "→ estable", "bajando": "↘ bajando"}


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cut(s, n):
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def bar(n):
    return "●" * n + "○" * (5 - n)


def fmt_num(v):
    if v is None:
        return "n/d"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} M".replace(".", ",")
    if v >= 1_000:
        return f"{v / 1_000:.0f} mil"
    return str(int(v))


def links(examples):
    return " · ".join(f"<{e['url']}|{esc(e.get('platform') or i + 1)}>" for i, e in enumerate(examples[:5]))


def section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": cut(text, 2990)}}


def metrics_line(m):
    basis = " (muestra)" if m.get("basis") == "muestra" else ""
    line = (f"_Menciones{basis}_ {fmt_num(m.get('mentions'))} · _Autores_ {fmt_num(m.get('authors'))} · "
            f"_Alcance potencial_ {fmt_num(m.get('potential_reach'))}")
    if m.get("search_volume"):
        line += f" · _Búsquedas Google_ {esc(m['search_volume'])}"
    if m.get("visible_engagement"):
        line += f"\n{esc(cut(m['visible_engagement'], 180))}"
    return line


def item_block(i, it, head_extra, lines_extra, with_links):
    lines = [f"*{i}. {esc(it.get('title') or it.get('name'))}*  {bar(it['strength'])}  "
             f"{ARROW.get(it['momentum'], '')}{head_extra}",
             esc(cut(it.get("description") or it.get("why_trending"), 300))]
    lines += [x for x in lines_extra if x]
    lines.append(metrics_line(it.get("metrics") or {}))
    if with_links and it.get("examples"):
        lines.append("Ejemplos: " + links(it["examples"]))
    return section("\n".join(lines))


def intent_line(p):
    pi = p.get("purchase_intent") or {}
    if not pi.get("level"):
        return None
    icon = {"alta": "🟢", "media": "🟡", "baja": "⚪"}.get(pi["level"], "")
    return f"_Intención de compra:_ {icon} {esc(pi['level'])} — {esc(cut(pi.get('evidence'), 200))}"


SECTIONS = [  # (clave, título, máximo de elementos en Slack)
    ("national_trends", "🇨🇴  1. Tendencias nacionales", 6),
    ("homecenter_trends", "🛠️  2. Tendencias de la categoría Homecenter", 6),
    ("products", "🔥  3. Productos ganando relevancia", 7),
    ("white_goods", "🧊  4. Línea blanca", 5),
]


def overview(r):
    """Cifras generales del día: suma de la muestra de todas las secciones."""
    tot = {"mentions": 0, "authors": 0, "potential_reach": 0}
    has = False
    for key, _, _ in SECTIONS:
        for it in r.get(key) or []:
            m = it.get("metrics") or {}
            for k in tot:
                if isinstance(m.get(k), (int, float)):
                    tot[k] += m[k]
                    has = True
    return tot if has else None


def examples_table(r):
    """Un solo cuadro con todos los ejemplos: sección, nombre, red, enlace y alcance."""
    head = ["Sección", "Tendencia / producto", "Red", "Enlace", "Alcance"]
    rows = [[{"type": "raw_text", "text": h} for h in head]]
    short = {"national_trends": "Nacional", "homecenter_trends": "Homecenter", "products": "Producto",
             "white_goods": "Línea blanca"}
    for key, _, limit in SECTIONS:
        for it in (r.get(key) or [])[:limit]:
            for e in it.get("examples") or []:
                reach = fmt_num(e.get("reach"))
                if e.get("reach") and e.get("reach_basis"):
                    reach += f" {e['reach_basis']}"
                rows.append([
                    {"type": "raw_text", "text": short[key]},
                    {"type": "raw_text", "text": cut(it.get("title") or it.get("name"), 60)},
                    {"type": "raw_text", "text": str(e.get("platform") or "-")},
                    {"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": [
                        {"type": "link", "url": e["url"], "text": "Ver publicación"}]}]},
                    {"type": "raw_text", "text": reach},
                ])
    if len(rows) == 1:
        return None
    return {"type": "table", "column_settings": [None, {"is_wrapped": True}, None, None, {"align": "right"}],
            "rows": rows[:100]}


def build_blocks(r, dashboard_url, with_table=True):
    d = datetime.strptime(r["date"], "%Y-%m-%d")
    title = f"📡 Radar de tendencias · {DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    summary = "\n".join(f"• {esc(s)}" for s in (r.get("summary") or []))
    tot = overview(r)
    totals = (f"\n\n📊 *Cifras generales (muestra del día):* {fmt_num(tot['mentions'])} menciones · "
              f"{fmt_num(tot['authors'])} autores · {fmt_num(tot['potential_reach'])} de alcance potencial"
              if tot else "")
    blocks.append(section(f"*{esc(r['headline'])}*\n{summary}{totals}"))
    table = examples_table(r) if with_table else None

    for key, label, limit in SECTIONS:
        items = (r.get(key) or [])[:limit]
        if not items:
            continue
        blocks += [{"type": "divider"}, section(f"*{label}*")]
        for i, it in enumerate(items, 1):
            platforms = f"  ·  {esc(', '.join(it.get('platforms') or []))}" if it.get("platforms") else ""
            if key == "national_trends":
                flag = " ⚠️ _no usar para marca_" if it.get("brand_safety") == "evitar" else ""
                head, extra = platforms, [f"_Ángulo de marca:_ {esc(cut(it.get('brand_angle'), 220))}{flag}"]
            elif key == "homecenter_trends":
                head = platforms
                extra = [f"`{esc(it.get('subcategory'))}`  _Oportunidad:_ {esc(cut(it.get('opportunity'), 240))}"]
            else:
                head = f"  ·  `{esc(it.get('subcategory'))}` · {esc(it.get('signal'))}"
                extra = [intent_line(it)]
                if it.get("drivers"):
                    extra.append(f"_Qué lo impulsa:_ {esc(cut(' · '.join(it['drivers']), 240))}")
                extra.append(f"_Idea:_ {esc(cut(it.get('content_idea'), 220))}"
                             + (f"  ·  _{esc(it.get('homecenter_availability'))}_"
                                if it.get("homecenter_availability") else ""))
            blocks.append(item_block(i, it, head, extra, table is None))

    blocks += [{"type": "divider"}, section("*💡  5. Recomendaciones de contenido para Homecenter*")]
    prio = {"alta": "🔴", "media": "🟠", "baja": "⚪"}
    for rec in (r.get("recommendations") or [])[:6]:
        channels = [c for c in rec.get("channels") or [] if c != rec.get("format")]
        lines = [f"{prio.get(rec.get('priority'), '•')} *{esc(rec['title'])}*  ·  {esc(rec.get('format'))}"
                 + (f" en {esc(', '.join(channels))}" if channels else "") + f"  ·  _{esc(rec.get('timing'))}_",
                 esc(cut(rec.get("description"), 380))]
        if rec.get("hook"):
            lines.append(f"_Gancho:_ “{esc(cut(rec['hook'], 160))}”")
        vh = rec.get("visual_hook") or {}
        if vh.get("idea") or vh.get("category"):
            label = esc(cut(vh.get("idea") or vh.get("category"), 160))
            lines.append("_Hook visual:_ " + (f"<{vh['url']}|{label}>" if vh.get("url") else label))
        if rec.get("products_to_feature"):
            lines.append(f"_Productos:_ {esc(', '.join(rec['products_to_feature']))}")
        if rec.get("why"):
            lines.append(f"_Por qué ahora:_ {esc(cut(rec['why'], 220))}")
        blocks.append(section("\n".join(lines)))

    if table:
        blocks += [{"type": "divider"}, section("*📎  Cuadro de ejemplos*"), table]
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                   "Fuentes: Google Trends, X, YouTube, Mercado Libre, autocompletar de Google y publicaciones "
                   "públicas de redes. Menciones, autores y alcance son de la *muestra* de publicaciones encontradas "
                   "ese día, no del total de la conversación; n/d = sin dato. La fuerza (●) es la estimación del analista."}]})
    if dashboard_url:
        blocks.append({"type": "actions", "elements": [{"type": "button", "style": "primary",
                       "text": {"type": "plain_text", "text": "Ver dashboard e histórico"},
                       "url": f"{dashboard_url}#/dia/{r['date']}"}]})
    return title, blocks


def slack(method, token, payload):
    req = urllib.request.Request(f"https://slack.com/api/{method}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data.get('error')} {data.get('response_metadata', '')}")
    return data


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force, dry = "--force" in sys.argv, "--dry-run" in sys.argv
    # --only=U123: envío de prueba inmediato solo a esa persona o canal; no toca el registro de envíos.
    only = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=") and a != "--only="), None)
    reports = sorted((ROOT / "data" / "reports").glob("*.json"))
    path = ROOT / "data" / "reports" / f"{args[0]}.json" if args else reports[-1]
    report = json.loads(path.read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / "config" / "slack.json").read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    date = report["date"]

    title, blocks = build_blocks(report, cfg.get("dashboard_url"))
    if dry:
        print(json.dumps({"text": title, "blocks": blocks}, ensure_ascii=False, indent=1))
        print(f"{len(blocks)} bloques", file=sys.stderr)
        return
    if only:
        token = os.environ["SLACK_BOT_TOKEN"]
        ch = slack("conversations.open", token, {"users": only})["channel"]["id"] if only.startswith("U") else only
        try:
            slack("chat.postMessage", token, {"channel": ch, "text": title, "blocks": blocks,
                                              "unfurl_links": False, "unfurl_media": False})
            print(f"Prueba enviada a {only} con el cuadro de ejemplos.")
        except RuntimeError as e:
            print(f"Slack rechazó el mensaje con cuadro ({e}); se prueba sin tabla.")
            _, plain = build_blocks(report, cfg.get("dashboard_url"), with_table=False)
            slack("chat.postMessage", token, {"channel": ch, "text": title, "blocks": plain,
                                              "unfurl_links": False, "unfurl_media": False})
            print(f"Prueba enviada a {only} sin tabla.")
        return
    already = set() if force else set(log.get(date, {}).get("targets", []))
    now = datetime.now(BOGOTA)
    if date != now.strftime("%Y-%m-%d") and not force:
        print(f"El reporte es del {date} y hoy es {now:%Y-%m-%d}: no se envía (usa --force).")
        return
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("Falta SLACK_BOT_TOKEN: no se envía nada.")
        sys.exit(1)

    hh, mm = map(int, cfg.get("send_at", "08:00").split(":"))
    send_at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    schedule = send_at - now > timedelta(minutes=2) and date == now.strftime("%Y-%m-%d")
    targets = list(cfg.get("channels") or [])
    for user in cfg.get("users") or []:
        targets.append(slack("conversations.open", token, {"users": user})["channel"]["id"])
    if not targets:
        print("config/slack.json no tiene canales ni usuarios.")
        sys.exit(1)
    # Solo los destinatarios que aún no lo tienen: agregar a alguien a mitad del día le envía el radar de hoy.
    targets = [t for t in targets if t not in already]
    if not targets:
        print(f"El radar del {date} ya se envió/programó a todos: {log[date]['status']}. Usa --force para reenviar.")
        return

    sent, failed = [], []
    _, plain_blocks = build_blocks(report, cfg.get("dashboard_url"), with_table=False)
    method = "chat.scheduleMessage" if schedule else "chat.postMessage"
    for ch in targets:
        payload = {"channel": ch, "text": title, "blocks": blocks, "unfurl_links": False, "unfurl_media": False}
        if schedule:
            payload["post_at"] = int(send_at.timestamp())
        try:
            try:
                slack(method, token, payload)
            except RuntimeError as e:
                # Plan B: si Slack no acepta el cuadro, se envía con los enlaces dentro de cada tendencia.
                if "invalid_blocks" not in str(e) or plain_blocks == blocks:
                    raise
                print(f"Slack rechazó el cuadro ({e}); se envía sin tabla.")
                slack(method, token, {**payload, "blocks": plain_blocks})
            sent.append(ch)
        except RuntimeError as e:
            failed.append(f"{ch}: {e}")
    status = f"programado {send_at:%H:%M}" if schedule else f"enviado {now:%H:%M}"
    log[date] = {"status": status, "targets": sorted(already | set(sent)), "failed": failed,
                 "at": now.isoformat(timespec="seconds")}
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{status} a {len(sent)} destinos" + (f"; fallaron: {failed}" if failed else ""))
    if failed and not sent:
        sys.exit(1)


if __name__ == "__main__":
    main()
