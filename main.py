import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
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

# Ordered list of rank role IDs from highest to lowest for permissions and sorting
RANK_ORDER = [
    ROLE_IDS["Superintendent"],
    ROLE_IDS["Deputy Superintendent"],
    ROLE_IDS["Colonel"],
    ROLE_IDS["Lieutenant Colonel"],
    ROLE_IDS["Major"],
    ROLE_IDS["Captain"],
    ROLE_IDS["Lieutenant"],
    ROLE_IDS["Sergeant"],
    ROLE_IDS["Corporal"],
    ROLE_IDS["Master Trooper"],
    ROLE_IDS["Trooper"],
]

# Quotas mapped by role ID
QUOTAS = {
    ROLE_IDS["Trooper"]: 2.0,
    ROLE_IDS["Master Trooper"]: 2.0,
    ROLE_IDS["Corporal"]: 2.0,
    ROLE_IDS["Sergeant"]: 1.5,
    ROLE_IDS["Lieutenant"]: 1.5,
    ROLE_IDS["Captain"]: 1.0,
    ROLE_IDS["Major"]: 1.0,
}

# Exempt roles by role ID
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

# Database setup with additional rating and notes columns
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

# ... [no change to earlier logic] ...

    for member in guild.members:
        member_roles_ids = {role.id for role in member.roles}
        member_ranks = [rid for rid in RANK_ORDER if rid in member_roles_ids]
        if not member_ranks:
            continue

        main_rank_role_id = member_ranks[0]

        # Skip exempt ranks entirely
        if main_rank_role_id in EXEMPT:
            continue

        uid = str(member.id)
        total_hours = logged_users.get(uid, (0, main_rank_role_id))[0]

        h = int(total_hours)
        m = int(round((total_hours - h) * 60))
        time_str = f"{h}h {m}m"

        has_loa = ROLE_IDS["LOA"] in member_roles_ids
        has_roa = ROLE_IDS["ROA"] in member_roles_ids

        if has_loa:
            symbol = "📘 Leave of Absence"
        elif main_rank_role_id in QUOTAS:
            required = QUOTAS[main_rank_role_id]
            if has_roa:
                required /= 2  # 50% quota for ROA
            passed = total_hours >= required
            symbol = "<:ROA:1394778057822441542>" if passed and has_roa else ("✅" if passed else "❌")
        else:
            symbol = "❌"

        rank_name = None
        for name, rid in ROLE_IDS.items():
            if rid == main_rank_role_id:
                rank_name = name
                break

        message += f"- {member.mention} ({rank_name or 'Unknown'}): {time_str} {symbol}\n"
        user_found = True

# ... [rest of the code continues unchanged] ...

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

    member_role_ids = {role.id for role in interaction.user.roles}
    allowed_roles = set(RANK_ORDER[:6])  # Captain+
    if not member_role_ids.intersection(allowed_roles):
        await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)
        return

    c.execute("DELETE FROM shifts")
    conn.commit()

    await interaction.followup.send("✅ All quota logs have been cleared.", ephemeral=True)

bot.run(TOKEN)
