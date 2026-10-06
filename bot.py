import asyncio
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone

import discord
import psycopg2
from discord.ext import commands

# =========================================
# CONFIG
# =========================================

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
# Servidor donde se registran los comandos (al instante).
# Si GUILD_ID=0 se registran globalmente (puede tardar hasta 1h en aparecer).
GUILD_ID = int(os.getenv("GUILD_ID", "1036557219585589319"))

if not TOKEN:
    raise SystemExit("❌ Missing DISCORD_TOKEN environment variable")
if not DATABASE_URL:
    raise SystemExit("❌ Missing DATABASE_URL environment variable")

log = logging.getLogger("fortnite-bot")

# =========================================
# IDIOMAS (ES / EN según el idioma de Discord de quien usa el comando)
# =========================================

MESSAGES = {
    "en": {
        "cooldown": "⏳ Wait {seconds}s before using this command again.",
        "invalid_values": "❌ Elims and playtime can't be negative.",
        "id_empty": "❌ Epic ID can't be empty.",
        "id_too_long": "❌ Epic ID too long (max {max} characters).",
        "created": "✅ Player `{epic_id}` registered.",
        "updated": "✅ Player `{epic_id}` updated.",
        "kept_highest": "ℹ️ Some values were lower than the saved ones, so the highest were kept.",
        "already_today": "⛔ `{epic_id}` was already updated today. You can update it again {when}.",
        "not_higher": "ℹ️ Nothing changed: the saved stats for `{epic_id}` are already equal or higher.",
        "not_found": "❌ Player `{epic_id}` not found.",
        "not_owner": "⛔ `{epic_id}` was registered by another Discord account. Only that account can update it. If this is your Epic ID, ask an admin for help.",
        "already_owner": "⛔ Your Discord account already registered `{owned}`. Each account can only register one Epic ID.",
        "removed": "🗑️ Player `{epic_id}` removed.",
        "admin_only": "⛔ Only admins can use this command.",
        "owner": "Owner",
        "no_players": "No players registered yet.",
        "error": "❌ Something went wrong. Please try again later.",
        "stats_title": "Stats {epic_id}",
        "elims": "Elims",
        "playtime": "Playtime",
        "registered": "Registered",
        "last_update": "Last update",
        "top_elims": "🏆 Top elims",
        "top_playtime": "⏱️ Top playtime",
    },
    "es": {
        "cooldown": "⏳ Espera {seconds}s antes de volver a usar este comando.",
        "invalid_values": "❌ Las eliminaciones y el tiempo jugado no pueden ser negativos.",
        "id_empty": "❌ El Epic ID no puede estar vacío.",
        "id_too_long": "❌ Epic ID demasiado largo (máximo {max} caracteres).",
        "created": "✅ Jugador `{epic_id}` registrado.",
        "updated": "✅ Jugador `{epic_id}` actualizado.",
        "kept_highest": "ℹ️ Algunos valores eran menores que los guardados, así que se mantuvieron los más altos.",
        "already_today": "⛔ `{epic_id}` ya se actualizó hoy. Podrás actualizarlo de nuevo {when}.",
        "not_higher": "ℹ️ No hubo cambios: las stats guardadas de `{epic_id}` ya son iguales o mayores.",
        "not_found": "❌ No se encontró al jugador `{epic_id}`.",
        "not_owner": "⛔ `{epic_id}` fue registrado por otra cuenta de Discord. Solo esa cuenta puede actualizarlo. Si este Epic ID es tuyo, pide ayuda a un admin.",
        "already_owner": "⛔ Tu cuenta de Discord ya registró `{owned}`. Cada cuenta solo puede registrar un Epic ID.",
        "removed": "🗑️ Jugador `{epic_id}` eliminado.",
        "admin_only": "⛔ Solo los admins pueden usar este comando.",
        "owner": "Dueño",
        "no_players": "Todavía no hay jugadores registrados.",
        "error": "❌ Algo salió mal. Inténtalo de nuevo más tarde.",
        "stats_title": "Stats {epic_id}",
        "elims": "Eliminaciones",
        "playtime": "Tiempo jugado",
        "registered": "Registrado",
        "last_update": "Última actualización",
        "top_elims": "🏆 Top eliminaciones",
        "top_playtime": "⏱️ Top tiempo jugado",
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

PLAYER_COLUMNS = "epic_id, elims, playtime, register_date, last_update, owner_id"

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
            # Cuenta de Discord dueña del Epic ID (una cuenta = un Epic ID)
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS owner_id BIGINT")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS players_owner_idx ON players (owner_id)")

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

def _db_save_player(epic_id: str, elims: int, playtime: int, today: str, user_id: int):
    """
    Registra o actualiza un jugador.
    - Cada cuenta de Discord solo puede registrar un Epic ID, y solo su dueño puede actualizarlo.
      (Los jugadores registrados antes de esto no tienen dueño: el primero que los
      actualice se queda como dueño.)
    - Siempre se conserva el valor más alto de elims y playtime.
    - Solo se puede actualizar una vez al día, y solo si algún valor sube.
    Devuelve (status, row) con status en: "created", "updated", "already_today",
    "not_higher", "not_owner", "already_owner".
    """
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            # Evita que dos personas registren el mismo nombre al mismo tiempo
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(LOWER(%s)))", (epic_id,))
            row = _find_player(cur, epic_id, lock=True)

            if row and row[5] is not None and row[5] != user_id:
                return "not_owner", row

            if row is None or row[5] is None:
                cur.execute(
                    f"SELECT {PLAYER_COLUMNS} FROM players WHERE owner_id = %s", (user_id,)
                )
                owned = cur.fetchone()
                if owned:
                    return "already_owner", owned

            if row is None:
                cur.execute(f"""
                INSERT INTO players (epic_id, elims, playtime, register_date, last_update, owner_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {PLAYER_COLUMNS}
                """, (epic_id, elims, playtime, today, today, user_id))
                return "created", cur.fetchone()

            if row[4] == today:
                return "already_today", row

            if elims <= (row[1] or 0) and playtime <= (row[2] or 0):
                return "not_higher", row

            cur.execute(f"""
            UPDATE players SET
                elims = GREATEST(elims, %s),
                playtime = GREATEST(playtime, %s),
                last_update = %s,
                owner_id = %s
            WHERE epic_id = %s
            RETURNING {PLAYER_COLUMNS}
            """, (elims, playtime, today, user_id, row[0]))
            return "updated", cur.fetchone()
    finally:
        conn.close()

async def db_run(sql: str, params=(), fetch=None):
    return await asyncio.to_thread(_db_run, sql, params, fetch)

# =========================================
# BOT
# =========================================

class MyBot(commands.Bot):

    async def setup_hook(self):
        await asyncio.to_thread(_db_init)

        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
            else:
                synced = await self.tree.sync()
                print(f"Synced {len(synced)} commands globally")
        except discord.Forbidden:
            print(
                f"❌ Could not sync commands to guild {GUILD_ID}. "
                "Make sure the bot is in that server and was invited with the "
                "'applications.commands' scope."
            )

intents = discord.Intents.default()
bot = MyBot(command_prefix="!", intents=intents)

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
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    log.error("Error in command %s", interaction.command and interaction.command.name, exc_info=error)
    message = t(interaction, "error")
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

# =========================================
# HELPERS
# =========================================

EPIC_ID_MAX_LENGTH = 30

def stats_embed(interaction: discord.Interaction, row) -> discord.Embed:
    epic_id, elims, playtime, register_date, last_update, owner_id = row
    embed = discord.Embed(title=t(interaction, "stats_title", epic_id=epic_id))
    embed.add_field(name=t(interaction, "elims"), value=elims, inline=False)
    embed.add_field(name=t(interaction, "playtime"), value=f"{playtime}h", inline=False)
    embed.add_field(name=t(interaction, "registered"), value=register_date or "-", inline=True)
    embed.add_field(name=t(interaction, "last_update"), value=last_update or "-", inline=True)
    embed.add_field(name=t(interaction, "owner"), value=f"<@{owner_id}>" if owner_id else "-", inline=True)
    return embed

def next_utc_midnight() -> int:
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return int(datetime.combine(tomorrow, datetime.min.time(), timezone.utc).timestamp())

# =========================================
# /ADDPLAYER
# =========================================

@bot.tree.command(name="addplayer", description="Register or update your Epic ID stats")
async def addplayer(interaction: discord.Interaction, epic_id: str, elims: int, playtime: int):

    if await on_cooldown(interaction, "addplayer"):
        return

    epic_id = epic_id.strip()

    if not epic_id:
        await interaction.response.send_message(t(interaction, "id_empty"), ephemeral=True)
        return

    if len(epic_id) > EPIC_ID_MAX_LENGTH:
        await interaction.response.send_message(
            t(interaction, "id_too_long", max=EPIC_ID_MAX_LENGTH), ephemeral=True
        )
        return

    if elims < 0 or playtime < 0:
        await interaction.response.send_message(t(interaction, "invalid_values"), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status, row = await asyncio.to_thread(
        _db_save_player, epic_id, elims, playtime, today, interaction.user.id
    )

    if status == "already_owner":
        # row es el jugador que ya tiene registrado esta cuenta
        await interaction.followup.send(
            t(interaction, "already_owner", owned=row[0]), ephemeral=True
        )
        return

    cache_set(player_cache, row[0].lower(), row)
    if status in ("created", "updated"):
        leaderboard_cache.clear()  # el ranking cambió

    name = row[0]
    if status == "not_owner":
        message = t(interaction, "not_owner", epic_id=name)
    elif status == "already_today":
        message = t(interaction, "already_today", epic_id=name, when=f"<t:{next_utc_midnight()}:R>")
    elif status == "not_higher":
        message = t(interaction, "not_higher", epic_id=name)
    else:
        message = t(interaction, status, epic_id=name)
        if row[1] > elims or row[2] > playtime:
            message += "\n" + t(interaction, "kept_highest")

    await interaction.followup.send(message, embed=stats_embed(interaction, row), ephemeral=True)

# =========================================
# /STATS
# =========================================

def _db_get_player(epic_id: str):
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            return _find_player(cur, epic_id)
    finally:
        conn.close()

@bot.tree.command(name="stats", description="View stats")
async def stats(interaction: discord.Interaction, epic_id: str):

    if await on_cooldown(interaction, "stats"):
        return

    epic_id = epic_id.strip()
    row = cache_get(player_cache, epic_id.lower())

    if row is None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        row = await asyncio.to_thread(_db_get_player, epic_id)

        if not row:
            await interaction.followup.send(t(interaction, "not_found", epic_id=epic_id), ephemeral=True)
            return

        cache_set(player_cache, epic_id.lower(), row)
        await interaction.followup.send(embed=stats_embed(interaction, row), ephemeral=True)
        return

    await interaction.response.send_message(embed=stats_embed(interaction, row), ephemeral=True)

# =========================================
# /REMOVEPLAYER (solo admins: permiso "Gestionar servidor")
# Sirve para borrar registros falsos o liberar un nombre que alguien
# registró sin ser suyo.
# =========================================

@bot.tree.command(name="removeplayer", description="(Admin) Remove a player")
@discord.app_commands.default_permissions(manage_guild=True)
@discord.app_commands.guild_only()
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
# /TOPELIMS y /TOPPLAYTIME
# =========================================

LEADERBOARD_QUERIES = {
    "elims": "SELECT epic_id, elims FROM players ORDER BY elims DESC NULLS LAST LIMIT 10",
    "playtime": "SELECT epic_id, playtime FROM players ORDER BY playtime DESC NULLS LAST LIMIT 10",
}

async def send_leaderboard(interaction: discord.Interaction, column: str, title_key: str, suffix: str = ""):
    rows = cache_get(leaderboard_cache, column)

    if rows is None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await db_run(LEADERBOARD_QUERIES[column], fetch="all")
        cache_set(leaderboard_cache, column, rows)

    text = "\n".join(
        f"#{i} • `{epic_id}` • {value}{suffix}"
        for i, (epic_id, value) in enumerate(rows, 1)
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
    await send_leaderboard(interaction, "playtime", "top_playtime", suffix="h")

# =========================================
# RUN
# =========================================

print("Starting bot...")
bot.run(TOKEN, root_logger=True)
