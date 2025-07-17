import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
from datetime import datetime
import os
from flask import Flask
from threading import Thread
from datetime import datetime

# Keep-alive webserver (Replit)
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

# Bot setup
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
    rank TEXT,
    duration REAL
)
''')
conn.commit()

# Ranks and quotas
RANKS = [
    "Superintendent", "Deputy Superintendent", "Colonel", "Lieutenant Colonel",
    "Major", "Captain", "Lieutenant", "Sergeant", "Corporal", "Master Trooper", "Trooper"
]
QUOTAS = {
    "Trooper": 2.0,
    "Master Trooper": 2.0,
    "Corporal": 2.0,
    "Sergeant": 1.5,
    "Lieutenant": 1.5,
    "Captain": 1.0,
    "Major": 1.0
}
EXEMPT = {"Lieutenant Colonel", "Colonel", "Deputy Superintendent", "Superintendent"}

def normalize_time(t):
    t = t.strip().upper().replace("AM", " AM").replace("PM", " PM")
    if not ("AM" in t or "PM" in t):
        raise ValueError("AM/PM missing")
    return t

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Bot is online as {bot.user}")
    bot.loop.create_task(background_task())  # Start the background loop


async def background_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        print("🔁 Background task running...")

        # Optional: Ping your own Flask site to keep Replit awake
        try:
            import requests
            r = requests.get("https://fb0bffd4-34e0-47d4-81c5-00cfe4b76154-00-nhzskekk44xj.riker.replit.dev/")  # Your actual Replit URL
            print(f"Self-ping response: {r.status_code} at {datetime.utcnow()}")
        except Exception as e:
            print("Ping failed:", e)

        await asyncio.sleep(300)  # Sleep for 5 minutes (300 seconds)


@bot.tree.command(name="logshift", description="Log your WSP shift", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    session_host="Who hosted the session?",
    time_started="Start time (e.g. 1:00 PM)",
    time_ended="End time (e.g. 3:15 PM)",
    rank="Your rank during the shift"
)
@app_commands.choices(rank=[app_commands.Choice(name=r, value=r) for r in RANKS])
async def logshift(interaction: discord.Interaction, session_host: str, time_started: str, time_ended: str, rank: app_commands.Choice[str]):
    user = interaction.user

    try:
        fmt = "%I:%M %p"
        t_start = datetime.strptime(normalize_time(time_started), fmt)
        t_end = datetime.strptime(normalize_time(time_ended), fmt)
        duration = (t_end - t_start).total_seconds() / 3600.0
        if duration < 0:
            duration += 24
    except Exception:
        await interaction.response.send_message("❌ Invalid time format. Use `1:10 PM`, `3:30am`, etc.", ephemeral=True)
        return

    c.execute("INSERT INTO shifts VALUES (?, ?, ?, ?, ?, ?, ?)", (
        str(user.id), str(user), session_host, time_started, time_ended, rank.value, round(duration, 2)
    ))
    conn.commit()

    embed = discord.Embed(title="🚓 Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=user.mention, inline=True)
    embed.add_field(name="Rank", value=rank.value, inline=True)
    embed.add_field(name="Session Host", value=session_host, inline=False)
    embed.add_field(name="Time", value=f"{time_started} - {time_ended}", inline=False)
    embed.add_field(name="Duration", value=f"{round(duration, 2)} hours", inline=True)
    embed.timestamp = datetime.utcnow()

    await interaction.channel.send(embed=embed)


    await interaction.response.send_message("✅ Shift logged successfully.", ephemeral=True)

@bot.tree.command(name="countallquota", description="Check everyone's quota", guild=discord.Object(id=GUILD_ID))
async def countallquota(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    member_roles = [role.name for role in interaction.user.roles]
    if not any(role in RANKS[:6] for role in member_roles):  # Captain+
        await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)
        return

    c.execute("SELECT user_id, SUM(duration), (SELECT rank FROM shifts s2 WHERE s2.user_id = s.user_id ORDER BY ROWID DESC LIMIT 1) FROM shifts s GROUP BY user_id")
    results = c.fetchall()
    logged_users = {uid: (total or 0, rank or "Unknown") for uid, total, rank in results}

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.followup.send("Guild not found.", ephemeral=True)
        return

    message = (
        "**2-Week Quota Count-up Results are now out!**\n"
        "__Quota key:__\n"
        "✴️ - Exempt\n"
        "❌ - Quota Not Met\n"
        "✅  - Quota Met\n"
        "📘 - Leave of Absence\n\n"
        "<:ROA:1394778057822441542> - ROA (Reduced Quota Met)\n\n"
        "__Activity Requirements:__\n"
        "Activity Requirements can be found in the database.\n"
    )

    user_found = False

    for member in guild.members:
        ranks = [r.name for r in member.roles if r.name in RANKS]
        if not ranks:
            continue

        main_rank = sorted(ranks, key=lambda x: RANKS.index(x))[0]
        uid = str(member.id)
        total_hours = logged_users.get(uid, (0, main_rank))[0]

        h = int(total_hours)
        m = int(round((total_hours - h) * 60))
        time_str = f"{h}h {m}m"

        # LOA Check
        has_loa = any(r.name == "LOA - WSP" for r in member.roles)
        has_roa = any(r.name == "ROA - WSP" for r in member.roles)

        if has_loa:
            symbol = "📘 Leave of Absence"
        elif main_rank in EXEMPT:
            symbol = "✴️ Exempt"
        elif main_rank in QUOTAS:
            required = QUOTAS[main_rank]
            if has_roa:
                required /= 2  # 50% quota for ROA
            passed = total_hours >= required
            symbol = "<:ROA:1394778057822441542>" if passed and has_roa else ("✅" if passed else "❌")
        else:
            symbol = "❌"


        message += f"- {member.mention} ({main_rank}): {time_str} {symbol}\n"
        user_found = True

    if not user_found:
        await interaction.followup.send("❌ No quota has been logged.", ephemeral=True)
        return

    # Clear logs after reporting
    c.execute("DELETE FROM shifts")
    conn.commit()

    await interaction.followup.send(message)

@bot.tree.command(name="resetquota", description="Clear all logged quota data", guild=discord.Object(id=GUILD_ID))
async def resetquota(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    member_roles = [role.name for role in interaction.user.roles]
    if not any(role in RANKS[:6] for role in member_roles):  # Captain+
        await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)
        return

    c.execute("DELETE FROM shifts")
    conn.commit()

    await interaction.followup.send("✅ All quota logs have been cleared.", ephemeral=True)

bot.run(TOKEN)
