import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
from datetime import datetime
import os
from flask import Flask
from threading import Thread

# Keep-alive webserver (for Replit/Render)
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

# Role IDs
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
    "Trooper"
]

QUOTAS = {
    ROLE_IDS["Trooper"]: 2.0,
    ROLE_IDS["Master Trooper"]: 2.0,
    ROLE_IDS["Corporal"]: 2.0,
    ROLE_IDS["Sergeant"]: 1.5,
    ROLE_IDS["Lieutenant"]: 1.5,
    ROLE_IDS["Captain"]: 1.0,
    ROLE_IDS["Major"]: 1.0,
}

EXEMPT = {
    ROLE_IDS["Lieutenant Colonel"],
    ROLE_IDS["Colonel"],
    ROLE_IDS["Deputy Superintendent"],
    ROLE_IDS["Superintendent"],
}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

db = sqlite3.connect("data.db", check_same_thread=False)
c = db.cursor()
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
db.commit()

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="logshift", description="Log a shift", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    session_host="Who hosted the session?",
    time_started="Time started (e.g. 13:00 or 1:00 PM)",
    time_ended="Time ended (e.g. 15:00 or 3:00 PM)",
    rating="Optional shift rating 1-10",
    notes="Optional notes"
)
async def logshift(interaction: discord.Interaction, 
                   session_host: str,
                   time_started: str,
                   time_ended: str,
                   rating: int = None,
                   notes: str = None):

    member = interaction.user
    member_role_ids = {role.id for role in member.roles}
    matched_ranks = [r for r in RANK_ORDER if ROLE_IDS[r] in member_role_ids]

    if not matched_ranks:
        await interaction.response.send_message("❌ You do not have a loggable rank.", ephemeral=True)
        return

    rank_name = matched_ranks[0]
    rank_id = ROLE_IDS[rank_name]

    # Time parsing
    def parse_time(t):
        t = t.strip().upper()
        try:
            if "AM" in t or "PM" in t:
                return datetime.strptime(t, "%I:%M %p")
            return datetime.strptime(t, "%H:%M")
        except:
            raise ValueError("Invalid time format")

    try:
        start = parse_time(time_started)
        end = parse_time(time_ended)
        duration = (end - start).total_seconds() / 3600
        if duration < 0:
            duration += 24
    except:
        await interaction.response.send_message("❌ Invalid time format.", ephemeral=True)
        return

    c.execute("INSERT INTO shifts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        str(member.id), str(member), session_host, time_started, time_ended, rank_id, round(duration, 2), rating, notes
    ))
    db.commit()

    embed = discord.Embed(title="🚓 Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Rank", value=rank_name, inline=True)
    embed.add_field(name="Session Host", value=session_host, inline=False)
    embed.add_field(name="Time", value=f"{time_started} - {time_ended}", inline=False)
    embed.add_field(name="Duration", value=f"{round(duration, 2)} hours", inline=True)
    if rating: embed.add_field(name="Rating", value=str(rating), inline=True)
    if notes: embed.add_field(name="Notes", value=notes, inline=False)
    embed.timestamp = datetime.utcnow()

    await interaction.response.send_message("✅ Shift logged successfully.", ephemeral=True)
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

bot.run(TOKEN)
