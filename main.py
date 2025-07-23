import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import sqlite3
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

TOKEN = "YOUR_BOT_TOKEN"
GUILD_ID = YOUR_GUILD_ID  # Replace with your server's ID
DATABASE = "shifts.db"

# Role IDs
WSP_ROLE_ID = 1226292433503916104
LOA_ROLE_ID = 1393373147545341992
ROA_ROLE_ID = 1394775443634131074

# Rank Role IDs
RANK_ROLE_IDS = {
    "trooper": 1393071210908221543,
    "master trooper": 1393071163617579038,
    "corporal": 1393071122836095078,
    "sergeant": 1393071092746158110,
    "lieutenant": 1393071005022425090,
    "captain": 1393070960206413824,
    "major": 1393071057279258806,
    "lieutenant colonel": 1393357571892445206,
    "colonel": 1393070827934580786,
    "deputy superintendent": 1393344391522943206,
    "superintendent": 1393070510040154196
}

# Quota requirements by rank (in hours per 2 weeks)
QUOTA_REQUIREMENTS = {
    "trooper": 2,
    "master trooper": 2,
    "corporal": 2,
    "sergeant": 2.5,
    "lieutenant": 3,
    "captain": 3.5,
    "major": 3.5,
    "lieutenant colonel": 4,
    "colonel": 4,
    "deputy superintendent": 4,
    "superintendent": 4
}

conn = sqlite3.connect(DATABASE)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS shifts (
    user_id TEXT,
    username TEXT,
    rank TEXT,
    duration REAL,
    timestamp TEXT
)
""")
conn.commit()

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="logshift", description="Log your patrol shift", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(rank="Your current rank", duration="Shift duration in hours (e.g. 1.5)")
async def logshift(interaction: discord.Interaction, rank: str, duration: float):
    user = interaction.user
    member = interaction.guild.get_member(user.id)

    # WSP check
    wsp_role = discord.Object(id=WSP_ROLE_ID)
    if WSP_ROLE_ID not in [role.id for role in member.roles]:
        await interaction.response.send_message("❌ You are not in the Wisconsin State Patrol.", ephemeral=True)
        return

    rank = rank.lower()
    if rank not in QUOTA_REQUIREMENTS:
        await interaction.response.send_message("❌ Invalid rank entered.", ephemeral=True)
        return

    timestamp = datetime.utcnow().isoformat()
    c.execute("INSERT INTO shifts (user_id, username, rank, duration, timestamp) VALUES (?, ?, ?, ?, ?)",
              (str(user.id), str(user), rank, duration, timestamp))
    conn.commit()

    await interaction.response.send_message(f"✅ Shift logged: {rank.title()}, {duration} hour(s).", ephemeral=True)

@bot.tree.command(name="countallquota", description="Admin command to count quota for all WSP members", guild=discord.Object(id=GUILD_ID))
async def countallquota(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    members = await guild.fetch_members(limit=None).flatten()

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=14)

    c.execute("SELECT user_id, SUM(duration) FROM shifts WHERE timestamp >= ? GROUP BY user_id", (start_time.isoformat(),))
    user_durations = dict(c.fetchall())

    embed = discord.Embed(title="📊 Quota Count-up Results (Last 14 Days)", color=discord.Color.blue())
    embed.description = (
        "__Quota key:__\n"
        "✴️ - Exempt\n"
        "❌ - Quota Not Met\n"
        "✅ - Quota Met\n"
        "📘 - Leave of Absence\n\n"
        "<:ROA:1394778057822441542> - ROA (Reduced Quota Met)\n\n"
        "__Activity Requirements:__\n"
        "See database for required hours by rank."
    )

    for member in members:
        if WSP_ROLE_ID not in [role.id for role in member.roles]:
            continue

        status = "✴️"
        loa = ROA = False

        if LOA_ROLE_ID in [role.id for role in member.roles]:
            status = "📘"
        elif ROA_ROLE_ID in [role.id for role in member.roles]:
            ROA = True

        for rank, role_id in RANK_ROLE_IDS.items():
            if role_id in [role.id for role in member.roles]:
                user_hours = user_durations.get(str(member.id), 0)
                required = QUOTA_REQUIREMENTS.get(rank, 2)
                if LOA_ROLE_ID in [r.id for r in member.roles]:
                    status = "📘"
                elif ROA:
                    status = "<:ROA:1394778057822441542>" if user_hours >= required / 2 else "❌"
                else:
                    status = "✅" if user_hours >= required else "❌"
                embed.add_field(name=f"{member.display_name}", value=f"{status} ({user_hours:.1f} hrs)", inline=False)
                break

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="resetquota", description="Reset all quota logs (admin only)", guild=discord.Object(id=GUILD_ID))
async def resetquota(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    c.execute("DELETE FROM shifts")
    conn.commit()
    await interaction.response.send_message("✅ All quota logs have been reset.")

@bot.tree.command(name="deletelastshift", description="Delete your most recently logged shift", guild=discord.Object(id=GUILD_ID))
async def deletelastshift(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    c.execute("SELECT rowid FROM shifts WHERE user_id = ? ORDER BY rowid DESC LIMIT 1", (user_id,))
    result = c.fetchone()

    if not result:
        await interaction.response.send_message("❌ You have no shifts to delete.", ephemeral=True)
        return

    rowid = result[0]
    c.execute("DELETE FROM shifts WHERE rowid = ?", (rowid,))
    conn.commit()

    await interaction.response.send_message("✅ Your most recent shift has been deleted.", ephemeral=True)

bot.run(TOKEN)
