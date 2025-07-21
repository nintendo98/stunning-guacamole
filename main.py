import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
from dateutil import parser
from datetime import datetime
import os
from flask import Flask
from threading import Thread

# Keep-alive webserver (Replit/Render)
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# ENV Variables
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# Role IDs dictionary
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

# RANK ORDER list (IDs, high to low)
RANK_ORDER = [
    1393070510040154196,  # Superintendent
    1393344391522943206,  # Deputy Superintendent
    1393070827934580786,  # Colonel
    1393357571892445206,  # Lieutenant Colonel
    1393071057279258806,  # Major
    1393070960206413824,  # Captain
    1393071005022425090,  # Lieutenant
    1393071092746158110,  # Sergeant
    1393071122836095078,  # Corporal
    1393071163617579038,  # Master Trooper
    1393071210908221543,  # Trooper
]

# Quotas mapped by rank name
QUOTAS = {
    "Trooper": 0.5,
    "Master Trooper": 0.5,
    "Corporal": 0.5,
    "Sergeant": 0.5,
    "Lieutenant": 0.5,
    "Captain": 0.5,
    "Major": 0.5,
}

# Exempt ranks set
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

# Database setup (add rating and notes)
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
    member_role_ids = [role.id for role in member.roles]
    for role_id in RANK_ORDER:
        if role_id in member_role_ids:
            return role_id
    return None

def has_permission_for_others(member: discord.Member):
    allowed_roles = set(RANK_ORDER[:4])  # Top 4 ranks
    member_role_ids = {role.id for role in member.roles}
    return bool(allowed_roles & member_role_ids)

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
            r = requests.get("https://shift-logger-bot.onrender.com/")
            print(f"Self-ping {r.status_code} at {datetime.utcnow()}")
        except Exception as e:
            print("Ping failed:", e)
        await asyncio.sleep(300)

@bot.tree.command(name="logshift", description="Log your WSP shift or for others (Lt. Colonel+ only)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    user="User to log shift for (Lt. Colonel+ only)",
    session_host="Who hosted the session?",
    time_started="Start time (e.g. 1:00 PM)",
    time_ended="End time (e.g. 3:15 PM)",
    rank="Your rank during the shift",
    rating="Shift rating 0-10 (optional)",
    notes="Additional notes (optional)"
)
@app_commands.choices(rank=[
    app_commands.Choice(name=name, value=role_id)
    for name, role_id in ROLE_IDS.items()
    if role_id in RANK_ORDER
])
async def logshift(
    interaction: discord.Interaction,
    session_host: str,
    time_started: str,
    time_ended: str,
    rank: app_commands.Choice[int],
    user: discord.Member = None,
    rating: int = None,
    notes: str = None
):
    target_user = user or interaction.user

    if user and not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to log shifts for others.", ephemeral=True)
        return

    if rating is not None and (rating < 0 or rating > 10):
        await interaction.response.send_message("❌ Rating must be between 0 and 10.", ephemeral=True)
        return

    try:
        t_start = parser.parse(time_started)
        t_end = parser.parse(time_ended)
        duration = (t_end - t_start).total_seconds() / 3600.0
        if duration < 0:
            duration += 24
    except Exception:
        await interaction.response.send_message("❌ Invalid time format. Use `1:10 PM`, `3:30am`, `13:00`, etc.", ephemeral=True)
        return

    c.execute("INSERT INTO shifts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        str(target_user.id),
        str(target_user),
        session_host,
        time_started,
        time_ended,
        rank.value,
        round(duration, 2),
        rating,
        notes
    ))
    conn.commit()

    embed = discord.Embed(title="🚓 Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=target_user.mention, inline=True)
    embed.add_field(name="Rank", value=rank.name, inline=True)
    embed.add_field(name="Session Host", value=session_host, inline=False)
    embed.add_field(name="Time", value=f"{time_started} - {time_ended}", inline=False)
    embed.add_field(name="Duration", value=f"{round(duration, 2)} hours", inline=True)
    if rating is not None:
        embed.add_field(name="Shift Rating", value=str(rating), inline=True)
    if notes:
        embed.add_field(name="Notes", value=notes, inline=False)
    embed.timestamp = datetime.utcnow()

    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Shift logged successfully.", ephemeral=True)

bot.run(TOKEN)
