import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import psycopg2
import time

# =========================================
# CONFIG
# =========================================

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1036557219585589319
DATABASE_URL = os.getenv("DATABASE_URL")

# =========================================
# ANTI-SPAM
# =========================================

user_last_call = {}
COOLDOWN_SECONDS = 15

def check_spam(user_id: int):
    now = time.time()
    last = user_last_call.get(user_id, 0)

    if now - last < COOLDOWN_SECONDS:
        return False

    user_last_call[user_id] = now
    return True

# =========================================
# CACHE PRO
# =========================================

CACHE = {
    "players": {},          # epic_id -> data
    "leaderboards": {},     # "elims" / "playtime"
    "timestamps": {}       # control de expiración
}

CACHE_TTL = 30  # segundos (ajusta si quieres más ahorro)

def cache_valid(key):
    return time.time() - CACHE["timestamps"].get(key, 0) < CACHE_TTL

# =========================================
# DATABASE
# =========================================

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        epic_id TEXT PRIMARY KEY,
        elims INTEGER,
        playtime INTEGER,
        register_date TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# =========================================
# BOT
# =========================================

class MyBot(commands.Bot):

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands")

intents = discord.Intents.default()
bot = MyBot(command_prefix="!", intents=intents)

# =========================================
# READY
# =========================================

@bot.event
async def on_ready():
    print("BOT READY:", bot.user)

# =========================================
# /ADDPLAYER (WRITE + CACHE UPDATE)
# =========================================

@bot.tree.command(name="addplayer", description="Add or update player")
async def addplayer(interaction: discord.Interaction, epic_id: str, elims: int, playtime: int):

    if not check_spam(interaction.user.id):
        await interaction.response.send_message("⏳ Slow down", ephemeral=True)
        return

    if elims < 0 or playtime < 0:
        await interaction.response.send_message("❌ Invalid values", ephemeral=True)
        return

    if len(epic_id) > 30:
        await interaction.response.send_message("❌ Epic ID too long", ephemeral=True)
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO players (epic_id, elims, playtime, register_date)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (epic_id)
    DO UPDATE SET
        elims = EXCLUDED.elims,
        playtime = EXCLUDED.playtime,
        register_date = EXCLUDED.register_date
    """, (epic_id, elims, playtime, datetime.now().strftime("%Y-%m-%d")))

    conn.commit()
    conn.close()

    # 🔥 UPDATE CACHE INSTANTE
    CACHE["players"][epic_id] = {
        "elims": elims,
        "playtime": playtime,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    CACHE["timestamps"]["players"] = time.time()

    await interaction.response.send_message(
        f"✅ Player `{epic_id}` saved",
        ephemeral=True
    )

# =========================================
# /STATS (CACHE FIRST)
# =========================================

@bot.tree.command(name="stats", description="View stats")
async def stats(interaction: discord.Interaction, epic_id: str):

    if not check_spam(interaction.user.id):
        await interaction.response.send_message("⏳ Slow down", ephemeral=True)
        return

    # 🔥 CACHE HIT
    if epic_id in CACHE["players"]:
        data = CACHE["players"][epic_id]

        embed = discord.Embed(title=f"Stats {epic_id}")
        embed.add_field(name="Elims", value=data["elims"], inline=False)
        embed.add_field(name="Playtime", value=f"{data['playtime']}h", inline=False)
        embed.add_field(name="Date", value=data["date"], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # DB fallback
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT epic_id, elims, playtime, register_date
    FROM players WHERE epic_id = %s
    """, (epic_id,))

    result = cur.fetchone()
    conn.close()

    if not result:
        await interaction.response.send_message("Player not found", ephemeral=True)
        return

    CACHE["players"][epic_id] = {
        "elims": result[1],
        "playtime": result[2],
        "date": result[3]
    }

    embed = discord.Embed(title=f"Stats {result[0]}")
    embed.add_field(name="Elims", value=result[1], inline=False)
    embed.add_field(name="Playtime", value=f"{result[2]}h", inline=False)
    embed.add_field(name="Date", value=result[3], inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================================
# /TOPELIMS (CACHE LEADERBOARD)
# =========================================

@bot.tree.command(name="topelims")
async def topelims(interaction: discord.Interaction):

    if not check_spam(interaction.user.id):
        await interaction.response.send_message("⏳ Slow down", ephemeral=True)
        return

    # CACHE HIT
    if cache_valid("leader_elims"):
        rows = CACHE["leaderboards"]["elims"]

    else:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
        SELECT epic_id, elims
        FROM players
        ORDER BY elims DESC
        LIMIT 10
        """)

        rows = cur.fetchall()
        conn.close()

        CACHE["leaderboards"]["elims"] = rows
        CACHE["timestamps"]["leader_elims"] = time.time()

    text = "\n".join(
        f"#{i} • `{r[0]}` • {r[1]}"
        for i, r in enumerate(rows, 1)
    ) if rows else "No players"

    await interaction.response.send_message(text, ephemeral=True)

# =========================================
# RUN
# =========================================

print("Starting bot...")
bot.run(TOKEN)
