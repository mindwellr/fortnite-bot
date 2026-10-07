# Fortnite Bot (UEFN stats)

Bot de Discord para registrar las stats de tu mapa de UEFN.

## Comandos

| Comando | Qué hace |
|---|---|
| `/verify` | Vincula tu cuenta de Epic Games (la que tienes conectada en Discord). |
| `/addplayer elims playtime` | Sube tus stats. Requiere `/verify`. Se guarda siempre el valor más alto y solo se puede actualizar una vez al día. |
| `/stats [epic_id]` | Muestra las stats de un jugador (sin Epic ID muestra las tuyas). |
| `/topelims`, `/topplaytime` | Top 10. ✅ = cuenta de Epic verificada. |
| `/removeplayer epic_id` | Solo admins (permiso "Gestionar servidor"). Borra un jugador. |

Los mensajes salen en español o inglés según el idioma de Discord de cada usuario.

## Puesta en marcha (gratis)

### 1. Base de datos en Neon
1. Crea una cuenta en <https://neon.tech> y un proyecto.
2. Copia la **Connection string** (empieza por `postgresql://`). Es tu `DATABASE_URL`.

### 2. Página de verificación (GitHub Pages)
1. En GitHub: **Settings → Pages**.
2. En **Source** elige **Deploy from a branch**, rama `main`, carpeta `/docs`, y pulsa **Save**.
3. En unos minutos la página estará en <https://mindwellr.github.io/fortnite-bot/>.

### 3. Discord Developer Portal (<https://discord.com/developers/applications>)
1. Abre tu aplicación → **OAuth2**.
2. En **Redirects** añade exactamente `https://mindwellr.github.io/fortnite-bot/` y guarda.
3. Copia el **Client Secret** (pulsa *Reset Secret* si no lo ves). Es tu `DISCORD_CLIENT_SECRET`.
4. En **Bot**, copia el token (o pulsa *Reset Token*). Es tu `DISCORD_TOKEN`.

### 4. Hosting del bot
1. Sube el código al hosting (o conéctalo a este repositorio de GitHub).
2. Crea un archivo `.env` junto a `bot.py` copiando `.env.example` y rellena los valores.
   **Nunca subas el `.env` a GitHub**: este repositorio es público.
3. Archivo de inicio: `bot.py`. Las dependencias están en `requirements.txt`.
