# Fortnite Bot — contexto para Claude

Bot de Discord (discord.py, Python) que registra stats de un **mapa de UEFN**
(no de Fortnite Battle Royale): eliminaciones y tiempo jugado (horas y minutos).
Servidor de Discord: UNIWELL (`GUILD_ID` 1036557219585589319).

## Sobre el dueño
- No sabe programar: explícale todo en **español**, en lenguaje sencillo y con pasos concretos.
- Quiere que los cambios se apliquen directamente: crea el PR hacia `main` y fusiónalo
  (ya dio permiso), salvo que algo sea arriesgado o cambie cómo funciona el bot para los usuarios.
- No tiene presupuesto: todo debe seguir siendo **gratis** (sin tarjeta).

## Infraestructura
- **Hosting:** Wispbyte (plan gratis, hay que entrar al panel cada ~2 semanas). Solo tiene
  `start.py` y `.env`. `start.py` descarga la última versión de la rama `main` de GitHub
  en cada arranque, instala `requirements.txt` y ejecuta `bot.py`.
  → **Para aplicar un cambio: fusionar a `main` y que el dueño pulse Restart en Wispbyte.**
  La integración de Git del panel de Wispbyte no funciona (crea un `.git` vacío); no usarla.
- **Base de datos:** PostgreSQL en Neon (gratis). El bot crea/migra sus tablas solo en `_db_init()`.
- **Página de verificación:** GitHub Pages desde `docs/` → https://mindwellr.github.io/fortnite-bot/
  (por eso el repositorio debe seguir siendo **público**; GitHub Pages gratis no funciona en privados).
- **Variables (`.env` en Wispbyte, nunca en GitHub):** `DISCORD_TOKEN`, `DATABASE_URL`,
  `DISCORD_CLIENT_SECRET`, opcional `GUILD_ID` y `OAUTH_REDIRECT_URI`.
  El repositorio es público: **nunca** escribir claves en el código. El historial contiene un
  token antiguo ya inválido.

## Cómo funciona el bot (`bot.py`)
- Comandos (nombres en inglés): `/verify`, `/addplayer elims hours [minutes]`, `/stats [epic_id]`,
  `/topelims`, `/topplaytime`, `/removeplayer epic_id` (solo admins con "Gestionar servidor").
- **Verificación:** el usuario conecta Epic Games en Discord (Ajustes → Conexiones), usa `/verify`,
  autoriza OAuth2 (`identify connections`), la página de `docs/` le muestra el código y lo pega en
  un modal. El bot canjea el código, comprueba que es la misma cuenta de Discord, lee la conexión
  `epicgames` verificada, guarda la cuenta en `verified_accounts` y revoca el token.
- **Reglas de `/addplayer`:** solo con cuenta verificada (usa su Epic ID, no lo escribe el usuario);
  se guarda siempre el valor más alto; una actualización al día (UTC) y solo si algún valor sube.
  Los jugadores se identifican por `epic_account_id` (sobrevive a cambios de nombre).
- **Tiempo jugado:** se guarda en minutos (`playtime_minutes`) y se muestra como `5h 8m`.
  La columna antigua `playtime` (horas) ya no se usa.
- **Idiomas:** todos los mensajes están en `MESSAGES` con versión `en` y `es`; se elige según el
  idioma de Discord del usuario. Al añadir un mensaje, añadirlo en **ambos** idiomas.
  Las descripciones y los campos de los comandos se traducen al español con `COMMAND_TEXT_ES`
  (`SpanishTranslator`); al añadir o cambiar un comando, añadir ahí sus textos. Los nombres de los
  comandos se quedan en inglés.
- Los comandos se registran solo en el servidor (`GUILD_ID`) y al arrancar se borran los globales
  (si no, aparecen duplicados).
- Consultas a la base de datos en hilos (`asyncio.to_thread`); caché en memoria de 30 s;
  cooldown de 15 s por usuario y comando.

## Al hacer cambios
- Las migraciones de base de datos van en `_db_init()` y deben poder ejecutarse en cada arranque
  sin romper ni duplicar datos (la base de producción ya tiene datos).
- Probar antes de publicar: levantar un PostgreSQL local y ejecutar la lógica de `_db_*`
  importando `bot.py` sin la última línea (`bot.run(...)`); simular la API de Discord si hace falta.
- Comentarios del código en español, como el resto del archivo.
