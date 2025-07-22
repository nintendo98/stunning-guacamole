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
    "WSP": 1226292433503916104,
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
    "Trooper": 3.5,
    "Master Trooper": 3.0,
    "Corporal": 2.5,
    "Sergeant": 2.0,
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

# ... everything else remains exactly the same ...

@bot.tree.command(name="countallquota", description="Check everyone's quota", guild=discord.Object(id=GUILD_ID))
async def countallquota(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not has_permission_for_quota_commands(interaction.user):
        await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)
        return

    c.execute("""
        SELECT user_id, SUM(duration), MAX(rowid)
        FROM shifts
        GROUP BY user_id
    """)
    results = c.fetchall()

    user_data = {}
    for user_id, total_duration, max_rowid in results:
        c.execute("SELECT rank_role_id FROM shifts WHERE rowid = ?", (max_rowid,))
        last_rank_role_id = c.fetchone()[0]
        user_data[user_id] = (total_duration or 0, last_rank_role_id)

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.followup.send("❌ Guild not found.", ephemeral=True)
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
        "Activity Requirements can be found in the database.\n\n"
    )

    any_logged = False

    for member in guild.members:
        if not any(role.id == ROLE_IDS["WSP"] for role in member.roles):
            continue

        rank_name = get_highest_rank_name(member)
        if not rank_name:
            continue

        user_id_str = str(member.id)
        total_hours, _ = user_data.get(user_id_str, (0, ROLE_IDS.get(rank_name)))

        h = int(total_hours)
        m = int(round((total_hours - h) * 60))
        time_str = f"{h}h {m}m"

        has_loa = any(role.id == ROLE_IDS["LOA"] for role in member.roles)
        has_roa = any(role.id == ROLE_IDS["ROA"] for role in member.roles)

        if has_loa:
            symbol = "📘 Leave of Absence"
        elif rank_name in EXEMPT:
            symbol = "✴️ Exempt"
        elif rank_name in QUOTAS:
            required_quota = QUOTAS[rank_name] / 2 if has_roa else QUOTAS[rank_name]
            passed = total_hours >= required_quota
            symbol = "<:ROA:1394778057822441542>" if passed and has_roa else ("✅" if passed else "❌")
        else:
            symbol = "❌"

        message += f"- {member.mention} ({rank_name}): {time_str} {symbol}\n"
        any_logged = True

    if not any_logged:
        await interaction.followup.send("❌ No quota has been logged.", ephemeral=True)
        return

    c.execute("DELETE FROM shifts")
    conn.commit()

    await interaction.followup.send(message)

# No other logic changed in the rest of your script.

bot.run(TOKEN)
