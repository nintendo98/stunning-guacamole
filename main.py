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

# RANK ORDER list (high to low)
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

# Quotas mapped by rank name
QUOTAS = {
    "Trooper": 2.0,
    "Master Trooper": 2.0,
    "Corporal": 2.0,
    "Sergeant": 1.5,
    "Lieutenant": 1.5,
    "Captain": 1.0,
    "Major": 1.0,
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

# Database setup (same as before, add rating and notes)
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

def normalize_time(t: str) -> str:
    t = t.strip().upper().replace("AM", " AM").replace("PM", " PM")
    if not ("AM" in t or "PM" in t):
        raise ValueError("AM/PM missing")
    return t

def get_highest_rank_role_id(member: discord.Member):
    member_roles = {role.name for role in member.roles}
    for rank_name in RANK_ORDER:
        if rank_name in member_roles:
            return ROLE_IDS[rank_name]
    return None

def get_highest_rank_name(member: discord.Member):
    member_roles = {role.name for role in member.roles}
    for rank_name in RANK_ORDER:
        if rank_name in member_roles:
            return rank_name
    return None

def has_permission_for_others(member: discord.Member):
    # Lt. Colonel and above can log shifts for others
    member_roles = {role.name for role in member.roles}
    allowed_ranks = RANK_ORDER[:4]  # Superintendent, Deputy Superintendent, Colonel, Lieutenant Colonel
    return any(rank in member_roles for rank in allowed_ranks)

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

    # Permission check for logging others
    if user and not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to log shifts for others.", ephemeral=True)
        return

    # Validate rating
    if rating is not None and (rating < 0 or rating > 10):
        await interaction.response.send_message("❌ Rating must be between 0 and 10.", ephemeral=True)
        return

    try:
    # Try to parse time_started and time_ended using dateutil parser
    # This allows flexible parsing (12h or 24h)
        t_start = parser.parse(time_started)
        t_end = parser.parse(time_ended)

        duration = (t_end - t_start).total_seconds() / 3600.0
        if duration < 0:
        duration += 24
except Exception:
    await interaction.response.send_message("❌ Invalid time format. Use `1:10 PM`, `3:30am`, `13:00`, etc.", ephemeral=True)
    return

    rank_role_id = ROLE_IDS.get(rank.value)
    if not rank_role_id:
        await interaction.response.send_message("❌ Invalid rank selected.", ephemeral=True)
        return

    # Insert shift into DB
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

    embed = discord.Embed(title="🚓 Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=target_user.mention, inline=True)
    embed.add_field(name="Rank", value=rank.value, inline=True)
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

# You can add your other commands here (countallquota, resetquota) similarly fixed if needed

bot.run(TOKEN)
