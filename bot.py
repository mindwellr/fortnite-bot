import asyncio
import logging
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, urlencode

import base64

import aiohttp
import discord
import psycopg2
from discord import app_commands
from dotenv import load_dotenv

# =========================================
# CONFIG
# Se leen de variables de entorno o de un archivo .env junto a bot.py
# (el .env nunca se sube a GitHub, ver .gitignore).
# =========================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
# Servidor donde se registran los comandos (al instante).
# Si GUILD_ID=0 se registran globalmente (puede tardar hasta 1h en aparecer).
GUILD_ID = int(os.getenv("GUILD_ID", "1036557219585589319"))

# Verificación de Epic Games (Discord Developer Portal → tu app → OAuth2)
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "https://mindwellr.github.io/fortnite-bot/")
DISCORD_API = "https://discord.com/api/v10"

if not TOKEN:
    raise SystemExit("❌ Missing DISCORD_TOKEN environment variable")
if not DATABASE_URL:
    raise SystemExit("❌ Missing DATABASE_URL environment variable")
if not DISCORD_CLIENT_SECRET:
    print("⚠️ DISCORD_CLIENT_SECRET is not set: /verify and /addplayer won't work until it is.")

log = logging.getLogger("fortnite-bot")

# =========================================
# IDIOMAS (ES / EN según el idioma de Discord de quien usa el comando)
# =========================================

MESSAGES = {
    "en": {
        "cooldown": "⏳ Wait {seconds}s before using this command again.",
        "need_verify": "🔒 First link your Epic Games account with `/verify`. That way nobody can submit stats in your name.",
        "created": "✅ Player `{epic_id}` registered.",
        "updated": "✅ Player `{epic_id}` updated.",
        "kept_highest": "ℹ️ Some values were lower than the saved ones, so the highest were kept.",
        "already_today": "⛔ `{epic_id}` was already updated today. You can update it again {when}.",
        "not_higher": "ℹ️ Nothing changed: the saved stats for `{epic_id}` are already equal or higher.",
        "name_conflict": "⚠️ The name `{epic_id}` is saved for a different Epic account. Ask an admin to remove it with `/removeplayer` and try again.",
        "not_found": "❌ Player `{epic_id}` not found.",
        "stats_need_id": "ℹ️ Write an Epic ID, or link yours with `/verify` to see your own stats.",
        "no_players": "No players registered yet.",
        "error": "❌ Something went wrong. Please try again later.",
        "removed": "🗑️ Player `{epic_id}` removed.",
        "admin_only": "⛔ Only admins can use this command.",
        "stats_title": "Stats {epic_id}",
        "elims": "Elims",
        "playtime": "Playtime",
        "registered": "Registered",
        "last_update": "Last update",
        "owner": "Discord",
        "verified": "Verified",
        "top_elims": "🏆 Top elims",
        "top_playtime": "⏱️ Top playtime",
        "verify_not_configured": "⚠️ Verification isn't set up yet. Ask an admin.",
        "verify_intro": (
            "🔗 **Link your Epic Games account**\n"
            "1. If you haven't yet, connect Epic Games to Discord: **User Settings → Connections → Epic Games**.\n"
            "2. Press **Authorize** and accept.\n"
            "3. Copy the code shown on the page, come back here and press **Enter code**."
        ),
        "btn_authorize": "Authorize",
        "btn_enter_code": "Enter code",
        "modal_title": "Link Epic Games",
        "modal_label": "Code",
        "modal_placeholder": "Paste the code here",
        "bad_code": "❌ That code isn't valid or has expired. Use `/verify` and try again.",
        "wrong_account": "❌ That code belongs to a different Discord account. Log in to Discord with your own account and try again.",
        "no_epic": "❌ There's no Epic Games account connected to your Discord. Connect it in **User Settings → Connections → Epic Games**, then use `/verify` again.",
        "verified_ok": "✅ Linked to Epic account **{epic_name}**. Now you can use `/addplayer`.",
    },
    "es": {
        "cooldown": "⏳ Espera {seconds}s antes de volver a usar este comando.",
        "need_verify": "🔒 Primero vincula tu cuenta de Epic Games con `/verify`. Así nadie puede subir stats en tu nombre.",
        "created": "✅ Jugador `{epic_id}` registrado.",
        "updated": "✅ Jugador `{epic_id}` actualizado.",
        "kept_highest": "ℹ️ Algunos valores eran menores que los guardados, así que se mantuvieron los más altos.",
        "already_today": "⛔ `{epic_id}` ya se actualizó hoy. Podrás actualizarlo de nuevo {when}.",
        "not_higher": "ℹ️ No hubo cambios: las stats guardadas de `{epic_id}` ya son iguales o mayores.",
        "name_conflict": "⚠️ El nombre `{epic_id}` está guardado para otra cuenta de Epic. Pide a un admin que lo borre con `/removeplayer` e inténtalo de nuevo.",
        "not_found": "❌ No se encontró al jugador `{epic_id}`.",
        "stats_need_id": "ℹ️ Escribe un Epic ID, o vincula el tuyo con `/verify` para ver tus propias stats.",
        "no_players": "Todavía no hay jugadores registrados.",
        "error": "❌ Algo salió mal. Inténtalo de nuevo más tarde.",
        "removed": "🗑️ Jugador `{epic_id}` eliminado.",
        "admin_only": "⛔ Solo los admins pueden usar este comando.",
        "stats_title": "Stats {epic_id}",
        "elims": "Eliminaciones",
        "playtime": "Tiempo jugado",
        "registered": "Registrado",
        "last_update": "Última actualización",
        "owner": "Discord",
        "verified": "Verificado",
        "top_elims": "🏆 Top eliminaciones",
        "top_playtime": "⏱️ Top tiempo jugado",
        "verify_not_configured": "⚠️ La verificación aún no está configurada. Avisa a un admin.",
        "verify_intro": (
            "🔗 **Vincula tu cuenta de Epic Games**\n"
            "1. Si aún no lo hiciste, conecta Epic Games a Discord: **Ajustes de usuario → Conexiones → Epic Games**.\n"
            "2. Pulsa **Autorizar** y acepta.\n"
            "3. Copia el código que aparece en la página, vuelve aquí y pulsa **Introducir código**."
        ),
        "btn_authorize": "Autorizar",
        "btn_enter_code": "Introducir código",
        "modal_title": "Vincular Epic Games",
        "modal_label": "Código",
        "modal_placeholder": "Pega el código aquí",
        "bad_code": "❌ Ese código no es válido o ya caducó. Usa `/verify` e inténtalo de nuevo.",
        "wrong_account": "❌ Ese código es de otra cuenta de Discord. Inicia sesión en Discord con tu propia cuenta e inténtalo de nuevo.",
        "no_epic": "❌ Tu Discord no tiene una cuenta de Epic Games conectada. Conéctala en **Ajustes de usuario → Conexiones → Epic Games** y vuelve a usar `/verify`.",
        "verified_ok": "✅ Vinculado a la cuenta de Epic **{epic_name}**. Ya puedes usar `/addplayer`.",
    },
}

def t(interaction: discord.Interaction, key: str, **kwargs) -> str:
    lang = "es" if str(interaction.locale).startswith("es") else "en"
    return MESSAGES[lang][key].format(**kwargs)

# =========================================
# ANTI-SPAM (por usuario y por comando)
# =========================================

user_last_call = {}
COOLDOWN_SECONDS = 15

def check_cooldown(user_id: int, command: str) -> int:
    """Devuelve 0 si puede usar el comando, o los segundos que le faltan."""
    now = time.monotonic()
    key = (user_id, command)
    remaining = COOLDOWN_SECONDS - (now - user_last_call.get(key, float("-inf")))
    if remaining > 0:
        return math.ceil(remaining)
    user_last_call[key] = now
    return 0

async def on_cooldown(interaction: discord.Interaction, command: str) -> bool:
    seconds = check_cooldown(interaction.user.id, command)
    if seconds:
        await interaction.response.send_message(
            t(interaction, "cooldown", seconds=seconds), ephemeral=True
        )
        return True
    return False

# =========================================
# CACHE (todo caduca a los CACHE_TTL segundos)
# =========================================

CACHE_TTL = 30
player_cache = {}       # epic_id en minúsculas -> (timestamp, row)
leaderboard_cache = {}  # "elims" / "playtime" -> (timestamp, rows)

def cache_get(cache: dict, key):
    entry = cache.get(key)
    if entry and time.monotonic() - entry[0] < CACHE_TTL:
        return entry[1]
    cache.pop(key, None)
    return None

def cache_set(cache: dict, key, value):
    cache[key] = (time.monotonic(), value)

# =========================================
# DATABASE
# Las funciones _db_* son síncronas y se ejecutan en otro hilo
# (asyncio.to_thread) para no bloquear al bot mientras esperan a PostgreSQL.
# =========================================

def _connect():
    return psycopg2.connect(DATABASE_URL)

def _db_run(sql: str, params=(), fetch=None):
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:  # commit si todo sale bien, rollback si falla
            cur.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
    finally:
        conn.close()

# playtime_minutes = tiempo jugado en minutos (la columna antigua "playtime" era en horas)
PLAYER_COLUMNS = "epic_id, elims, playtime_minutes, register_date, last_update, owner_id, epic_account_id"

def _db_init():
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                epic_id TEXT PRIMARY KEY,
                elims INTEGER,
                playtime INTEGER,
                register_date TEXT
            )
            """)
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS last_update TEXT")
            # Cuenta de Discord que subió las stats por última vez
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS owner_id BIGINT")
            # Ya no se limita a un Epic ID por cuenta: ahora la verificación lo garantiza
            cur.execute("DROP INDEX IF EXISTS players_owner_idx")
            # ID real de la cuenta de Epic (no cambia aunque cambie el nombre)
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS epic_account_id TEXT")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS players_account_idx ON players (epic_account_id)")

            # El tiempo jugado pasa de horas a minutos: se convierte una sola vez
            cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'players' AND column_name = 'playtime_minutes'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE players ADD COLUMN playtime_minutes INTEGER")
                cur.execute("UPDATE players SET playtime_minutes = playtime * 60")

            # Cuentas de Discord verificadas con su cuenta de Epic Games
            cur.execute("""
            CREATE TABLE IF NOT EXISTS verified_accounts (
                discord_id BIGINT PRIMARY KEY,
                epic_account_id TEXT NOT NULL,
                epic_name TEXT NOT NULL,
                verified_at TEXT
            )
            """)

        # "Ninja" y "ninja" son el mismo jugador. Si ya existieran duplicados
        # con distinta mayúscula, el índice no se puede crear, pero el bot
        # sigue funcionando igual porque las búsquedas ya ignoran mayúsculas.
        try:
            with conn, conn.cursor() as cur:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS players_lower_idx ON players (LOWER(epic_id))")
        except psycopg2.Error as e:
            print(f"⚠️ Could not create case-insensitive index (duplicate names?): {e}")
    finally:
        conn.close()

def _find_player(cur, epic_id: str, lock: bool = False):
    cur.execute(
        f"SELECT {PLAYER_COLUMNS} FROM players WHERE LOWER(epic_id) = LOWER(%s) "
        "ORDER BY register_date LIMIT 1" + (" FOR UPDATE" if lock else ""),
        (epic_id,),
    )
    return cur.fetchone()

def _find_player_by_account(cur, account_id: str, lock: bool = False):
    cur.execute(
        f"SELECT {PLAYER_COLUMNS} FROM players WHERE epic_account_id = %s"
        + (" FOR UPDATE" if lock else ""),
        (account_id,),
    )
    return cur.fetchone()

def _db_get_verification(discord_id: int):
    """Devuelve (epic_account_id, epic_name) o None."""
    return _db_run(
        "SELECT epic_account_id, epic_name FROM verified_accounts WHERE discord_id = %s",
        (discord_id,), fetch="one",
    )

def _db_save_verification(discord_id: int, account_id: str, epic_name: str, today: str):
    _db_run("""
    INSERT INTO verified_accounts (discord_id, epic_account_id, epic_name, verified_at)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (discord_id) DO UPDATE SET
        epic_account_id = EXCLUDED.epic_account_id,
        epic_name = EXCLUDED.epic_name,
        verified_at = EXCLUDED.verified_at
    """, (discord_id, account_id, epic_name, today))

def _db_save_player(account_id: str, epic_name: str, elims: int, playtime: int, today: str, user_id: int):
    # playtime en minutos
    """
    Registra o actualiza las stats de una cuenta de Epic YA VERIFICADA.
    - Siempre se conserva el valor más alto de elims y tiempo jugado.
    - Solo se puede actualizar una vez al día, y solo si algún valor sube.
    - Los jugadores registrados antes de la verificación se vinculan por nombre
      la primera vez que su dueño real los actualiza.
    Devuelve (status, row) con status en: "created", "updated", "already_today",
    "not_higher", "name_conflict".
    """
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            # Evita que dos actualizaciones de la misma cuenta se pisen
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (account_id,))
            row = _find_player_by_account(cur, account_id, lock=True)

            if row is None:
                row = _find_player(cur, epic_name, lock=True)
                if row and row[6] is not None:
                    # Ese nombre ya pertenece a otra cuenta de Epic
                    return "name_conflict", row
                if row:
                    # Jugador antiguo sin verificar: se vincula a esta cuenta
                    cur.execute(f"""
                    UPDATE players SET epic_account_id = %s, owner_id = %s
                    WHERE epic_id = %s
                    RETURNING {PLAYER_COLUMNS}
                    """, (account_id, user_id, row[0]))
                    row = cur.fetchone()

            if row is None:
                cur.execute(f"""
                INSERT INTO players (epic_id, elims, playtime_minutes, register_date, last_update, owner_id, epic_account_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING {PLAYER_COLUMNS}
                """, (epic_name, elims, playtime, today, today, user_id, account_id))
                return "created", cur.fetchone()

            if row[4] == today:
                return "already_today", row

            if elims <= (row[1] or 0) and playtime <= (row[2] or 0):
                return "not_higher", row

            # Si cambió su nombre en Epic, se actualiza (salvo que otro jugador ya lo use)
            new_name = row[0]
            if epic_name.lower() != row[0].lower():
                other = _find_player(cur, epic_name)
                if other is None:
                    new_name = epic_name

            cur.execute(f"""
            UPDATE players SET
                epic_id = %s,
                elims = GREATEST(elims, %s),
                playtime_minutes = GREATEST(playtime_minutes, %s),
                last_update = %s,
                owner_id = %s
            WHERE epic_account_id = %s
            RETURNING {PLAYER_COLUMNS}
            """, (new_name, elims, playtime, today, user_id, account_id))
            return "updated", cur.fetchone()
    finally:
        conn.close()

def _db_get_player(epic_id: Optional[str] = None, account_id: Optional[str] = None):
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            if account_id:
                return _find_player_by_account(cur, account_id)
            return _find_player(cur, epic_id)
    finally:
        conn.close()

async def db_run(sql: str, params=(), fetch=None):
    return await asyncio.to_thread(_db_run, sql, params, fetch)

def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

# =========================================
# VERIFICACIÓN CON EPIC GAMES
# El usuario conecta Epic Games en su perfil de Discord (Discord lo verifica).
# Luego autoriza al bot a leer sus conexiones; la página de GitHub Pages
# (carpeta docs/) le muestra un código que pega en el bot. El bot comprueba que
# el código es de la misma cuenta de Discord y lee su cuenta de Epic.
# =========================================

class VerifyError(Exception):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key

def authorize_url(client_id: int) -> str:
    return "https://discord.com/oauth2/authorize?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "scope": "identify connections",
        "redirect_uri": OAUTH_REDIRECT_URI,
        "prompt": "consent",
    }, quote_via=quote)

def extract_code(text: str) -> Optional[str]:
    """Acepta el código solo o la URL completa de la página."""
    text = text.strip()
    match = re.search(r"[?&]code=([^&#\s]+)", text)
    code = match.group(1) if match else text
    return code if re.fullmatch(r"[A-Za-z0-9_-]{10,100}", code) else None

def client_auth(client_id: int) -> dict:
    credentials = base64.b64encode(f"{client_id}:{DISCORD_CLIENT_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}

async def fetch_epic_account(code: str, client_id: int):
    """Devuelve (discord_user_id, [conexiones de Epic verificadas])."""
    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{DISCORD_API}/oauth2/token",
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": OAUTH_REDIRECT_URI},
            headers=client_auth(client_id),
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                if body.get("error") == "invalid_grant":
                    raise VerifyError("bad_code")
                # invalid_client / redirect_uri incorrecto = problema de configuración
                raise RuntimeError(f"OAuth token exchange failed ({resp.status}): {body}")
            token = body["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with http.get(f"{DISCORD_API}/users/@me", headers=headers) as resp:
                resp.raise_for_status()
                me = await resp.json()
            async with http.get(f"{DISCORD_API}/users/@me/connections", headers=headers) as resp:
                resp.raise_for_status()
                connections = await resp.json()
        finally:
            # El bot ya no necesita el token: se revoca
            try:
                await http.post(
                    f"{DISCORD_API}/oauth2/token/revoke",
                    data={"token": token, "token_type_hint": "access_token"},
                    headers=client_auth(client_id),
                )
            except aiohttp.ClientError:
                pass

    epic = [
        c for c in connections
        if c.get("type") == "epicgames" and c.get("verified") and not c.get("revoked")
    ]
    return int(me["id"]), epic

async def send_error(interaction: discord.Interaction):
    message = t(interaction, "error")
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

class CodeModal(discord.ui.Modal):

    def __init__(self, interaction: discord.Interaction):
        super().__init__(title=t(interaction, "modal_title"))
        self.code = discord.ui.TextInput(
            label=t(interaction, "modal_label"),
            placeholder=t(interaction, "modal_placeholder"),
            min_length=10,
            max_length=500,
        )
        self.add_item(self.code)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            code = extract_code(self.code.value)
            if not code:
                raise VerifyError("bad_code")

            discord_id, epic = await fetch_epic_account(code, interaction.client.application_id)

            if discord_id != interaction.user.id:
                raise VerifyError("wrong_account")
            if not epic:
                raise VerifyError("no_epic")
        except VerifyError as e:
            await interaction.followup.send(t(interaction, e.key), ephemeral=True)
            return

        account = epic[0]
        await asyncio.to_thread(
            _db_save_verification, interaction.user.id, account["id"], account["name"], today_utc()
        )
        await interaction.followup.send(
            t(interaction, "verified_ok", epic_name=account["name"]), ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error("Error in verification", exc_info=error)
        await send_error(interaction)

class VerifyView(discord.ui.View):

    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=600)
        self.add_item(discord.ui.Button(
            label=t(interaction, "btn_authorize"),
            url=authorize_url(interaction.client.application_id),
        ))
        enter_code = discord.ui.Button(
            label=t(interaction, "btn_enter_code"), style=discord.ButtonStyle.primary
        )
        enter_code.callback = self.enter_code
        self.add_item(enter_code)

    async def enter_code(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CodeModal(interaction))

# =========================================
# TRADUCCIÓN DE LOS COMANDOS
# Discord muestra estas traducciones a quien tenga Discord en español.
# Los nombres de los comandos se quedan en inglés; solo se traducen las
# descripciones y los campos.
# =========================================

COMMAND_TEXT_ES = {
    # Descripciones de comandos
    "Link your Epic Games account": "Vincula tu cuenta de Epic Games",
    "Register or update your stats": "Registra o actualiza tus stats",
    "View stats": "Ver las stats de un jugador",
    "(Admin) Remove a player": "(Admin) Eliminar un jugador",
    "Top 10 players by elims": "Top 10 jugadores por eliminaciones",
    "Top 10 players by playtime": "Top 10 jugadores por tiempo jugado",
    # Campos
    "elims": "eliminaciones",
    "hours": "horas",
    "minutes": "minutos",
    "Eliminations": "Eliminaciones",
    "Hours played": "Horas jugadas",
    "Minutes played (0-59)": "Minutos jugados (0-59)",
    "Epic ID (leave empty to see yours)": "Epic ID (déjalo vacío para ver el tuyo)",
    "Epic ID to remove": "Epic ID a eliminar",
}

TRANSLATED_LOCATIONS = (
    app_commands.TranslationContextLocation.command_description,
    app_commands.TranslationContextLocation.parameter_name,
    app_commands.TranslationContextLocation.parameter_description,
)

class SpanishTranslator(app_commands.Translator):

    async def translate(self, string: app_commands.locale_str, locale: discord.Locale, context):
        if not str(locale).startswith("es") or context.location not in TRANSLATED_LOCATIONS:
            return None
        return COMMAND_TEXT_ES.get(string.message)

# =========================================
# BOT
# =========================================

class MyBot(discord.Client):

    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await asyncio.to_thread(_db_init)
        await self.tree.set_translator(SpanishTranslator())

        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
                # Borra los comandos globales que registraron versiones antiguas
                # del bot; si no, cada comando aparece duplicado en el servidor.
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
            else:
                synced = await self.tree.sync()
                print(f"Synced {len(synced)} commands globally")
        except discord.Forbidden:
            print(
                f"❌ Could not sync commands to guild {GUILD_ID}. "
                "Make sure the bot is in that server and was invited with the "
                "'applications.commands' scope."
            )

bot = MyBot()

# =========================================
# READY
# =========================================

@bot.event
async def on_ready():
    print("BOT READY:", bot.user)
    for guild in bot.guilds:
        print(f" - in guild: {guild.name} ({guild.id})")

# =========================================
# ERRORES
# =========================================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    log.error("Error in command %s", interaction.command and interaction.command.name, exc_info=error)
    await send_error(interaction)

# =========================================
# HELPERS
# =========================================

def stats_embed(interaction: discord.Interaction, row) -> discord.Embed:
    epic_id, elims, playtime, register_date, last_update, owner_id, account_id = row
    embed = discord.Embed(title=t(interaction, "stats_title", epic_id=epic_id))
    embed.add_field(name=t(interaction, "elims"), value=elims, inline=False)
    embed.add_field(name=t(interaction, "playtime"), value=format_playtime(playtime), inline=False)
    embed.add_field(name=t(interaction, "registered"), value=register_date or "-", inline=True)
    embed.add_field(name=t(interaction, "last_update"), value=last_update or "-", inline=True)
    embed.add_field(name=t(interaction, "verified"), value="✅" if account_id else "❌", inline=True)
    embed.add_field(name=t(interaction, "owner"), value=f"<@{owner_id}>" if owner_id else "-", inline=True)
    return embed

def format_playtime(minutes) -> str:
    minutes = minutes or 0
    return f"{minutes // 60}h {minutes % 60}m"

def next_utc_midnight() -> int:
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return int(datetime.combine(tomorrow, datetime.min.time(), timezone.utc).timestamp())

# =========================================
# /VERIFY
# =========================================

@bot.tree.command(name="verify", description="Link your Epic Games account")
async def verify(interaction: discord.Interaction):

    if await on_cooldown(interaction, "verify"):
        return

    if not DISCORD_CLIENT_SECRET:
        await interaction.response.send_message(t(interaction, "verify_not_configured"), ephemeral=True)
        return

    await interaction.response.send_message(
        t(interaction, "verify_intro"), view=VerifyView(interaction), ephemeral=True
    )

# =========================================
# /ADDPLAYER (usa la cuenta de Epic verificada de quien lo usa)
# =========================================

@bot.tree.command(name="addplayer", description="Register or update your stats")
@app_commands.describe(
    elims="Eliminations",
    hours="Hours played",
    minutes="Minutes played (0-59)",
)
async def addplayer(
    interaction: discord.Interaction,
    elims: app_commands.Range[int, 0, 10_000_000],
    hours: app_commands.Range[int, 0, 100_000],
    minutes: app_commands.Range[int, 0, 59] = 0,
):

    if await on_cooldown(interaction, "addplayer"):
        return

    playtime = hours * 60 + minutes

    await interaction.response.defer(ephemeral=True, thinking=True)

    verification = await asyncio.to_thread(_db_get_verification, interaction.user.id)
    if not verification:
        await interaction.followup.send(t(interaction, "need_verify"), ephemeral=True)
        return

    account_id, epic_name = verification
    status, row = await asyncio.to_thread(
        _db_save_player, account_id, epic_name, elims, playtime, today_utc(), interaction.user.id
    )

    if status == "name_conflict":
        await interaction.followup.send(t(interaction, "name_conflict", epic_id=row[0]), ephemeral=True)
        return

    cache_set(player_cache, row[0].lower(), row)
    if status in ("created", "updated"):
        leaderboard_cache.clear()  # el ranking cambió

    name = row[0]
    if status == "already_today":
        message = t(interaction, "already_today", epic_id=name, when=f"<t:{next_utc_midnight()}:R>")
    elif status == "not_higher":
        message = t(interaction, "not_higher", epic_id=name)
    else:
        message = t(interaction, status, epic_id=name)
        if row[1] > elims or row[2] > playtime:
            message += "\n" + t(interaction, "kept_highest")

    await interaction.followup.send(message, embed=stats_embed(interaction, row), ephemeral=True)

# =========================================
# /STATS (sin Epic ID muestra las tuyas)
# =========================================

@bot.tree.command(name="stats", description="View stats")
@app_commands.describe(epic_id="Epic ID (leave empty to see yours)")
async def stats(interaction: discord.Interaction, epic_id: Optional[str] = None):

    if await on_cooldown(interaction, "stats"):
        return

    epic_id = epic_id.strip() if epic_id else None
    row = cache_get(player_cache, epic_id.lower()) if epic_id else None

    if row is not None:
        await interaction.response.send_message(embed=stats_embed(interaction, row), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    if epic_id:
        row = await asyncio.to_thread(_db_get_player, epic_id)
    else:
        verification = await asyncio.to_thread(_db_get_verification, interaction.user.id)
        if not verification:
            await interaction.followup.send(t(interaction, "stats_need_id"), ephemeral=True)
            return
        epic_id = verification[1]
        row = await asyncio.to_thread(_db_get_player, None, verification[0])

    if not row:
        await interaction.followup.send(t(interaction, "not_found", epic_id=epic_id), ephemeral=True)
        return

    cache_set(player_cache, row[0].lower(), row)
    await interaction.followup.send(embed=stats_embed(interaction, row), ephemeral=True)

# =========================================
# /REMOVEPLAYER (solo admins: permiso "Gestionar servidor")
# Sirve para borrar registros falsos o antiguos.
# =========================================

@bot.tree.command(name="removeplayer", description="(Admin) Remove a player")
@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.describe(epic_id="Epic ID to remove")
async def removeplayer(interaction: discord.Interaction, epic_id: str):

    if not interaction.permissions.manage_guild:
        await interaction.response.send_message(t(interaction, "admin_only"), ephemeral=True)
        return

    epic_id = epic_id.strip()
    await interaction.response.defer(ephemeral=True, thinking=True)

    rows = await db_run(
        "DELETE FROM players WHERE LOWER(epic_id) = LOWER(%s) RETURNING epic_id",
        (epic_id,), fetch="all",
    )

    player_cache.pop(epic_id.lower(), None)
    leaderboard_cache.clear()

    key = "removed" if rows else "not_found"
    await interaction.followup.send(t(interaction, key, epic_id=epic_id), ephemeral=True)

# =========================================
# /TOPELIMS y /TOPPLAYTIME (✅ = cuenta de Epic verificada)
# =========================================

LEADERBOARD_QUERIES = {
    "elims": "SELECT epic_id, elims, epic_account_id IS NOT NULL FROM players ORDER BY elims DESC NULLS LAST LIMIT 10",
    "playtime": "SELECT epic_id, playtime_minutes, epic_account_id IS NOT NULL FROM players ORDER BY playtime_minutes DESC NULLS LAST LIMIT 10",
}

async def send_leaderboard(interaction: discord.Interaction, column: str, title_key: str, fmt=str):
    rows = cache_get(leaderboard_cache, column)

    if rows is None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await db_run(LEADERBOARD_QUERIES[column], fetch="all")
        cache_set(leaderboard_cache, column, rows)

    text = "\n".join(
        f"#{i} • `{epic_id}`{' ✅' if verified else ''} • {fmt(value)}"
        for i, (epic_id, value, verified) in enumerate(rows, 1)
    ) if rows else t(interaction, "no_players")

    embed = discord.Embed(title=t(interaction, title_key), description=text)

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="topelims", description="Top 10 players by elims")
async def topelims(interaction: discord.Interaction):
    if await on_cooldown(interaction, "topelims"):
        return
    await send_leaderboard(interaction, "elims", "top_elims")

@bot.tree.command(name="topplaytime", description="Top 10 players by playtime")
async def topplaytime(interaction: discord.Interaction):
    if await on_cooldown(interaction, "topplaytime"):
        return
    await send_leaderboard(interaction, "playtime", "top_playtime", fmt=format_playtime)

# =========================================
# RUN
# =========================================

bot.run(TOKEN, root_logger=True)
