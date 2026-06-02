import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import sqlite3
import os

# =========================================
# CONFIG
# =========================================

TOKEN = os.getenv("DISCORD_TOKEN")

# TU SERVER ID REAL
GUILD_ID = 1036557219585589319

# =========================================
# DATABASE
# =========================================

conn = sqlite3.connect("stats.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    epic_id TEXT PRIMARY KEY,
    elims INTEGER,
    playtime INTEGER,
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

def generate_signature(elims, playtime):

    return (
        ((elims * 17) + SECRET) ^
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
    epic_id="Epic ID",
    elims="Total elims",
    playtime="Playtime in hours"
)
async def addplayer(
    interaction: discord.Interaction,
    epic_id: str,
    elims: int,
    playtime: int
):
    current_date = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
    INSERT OR REPLACE INTO players
    (epic_id, elims, playtime, register_date)
    VALUES (?, ?, ?, ?)
    """, (
            epic_id,
            elims,
            playtime,
            current_date
        ))

    conn.commit()

    embed = discord.Embed(
        title="Player Saved",
        description=f"Player `{epic_id}` updated."
    )

    embed.add_field(
        name="Elims",
        value=str(elims),
        inline=False
    )

    embed.add_field(
        name="Playtime",
        value=f"{playtime}h",
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
    epic_id="Epic ID"
)
async def stats(
    interaction: discord.Interaction,
    epic_id: str
):

    cursor.execute("""
    SELECT * FROM players
    WHERE epic_id = ?
    """, (epic_id,))

    result = cursor.fetchone()

    if result:

        embed = discord.Embed(
            title=f"Stats for {result[0]}"
        )

        embed.add_field(
            name="Elims",
            value=str(result[1]),
            inline=False
        )

        embed.add_field(
            name="Playtime",
            value=f"{result[2]}h",
            inline=False
        )

        embed.add_field(
            name="Registered",
            value=result[3],
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    else:

        await interaction.response.send_message(
            "Player not found.",
            ephemeral=True
        )

# =========================================
# /TOPELIMS
# =========================================

@bot.tree.command(
    name="topelims",
    description="Top elims leaderboard",
)
async def topelims(
    interaction: discord.Interaction,
):

    cursor.execute("""
    SELECT epic_id, elims
    FROM players
    ORDER BY elims DESC
    LIMIT 10
    """)

    results = cursor.fetchall()

    embed = discord.Embed(
        title="Top Elims"
    )

    if len(results) == 0:

        embed.description = "No players found."

    else:

        leaderboard_text = ""

        for i, row in enumerate(results, start=1):

            leaderboard_text += (
                f"#{i} • `{row[0]}` • {row[1]} elims\n"
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
):

    cursor.execute("""
    SELECT epic_id, playtime
    FROM players
    ORDER BY playtime DESC
    LIMIT 10
    """)

    results = cursor.fetchall()

    embed = discord.Embed(
        title="Top Playtime"
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
