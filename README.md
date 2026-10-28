# Radar de tendencias · Colombia + Homecenter

Radar diario del equipo de Intelligence de Rebold: tendencias nacionales, tendencias de la
categoría de mejoramiento del hogar, productos que ganan relevancia en redes y recomendaciones
de contenido para Homecenter. Llega por Slack a las 8:00 a. m. y se acumula en un dashboard con
rankings por semana, mes y año.

**Dashboard:** https://sebastianromero-rebold.github.io/ColombianTrends-/

## Cómo funciona

```
6:30 a. m.  Rutina de Claude (claude.ai/code/routines)
            └─ sigue prompts/radar_diario.md: investiga en web y redes públicas,
               escribe data/reports/AAAA-MM-DD.json y lo sube a GitHub
            ↓  push
~7:00 a. m. GitHub Action .github/workflows/radar.yml
            ├─ valida el reporte (scripts/validate_report.py)
            ├─ regenera data/index.json y data/history.json (scripts/build_history.py)
            └─ programa el mensaje con chat.scheduleMessage (scripts/slack_send.py)
8:00 a. m.  Slack entrega el radar al canal y por DM a las personas de config/slack.json
```

Si el reporte llega después de las 8:00, el mensaje sale de inmediato. `data/slack_log.json`
evita envíos duplicados del mismo día.

## Qué datos son reales

Todo sale de búsquedas web y publicaciones públicas del día, con enlaces. Sin una herramienta de
social listening no hay conteo de **menciones, autores ni alcance**: esos campos aparecen como
`n/d`, salvo que una fuente publicada dé la cifra (se cita la fuente). Lo que sí se reporta es el
engagement visible de las publicaciones (vistas, likes, comentarios). La **fuerza** (1 a 5) es
una estimación del analista con la escala definida en el prompt, y es la base de los rankings.

Si más adelante se conecta una herramienta de social listening, los campos `metrics.mentions`,
`metrics.authors` y `metrics.potential_reach` ya existen en el esquema.

## Configuración

| Qué | Dónde |
| --- | --- |
| Destinatarios y hora de envío | `config/slack.json` (`channels`: IDs `C…`; `users`: IDs `U…`) |
| Token del bot de Slack | Secreto `SLACK_BOT_TOKEN` en Settings → Secrets and variables → Actions |
| App de Slack | Crear desde `slack-manifest.json` (scopes `chat:write`, `chat:write.public`, `im:write`) |
| Instrucciones del analista | `prompts/radar_diario.md` (la rutina lo lee cada día; editarlo cambia el reporte siguiente) |
| Dashboard | `index.html` en GitHub Pages (rama `main`, carpeta raíz) |

Para que el bot publique en un canal privado hay que invitarlo (`/invite @Radar Rebold`).

## Reenviar o probar

- Actions → **Radar diario** → *Run workflow*, con fecha y `force` para reenviar.
- Local: `python scripts/slack_send.py --dry-run` imprime los bloques de Slack sin enviar.
