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
player_cache = {}       # epic_id -> (timestamp, row)
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
    finally:
        conn.close()

def _db_save_player(epic_id: str, elims: int, playtime: int, today: str):
    """
    Registra o actualiza un jugador.
    - Siempre se conserva el valor más alto de elims y playtime.
    - Solo se puede actualizar una vez al día, y solo si algún valor sube
      (así nadie puede "gastar" la actualización diaria de otro con valores bajos).
    Devuelve (status, row) con status en: "created", "updated", "already_today", "not_higher".
    """
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
            INSERT INTO players (epic_id, elims, playtime, register_date, last_update)
            VALUES (%(epic_id)s, %(elims)s, %(playtime)s, %(today)s, %(today)s)
            ON CONFLICT (epic_id) DO UPDATE SET
                elims = GREATEST(players.elims, EXCLUDED.elims),
                playtime = GREATEST(players.playtime, EXCLUDED.playtime),
                last_update = EXCLUDED.last_update
            WHERE players.last_update IS DISTINCT FROM EXCLUDED.last_update
              AND (EXCLUDED.elims > COALESCE(players.elims, -1)
                   OR EXCLUDED.playtime > COALESCE(players.playtime, -1))
            RETURNING elims, playtime, register_date, last_update, (xmax = 0) AS inserted
            """, {"epic_id": epic_id, "elims": elims, "playtime": playtime, "today": today})
            result = cur.fetchone()

            if result:
                return ("created" if result[4] else "updated"), result[:4]

            cur.execute("""
            SELECT elims, playtime, register_date, last_update
            FROM players WHERE epic_id = %s
            """, (epic_id,))
            row = cur.fetchone()
            status = "already_today" if row[3] == today else "not_higher"
            return status, row
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

def stats_embed(interaction: discord.Interaction, epic_id: str, row) -> discord.Embed:
    elims, playtime, register_date, last_update = row
    embed = discord.Embed(title=t(interaction, "stats_title", epic_id=epic_id))
    embed.add_field(name=t(interaction, "elims"), value=elims, inline=False)
    embed.add_field(name=t(interaction, "playtime"), value=f"{playtime}h", inline=False)
    embed.add_field(name=t(interaction, "registered"), value=register_date or "-", inline=True)
    embed.add_field(name=t(interaction, "last_update"), value=last_update or "-", inline=True)
    return embed

def next_utc_midnight() -> int:
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return int(datetime.combine(tomorrow, datetime.min.time(), timezone.utc).timestamp())

# =========================================
# /ADDPLAYER
# =========================================

@bot.tree.command(name="addplayer", description="Add or update player")
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
    status, row = await asyncio.to_thread(_db_save_player, epic_id, elims, playtime, today)

    cache_set(player_cache, epic_id, row)
    if status in ("created", "updated"):
        leaderboard_cache.clear()  # el ranking cambió

    if status == "already_today":
        message = t(interaction, "already_today", epic_id=epic_id, when=f"<t:{next_utc_midnight()}:R>")
    elif status == "not_higher":
        message = t(interaction, "not_higher", epic_id=epic_id)
    else:
        message = t(interaction, status, epic_id=epic_id)
        if row[0] > elims or row[1] > playtime:
            message += "\n" + t(interaction, "kept_highest")

    await interaction.followup.send(
        message, embed=stats_embed(interaction, epic_id, row), ephemeral=True
    )

# =========================================
# /STATS
# =========================================

@bot.tree.command(name="stats", description="View stats")
async def stats(interaction: discord.Interaction, epic_id: str):

    if await on_cooldown(interaction, "stats"):
        return

    epic_id = epic_id.strip()
    row = cache_get(player_cache, epic_id)

    if row is None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        row = await db_run("""
        SELECT elims, playtime, register_date, last_update
        FROM players WHERE epic_id = %s
        """, (epic_id,), fetch="one")

        if not row:
            await interaction.followup.send(t(interaction, "not_found", epic_id=epic_id), ephemeral=True)
            return

        cache_set(player_cache, epic_id, row)
        await interaction.followup.send(embed=stats_embed(interaction, epic_id, row), ephemeral=True)
        return

    await interaction.response.send_message(embed=stats_embed(interaction, epic_id, row), ephemeral=True)

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
