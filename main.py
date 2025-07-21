import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
from dateutil import parser
from datetime import datetime, timedelta, timezone
import os
from flask import Flask
from threading import Thread

# Web server to keep alive (Render)
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# ENV variables
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# Roles and rank logic
ROLE_IDS = {
    "Superintendent": 1393070510040154196,
    "Deputy Superintendent": 1393344391522943206,
    "Colonel": 1393070827934580786,
    "Lieutenant Colonel": 1393357571892445206,
    "Major": 1393071057279258806,
    "Captain": 1393070960206413824,
    "Lieutenant": 1393071005022425090,
    "Sergeant": 1393071092746158110,
    "Corporal": 1393071122836095078,
    "Master Trooper": 1393071163617579038,
    "Trooper": 1393071210908221543,
    "ROA": 1394775443634131074,
    "LOA": 1393373147545341992,
}

RANK_ORDER = [
    "Superintendent",
    "Deputy Superintendent",
    "Colonel",
    "Lieutenant Colonel",
    "Major",
    "Captain",
    "Lieutenant",
    "Sergeant",
    "Corporal",
    "Master Trooper",
    "Trooper",
]

QUOTAS = {
    "Trooper": 2.0,
    "Master Trooper": 2.0,
    "Corporal": 2.0,
    "Sergeant": 1.5,
    "Lieutenant": 1.5,
    "Captain": 1.0,
    "Major": 1.0,
}

EXEMPT = {
    "Lieutenant Colonel",
    "Colonel",
    "Deputy Superintendent",
    "Superintendent",
}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Database setup
conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS shifts (
    user_id TEXT,
    username TEXT,
    session_host TEXT,
    time_in TEXT,
    time_out TEXT,
    rank_role_id INTEGER,
    duration REAL,
    rating INTEGER,
    notes TEXT
)
''')
conn.commit()

def get_highest_rank_role_id(member: discord.Member):
    member_roles = {role.name for role in member.roles}
    for rank_name in RANK_ORDER:
        if rank_name in member_roles:
            return ROLE_IDS[rank_name]
    return None

def has_permission_for_others(member: discord.Member):
    allowed_ranks = RANK_ORDER[:4]  # Top 4 ranks allowed
    return any(role.name in allowed_ranks for role in member.roles)

def get_rank_name_from_role_id(role_id):
    for name, r_id in ROLE_IDS.items():
        if r_id == role_id:
            return name
    return "Unknown"

def get_member_rank(member: discord.Member):
    for rank in RANK_ORDER:
        if discord.utils.get(member.roles, name=rank):
            return rank
    return None

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Bot is online as {bot.user}")
    bot.loop.create_task(background_task())

async def background_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            import requests
            requests.get("https://shift-logger-bot.onrender.com/")
        except Exception as e:
            print("Ping failed:", e)
        await asyncio.sleep(300)

@bot.tree.command(name="logshift", description="Log a WSP shift", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    user="User to log shift for (Lt. Colonel+ only)",
    session_host="Who hosted the session?",
    time_started="Start time (e.g. 1:00 PM or 13:00)",
    time_ended="End time (e.g. 3:00 PM or 15:00)",
    rank="Your rank during the shift",
    rating="Shift rating 0-10 (optional)",
    notes="Any notes (optional)"
)
@app_commands.choices(rank=[app_commands.Choice(name=r, value=r) for r in RANK_ORDER])
async def logshift(
    interaction: discord.Interaction,
    session_host: str,
    time_started: str,
    time_ended: str,
    rank: app_commands.Choice[str],
    user: discord.Member = None,
    rating: int = None,
    notes: str = None
):
    target_user = user or interaction.user
    if user and not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ You can't log for others.", ephemeral=True)
        return

    if rating is not None and (rating < 0 or rating > 10):
        await interaction.response.send_message("❌ Rating must be 0–10.", ephemeral=True)
        return

    try:
        t_start = parser.parse(time_started)
        t_end = parser.parse(time_ended)
        duration = (t_end - t_start).total_seconds() / 3600.0
        if duration < 0:
            duration += 24
    except Exception:
        await interaction.response.send_message("❌ Invalid time format. Use 1:30 PM or 13:30", ephemeral=True)
        return

    rank_role_id = ROLE_IDS.get(rank.value)
    if not rank_role_id:
        await interaction.response.send_message("❌ Invalid rank.", ephemeral=True)
        return

    # Log in DB
    c.execute("INSERT INTO shifts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        str(target_user.id),
        str(target_user),
        session_host,
        time_started,
        time_ended,
        rank_role_id,
        round(duration, 2),
        rating,
        notes
    ))
    conn.commit()

    # Build embed for announcement
    embed = discord.Embed(title="✅ Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=target_user.mention, inline=True)
    embed.add_field(name="Rank", value=rank.value, inline=True)
    embed.add_field(name="Session Host", value=session_host, inline=False)
    embed.add_field(name="Time", value=f"{time_started} - {time_ended}", inline=False)
    embed.add_field(name="Duration", value=f"{round(duration, 2)} hours", inline=True)
    if rating is not None:
        embed.add_field(name="Rating", value=str(rating), inline=True)
    if notes:
        embed.add_field(name="Notes", value=notes, inline=False)
    embed.set_footer(text="WSP Shift Logger")
    embed.timestamp = datetime.now(timezone.utc)

    # Send embed announcement in the channel where the command was invoked
    await interaction.channel.send(embed=embed)

    await interaction.response.send_message("✅ Shift logged.", ephemeral=True)

@bot.tree.command(name="countallquota", description="Display the 2-week quota count results.")
async def countallquota(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Full message split into chunks under 2000 characters
    chunks = [
        "**2-Week Quota Count-up Results are now out!**\n"
        "__Quota key:__\n"
        "✴️ - Exempt\n"
        "❌ - Quota Not Met\n"
        "✅ - Quota Met\n"
        "📘 - Leave of Absence\n\n",
        
        "<:ROA:1394778057822441542> - ROA (Reduced Quota Met)\n\n"
        "__Activity Requirements:__\n"
        "Activity Requirements can be found in the database.\n\n",
        
        "**📊 Quota Summary (last 14 days)**\n\n"
        # Add more quota summary content here,
        # make sure each chunk is less than 2000 chars.
    ]

    # Example additional quota summary lines (add your real data here)
    quota_summary_lines = [
        "User1: ✅✅❌✅✅✅✅✅✅✅✅✅✅✅\n",
        "User2: ✅✅✅✅✅✅✅✅✅✅✅✅✅✅\n",
        # ...
    ]

    # To avoid breaking Discord limit, split quota summary if large
    summary_chunk = ""
    for line in quota_summary_lines:
        if len(summary_chunk) + len(line) > 1900:  # leave some room
            chunks.append(summary_chunk)
            summary_chunk = ""
        summary_chunk += line
    if summary_chunk:
        chunks.append(summary_chunk)

    # Send all chunks one by one
    for chunk in chunks:
        await interaction.followup.send(chunk, ephemeral=True)

@bot.tree.command(name="resetquota", description="Wipe all shift logs", guild=discord.Object(id=GUILD_ID))
async def resetquota(interaction: discord.Interaction):
    if not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    c.execute("DELETE FROM shifts")
    conn.commit()
    await interaction.response.send_message("🧹 All shift logs wiped.", ephemeral=True)

bot.run(TOKEN)
