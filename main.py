import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
from dateutil import parser
from datetime import datetime, timedelta
import os
from flask import Flask
from threading import Thread

# Flask server for keeping bot alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# ENV variables
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

# Quota requirements
QUOTAS = {
    "Trooper": 2.0,
    "Master Trooper": 2.0,
    "Corporal": 2.0,
    "Sergeant": 1.5,
    "Lieutenant": 1.5,
    "Captain": 1.0,
    "Major": 1.0,
}

# Roles exempt from quota
EXEMPT = {"Lieutenant Colonel", "Colonel", "Deputy Superintendent", "Superintendent"}
LEAVE_ROLES = {ROLE_IDS["LOA"], ROLE_IDS["ROA"]}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# SQLite database
conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS shifts (
    user_id TEXT,
    username TEXT,
    session_host TEXT,
    time_in TEXT,
    time_out TEXT,
    rank_role_id INTEGER,
    duration REAL,
    rating INTEGER,
    notes TEXT
)''')
conn.commit()

def get_highest_rank(member: discord.Member):
    for rank in RANK_ORDER:
        if any(role.name == rank for role in member.roles):
            return rank
    return None

def has_permission_for_others(member: discord.Member):
    return get_highest_rank(member) in RANK_ORDER[:4]

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

@bot.tree.command(name="logshift", description="Log your WSP shift", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    user="User to log shift for (Lt. Colonel+ only)",
    session_host="Who hosted the session?",
    time_started="Start time (e.g. 13:00 or 1:00 PM)",
    time_ended="End time (e.g. 15:30 or 3:30 PM)",
    rank="Your rank during the shift",
    rating="Shift rating 0–10 (optional)",
    notes="Additional notes (optional)"
)
@app_commands.choices(rank=[app_commands.Choice(name=r, value=r) for r in RANK_ORDER])
async def logshift(interaction: discord.Interaction, session_host: str, time_started: str, time_ended: str, rank: app_commands.Choice[str], user: discord.Member = None, rating: int = None, notes: str = None):
    target = user or interaction.user

    if user and not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to log shifts for others.", ephemeral=True)
        return

    if rating is not None and (rating < 0 or rating > 10):
        await interaction.response.send_message("❌ Rating must be between 0 and 10.", ephemeral=True)
        return

    try:
        t_start = parser.parse(time_started)
        t_end = parser.parse(time_ended)
        duration = (t_end - t_start).total_seconds() / 3600
        if duration < 0:
            duration += 24
    except:
        await interaction.response.send_message("❌ Invalid time format. Use `13:00`, `3:00 PM`, etc.", ephemeral=True)
        return

    rank_role_id = ROLE_IDS.get(rank.value)
    if not rank_role_id:
        await interaction.response.send_message("❌ Invalid rank.", ephemeral=True)
        return

    c.execute("INSERT INTO shifts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        str(target.id), str(target), session_host,
        time_started, time_ended, rank_role_id,
        round(duration, 2), rating, notes
    ))
    conn.commit()

    embed = discord.Embed(title="🚓 Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=target.mention, inline=True)
    embed.add_field(name="Rank", value=rank.value, inline=True)
    embed.add_field(name="Session Host", value=session_host, inline=False)
    embed.add_field(name="Time", value=f"{time_started} - {time_ended}", inline=False)
    embed.add_field(name="Duration", value=f"{round(duration, 2)} hours", inline=True)
    if rating is not None:
        embed.add_field(name="Rating", value=str(rating), inline=True)
    if notes:
        embed.add_field(name="Notes", value=notes, inline=False)
    embed.timestamp = datetime.utcnow()

    await interaction.response.send_message("✅ Shift logged!", ephemeral=True)
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

@bot.tree.command(name="countallquota", description="Count quota for all users", guild=discord.Object(id=GUILD_ID))
async def countallquota(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    guild = interaction.guild
    await guild.chunk()

    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    c.execute("SELECT * FROM shifts")
    all_shifts = c.fetchall()

    shift_data = {}
    for shift in all_shifts:
        user_id, _, _, time_in, _, role_id, duration, _, _ = shift
        try:
            if parser.parse(time_in) >= two_weeks_ago:
                shift_data.setdefault(user_id, []).append((int(role_id), float(duration)))
        except:
            continue

    lines = []
    for member in guild.members:
        if not any(role.id in ROLE_IDS.values() for role in member.roles):
            continue

        if any(role.id in LEAVE_ROLES for role in member.roles):
            lines.append(f"{member.mention} — **LOA/ROA**")
            continue

        rank = get_highest_rank(member)
        if not rank or rank in EXEMPT:
            continue

        quota_required = QUOTAS.get(rank, 0)
        shifts = shift_data.get(str(member.id), [])
        total_hours = sum(d for _, d in shifts if _ == ROLE_IDS[rank])
        status = "✅ Met" if total_hours >= quota_required else "❌ Not Met"
        lines.append(f"{member.mention} — **{rank}** — {total_hours:.2f}h / {quota_required}h — {status}")

    await interaction.followup.send("\n".join(lines) or "No eligible members found.")

@bot.tree.command(name="resetquota", description="Clear all logged shifts", guild=discord.Object(id=GUILD_ID))
async def resetquota(interaction: discord.Interaction):
    if not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ Only Lt. Colonel+ can use this.", ephemeral=True)
        return

    c.execute("DELETE FROM shifts")
    conn.commit()
    await interaction.response.send_message("🗑️ All shift data has been reset.", ephemeral=False)

bot.run(TOKEN)
