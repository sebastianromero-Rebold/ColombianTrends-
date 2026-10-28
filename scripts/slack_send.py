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


def trend_block(i, t, extra):
    m = t.get("metrics") or {}
    lines = [f"*{i}. {esc(t['title'])}*  {bar(t['strength'])}  {ARROW.get(t['momentum'], '')}"
             + (f"  ·  {esc(', '.join(t.get('platforms') or []))}" if t.get("platforms") else ""),
             esc(cut(t.get("description"), 320))]
    if extra:
        lines.append(extra)
    lines.append(f"_Menciones_ {fmt_num(m.get('mentions'))} · _Autores_ {fmt_num(m.get('authors'))} · "
                 f"_Alcance_ {fmt_num(m.get('potential_reach'))}"
                 + (f" · {esc(cut(m.get('visible_engagement'), 160))}" if m.get("visible_engagement") else ""))
    if t.get("examples"):
        lines.append("Ejemplos: " + links(t["examples"]))
    return section("\n".join(lines))


def build_blocks(r, dashboard_url):
    d = datetime.strptime(r["date"], "%Y-%m-%d")
    title = f"📡 Radar de tendencias · {DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    summary = "\n".join(f"• {esc(s)}" for s in (r.get("summary") or []))
    blocks.append(section(f"*{esc(r['headline'])}*\n{summary}"))

    blocks += [{"type": "divider"}, section("*🇨🇴  1. Tendencias nacionales*")]
    for i, t in enumerate((r.get("national_trends") or [])[:6], 1):
        flag = " ⚠️ _no usar para marca_" if t.get("brand_safety") == "evitar" else ""
        blocks.append(trend_block(i, t, f"_Ángulo de marca:_ {esc(cut(t.get('brand_angle'), 220))}{flag}"))

    blocks += [{"type": "divider"}, section("*🛠️  2. Tendencias de la categoría Homecenter*")]
    for i, t in enumerate((r.get("homecenter_trends") or [])[:6], 1):
        blocks.append(trend_block(i, t, f"`{esc(t.get('subcategory'))}`  _Oportunidad:_ {esc(cut(t.get('opportunity'), 240))}"))

    blocks += [{"type": "divider"}, section("*🔥  3. Productos ganando relevancia*")]
    for i, p in enumerate((r.get("products") or [])[:8], 1):
        lines = [f"*{i}. {esc(p['name'])}*  {bar(p['strength'])}  {ARROW.get(p['momentum'], '')}  ·  "
                 f"`{esc(p.get('subcategory'))}` · {esc(p.get('signal'))}",
                 esc(cut(p.get("why_trending"), 260)),
                 f"_Idea:_ {esc(cut(p.get('content_idea'), 220))}"
                 + (f"  ·  _{esc(p.get('homecenter_availability'))}_" if p.get("homecenter_availability") else "")]
        if p.get("examples"):
            lines.append("Ejemplos: " + links(p["examples"]))
        blocks.append(section("\n".join(lines)))

    blocks += [{"type": "divider"}, section("*💡  4. Recomendaciones de contenido para Homecenter*")]
    prio = {"alta": "🔴", "media": "🟠", "baja": "⚪"}
    for i, rec in enumerate((r.get("recommendations") or [])[:6], 1):
        channels = [c for c in rec.get("channels") or [] if c != rec.get("format")]
        lines = [f"{prio.get(rec.get('priority'), '•')} *{esc(rec['title'])}*  ·  {esc(rec.get('format'))}"
                 + (f" en {esc(', '.join(channels))}" if channels else "") + f"  ·  _{esc(rec.get('timing'))}_",
                 esc(cut(rec.get("description"), 380))]
        if rec.get("hook"):
            lines.append(f"_Gancho:_ “{esc(cut(rec['hook'], 160))}”")
        if rec.get("products_to_feature"):
            lines.append(f"_Productos:_ {esc(', '.join(rec['products_to_feature']))}")
        if rec.get("why"):
            lines.append(f"_Por qué ahora:_ {esc(cut(rec['why'], 220))}")
        blocks.append(section("\n".join(lines)))

    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                   "Fuentes: búsqueda web y publicaciones públicas. Menciones, autores y alcance aparecen como "
                   "n/d cuando no hay una cifra publicada; la fuerza (●) es la estimación del analista."}]})
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
    for ch in targets:
        payload = {"channel": ch, "text": title, "blocks": blocks, "unfurl_links": False, "unfurl_media": False}
        try:
            if schedule:
                payload["post_at"] = int(send_at.timestamp())
                slack("chat.scheduleMessage", token, payload)
            else:
                slack("chat.postMessage", token, payload)
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
