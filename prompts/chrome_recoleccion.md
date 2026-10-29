# Recolección en Chrome — publicaciones de TikTok, Instagram y Facebook

Corre en el computador de Sebastián a las 5:50 a. m. con Claude in Chrome. Su único trabajo es
encontrar publicaciones **reales y recientes** de redes sociales en Colombia, leer su alcance
visible y guardarlas en `data/raw/AAAA-MM-DD/chrome.json` para que el agente del radar (6:30 a. m.)
las use como ejemplos y métricas. No analiza ni redacta el radar.

## Reglas

- Solo navegar y leer. No iniciar sesión, no escribir contraseñas, no dar like, no comentar, no
  seguir cuentas, no aceptar nada más allá de cerrar avisos de cookies (rechazando lo opcional).
- Si aparece un CAPTCHA o un muro de inicio de sesión, no lo resuelvas: anota el error en
  `errors` y sigue con la siguiente fuente.
- Usa una sola pestaña nueva y ciérrala al terminar.
- Guarda solo lo que viste: si una cifra no aparece, déjala en `null`. Nunca escribas una URL que
  no hayas visto.

## Pasos

1. Prepara el repositorio (ruta local `C:\Users\sebastian.romero\Rebold\ColombianTrends`):
   ```bash
   cd /c/Users/sebastian.romero/Rebold/ColombianTrends && git pull -q
   D=$(TZ=America/Bogota date +%F)
   ```
2. Arma la lista de búsquedas (entre 12 y 16):
   - Si existe `data/raw/$D/signals.json`, toma las 4 primeras `google_trends[].query` y las 4
     primeras `x_trends[].name` que no sean temas sensibles (política, tragedias, orden público).
   - Agrega estas fijas: `remodelación apartamento`, `decoración navidad casa`, `hack hogar`,
     `herramientas recomendadas`, `homecenter`, `nevera`, `lavadora`, `freidora de aire`.
3. Para cada búsqueda abre Google con filtro de la última semana y Colombia:
   `https://www.google.com/search?hl=es&gl=co&tbs=qdr:w&q=(site:tiktok.com OR site:instagram.com OR site:facebook.com) <búsqueda> colombia`
   y extrae los enlaces con JavaScript:
   ```js
   [...new Set([...document.querySelectorAll('a[href]')].map(a => a.href)
     .filter(h => /tiktok\.com\/@[^/]+\/(video|photo)\/|instagram\.com\/(p|reel|reels)\/|facebook\.com\/.+\/(posts|videos|reel)|facebook\.com\/(reel|watch)/.test(h)))].slice(0, 8)
   ```
   Guarda también el título y el fragmento que muestra Google para cada enlace si los puedes
   leer. Espera 3 a 5 segundos entre búsquedas.
4. Abre hasta **25 videos de TikTok** (priorizando los de distintas búsquedas) y lee sus cifras:
   ```js
   (() => { const it = JSON.parse(document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__').textContent)
       .__DEFAULT_SCOPE__['webapp.video-detail'].itemInfo.itemStruct;
     return { views: +it.stats.playCount, likes: +it.stats.diggCount, comments: +it.stats.commentCount,
              shares: +it.stats.shareCount, followers: it.authorStats && +it.authorStats.followerCount,
              date: new Date(it.createTime * 1000).toISOString().slice(0, 10), text: it.desc.slice(0, 200) }; })()
   ```
   El autor sale de la URL (`tiktok.com/@autor/...`).
5. Abre hasta **10 publicaciones de Instagram y 5 de Facebook** y lee lo que se vea sin iniciar
   sesión (por ejemplo `document.querySelector('meta[property="og:description"]')?.content`, que
   suele traer likes y comentarios). Si pide iniciar sesión, deja las cifras en `null`.
6. AnswerThePublic (opcional): abre `https://answerthepublic.com/es`. Si ya hay una sesión
   iniciada, busca **una sola** semilla del día (lunes `nevera`, martes `remodelar`, miércoles
   `decoración`, jueves `herramientas`, viernes `lavadora`, sábado `jardín`, domingo `organizar casa`)
   con idioma español y país Colombia, y guarda las preguntas que aparezcan. Si no hay sesión o no
   quedan búsquedas gratis, sáltalo y anótalo en `errors`.
7. Escribe `data/raw/$D/chrome.json` con este formato y súbelo:
   ```json
   {
     "date": "AAAA-MM-DD",
     "collected_at": "AAAA-MM-DDTHH:MM:SS-05:00",
     "queries": ["..."],
     "posts": [
       { "query": "remodelación apartamento", "platform": "TikTok", "url": "https://www.tiktok.com/@cuenta/video/123",
         "author": "@cuenta", "date": "2026-10-23", "text": "Descripción o fragmento",
         "views": 27300, "likes": 247, "comments": 12, "shares": 96, "followers": 41200 }
     ],
     "answerthepublic": { "seed": "nevera", "questions": ["¿qué nevera comprar…?"] },
     "errors": ["Instagram pidió iniciar sesión en 7 de 10 publicaciones"]
   }
   ```
   ```bash
   git add data/raw/$D/chrome.json
   git commit -m "Señales de Chrome $D"
   git pull --rebase -q origin main && git push -q origin main
   ```

Termina con una línea: cuántas publicaciones por red, cuántas con cifras y si hubo errores.
