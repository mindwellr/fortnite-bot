import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import sqlite3

# =========================================
# CONFIG
# =========================================

TOKEN = "MTUwNzQ4MTgyNTkwNjI2MjAzNw.Gu1VI2.ikcj4cx1dPvN7S9nZjN7T4TKMjZlCMnKOYLA0Y"

# TU SERVER ID REAL
GUILD_ID = 1036557219585589319
CURRENT_SEASON = 1

# =========================================
# DATABASE
# =========================================

conn = sqlite3.connect("stats.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    kills INTEGER,
    playtime INTEGER,
    rank TEXT,
    season INTEGER,
    register_date TEXT
)
""")

conn.commit()

# =========================================
# BOT CLASS
# =========================================

class MyBot(commands.Bot):

    async def setup_hook(self):

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)

        print("Synced guild commands")

# =========================================
# DISCORD SETUP
# =========================================

intents = discord.Intents.default()
intents.message_content = True

bot = MyBot(
    command_prefix="!",
    intents=intents
)

# =========================================
# READY EVENT
# =========================================

@bot.event
async def on_ready():

    print("BOT READY")
    print("Commands loaded:", [c.name for c in bot.tree.get_commands()])

# =========================
# SIGNATURE VERIFICATION
# =========================

SECRET = 4837

def generate_signature(kills, playtime):

    return (
        ((kills * 17) + SECRET) ^
        ((playtime * 9) + 112)
    )

# =========================================
# /ADDPLAYER
# =========================================

@bot.tree.command(
    name="addplayer",
    description="Add or update a player",
)
@app_commands.describe(
    player_id="Player ID",
    kills="Total kills",
    playtime="Playtime in hours",
    rank="Current rank"
)
async def addplayer(
    interaction: discord.Interaction,
    player_id: str,
    kills: int,
    playtime: int,
    rank: str
):
    current_date = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
    INSERT OR REPLACE INTO players
    (player_id, kills, playtime, rank, season, register_date)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
            player_id,
            kills,
            playtime,
            rank,
            CURRENT_SEASON,
            current_date
        ))

    conn.commit()

    embed = discord.Embed(
        title="Player Saved",
        description=f"Player `{player_id}` updated."
    )

    embed.add_field(
        name="Kills",
        value=str(kills),
        inline=False
    )

    embed.add_field(
        name="Playtime",
        value=f"{playtime}h",
        inline=False
    )

    embed.add_field(
        name="Rank",
        value=rank,
        inline=False
    )

    await interaction.response.send_message(embed=embed)

# =========================================
# /STATS
# =========================================

@bot.tree.command(
    name="stats",
    description="View player stats",
)
@app_commands.describe(
    player_id="Player ID"
)
async def stats(
    interaction: discord.Interaction,
    player_id: str
):

    cursor.execute("""
    SELECT * FROM players
    WHERE player_id = ?
    """, (player_id,))

    result = cursor.fetchone()

    if result:

        embed = discord.Embed(
            title=f"Stats for {result[0]}"
        )

        embed.add_field(
            name="Kills",
            value=str(result[1]),
            inline=False
        )

        embed.add_field(
            name="Playtime",
            value=f"{result[2]}h",
            inline=False
        )

        embed.add_field(
            name="Rank",
            value=result[3],
            inline=False
        )

        embed.add_field(
            name="Season",
            value=str(result[4]),
            inline=False
        )

        embed.add_field(
            name="Registered",
            value=result[5],
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    else:

        await interaction.response.send_message(
            "Player not found.",
            ephemeral=True
        )

# =========================================
# /TOPKILLS
# =========================================

@bot.tree.command(
    name="topkills",
    description="Top kills leaderboard",
)
async def topkills(
    interaction: discord.Interaction,
    season: int = CURRENT_SEASON
):

    cursor.execute("""
    SELECT player_id, kills
    FROM players
    WHERE season = ?
    ORDER BY kills DESC
    LIMIT 10
    """, (season,))

    results = cursor.fetchall()

    embed = discord.Embed(
        title=f"Season {season} Top Kills"
    )

    if len(results) == 0:

        embed.description = "No players found."

    else:

        leaderboard_text = ""

        for i, row in enumerate(results, start=1):

            leaderboard_text += (
                f"#{i} • `{row[0]}` • {row[1]} kills\n"
            )

        embed.description = leaderboard_text

    await interaction.response.send_message(embed=embed)

# =========================================
# /TOPPLAYTIME
# =========================================

@bot.tree.command(
    name="topplaytime",
    description="Top playtime leaderboard",
)
async def topplaytime(
    interaction: discord.Interaction,
    season: int = CURRENT_SEASON
):

    cursor.execute("""
    SELECT player_id, playtime
    FROM players
    WHERE season = ?
    ORDER BY playtime DESC
    LIMIT 10
    """, (season,))

    results = cursor.fetchall()

    embed = discord.Embed(
        title=f"Season {season} Top Playtime"
    )

    if len(results) == 0:

        embed.description = "No players found."

    else:

        leaderboard_text = ""

        for i, row in enumerate(results, start=1):

            leaderboard_text += (
                f"#{i} • `{row[0]}` • {row[1]}h\n"
            )

        embed.description = leaderboard_text

    await interaction.response.send_message(embed=embed)

# =========================================
# RUN BOT
# =========================================
print("Starting bot...")
bot.run(TOKEN)