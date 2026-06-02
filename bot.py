import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import psycopg2

# =========================================
# CONFIG
# =========================================

TOKEN = os.getenv("DISCORD_TOKEN")

# TU SERVER ID REAL
GUILD_ID = 1036557219585589319

# =========================================
# DATABASE
# =========================================

def get_db():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    return conn, cursor


# crear tabla al iniciar
conn, cursor = get_db()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    epic_id TEXT PRIMARY KEY,
    elims INTEGER,
    playtime INTEGER,
    register_date TEXT
)
""")

conn.commit()
conn.close()

# =========================================
# BOT CLASS
# =========================================

class MyBot(commands.Bot):

    async def setup_hook(self):
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} global commands")


# =========================================
# DISCORD SETUP
# =========================================

intents = discord.Intents.default()
bot = MyBot(command_prefix="!", intents=intents)


# =========================================
# READY EVENT
# =========================================

@bot.event
async def on_ready():
    print("BOT READY")
    print("Commands loaded:", [c.name for c in bot.tree.get_commands()])


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
async def addplayer(interaction: discord.Interaction, epic_id: str, elims: int, playtime: int):

    current_date = datetime.now().strftime("%Y-%m-%d")

    conn, cursor = get_db()

    cursor.execute("""
    INSERT INTO players (epic_id, elims, playtime, register_date)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (epic_id)
    DO UPDATE SET
        elims = EXCLUDED.elims,
        playtime = EXCLUDED.playtime,
        register_date = EXCLUDED.register_date
    """, (
        epic_id,
        elims,
        playtime,
        current_date
    ))

    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="Player Saved",
        description=f"Player `{epic_id}` updated."
    )

    embed.add_field(name="Elims", value=str(elims), inline=False)
    embed.add_field(name="Playtime", value=f"{playtime}h", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================
# /STATS
# =========================================

@bot.tree.command(
    name="stats",
    description="View player stats",
)
async def stats(interaction: discord.Interaction, epic_id: str):

    conn, cursor = get_db()

    cursor.execute("""
    SELECT * FROM players
    WHERE epic_id = %s
    """, (epic_id,))

    result = cursor.fetchone()
    conn.close()

    if result:

        embed = discord.Embed(title=f"Stats for {result[0]}")
        embed.add_field(name="Elims", value=str(result[1]), inline=False)
        embed.add_field(name="Playtime", value=f"{result[2]}h", inline=False)
        embed.add_field(name="Registered", value=result[3], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    else:
        await interaction.response.send_message("Player not found.", ephemeral=True)


# =========================================
# /TOPELIMS
# =========================================

@bot.tree.command(
    name="topelims",
    description="Top elims leaderboard",
)
async def topelims(interaction: discord.Interaction):

    conn, cursor = get_db()

    cursor.execute("""
    SELECT epic_id, elims
    FROM players
    ORDER BY elims DESC
    LIMIT 10
    """)

    results = cursor.fetchall()
    conn.close()

    embed = discord.Embed(title="Top Elims")

    if not results:
        embed.description = "No players found."
    else:
        text = ""
        for i, row in enumerate(results, start=1):
            text += f"#{i} • `{row[0]}` • {row[1]} elims\n"
        embed.description = text

    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================
# /TOPPLAYTIME
# =========================================

@bot.tree.command(
    name="topplaytime",
    description="Top playtime leaderboard",
)
async def topplaytime(interaction: discord.Interaction):

    conn, cursor = get_db()

    cursor.execute("""
    SELECT epic_id, playtime
    FROM players
    ORDER BY playtime DESC
    LIMIT 10
    """)

    results = cursor.fetchall()
    conn.close()

    embed = discord.Embed(title="Top Playtime")

    if not results:
        embed.description = "No players found."
    else:
        text = ""
        for i, row in enumerate(results, start=1):
            text += f"#{i} • `{row[0]}` • {row[1]}h\n"
        embed.description = text

    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================
# RUN BOT
# =========================================

print("Starting bot...")
bot.run(TOKEN)
