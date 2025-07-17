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

def normalize_time(t):
    t = t.strip().upper().replace("AM", " AM").replace("PM", " PM")
    if not ("AM" in t or "PM" in t):
        raise ValueError("AM/PM missing")
    return t

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Bot is online as {bot.user}")
    bot.loop.create_task(background_task())

async def background_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        print("🔁 Background task running...")
        try:
            import requests
            # Replace with your actual keep-alive URL if needed
            r = requests.get("https://shift-logger-bot.onrender.com/")
            print(f"Self-ping response: {r.status_code} at {datetime.utcnow()}")
        except Exception as e:
            print("Ping failed:", e)
        await asyncio.sleep(300)  # 5 minutes

def get_highest_rank_role_id(member: discord.Member):
    member_role_ids = {role.id for role in member.roles}
    for rid in RANK_ORDER:
        if rid in member_role_ids:
            return rid
    return None

def has_permission_for_others(member: discord.Member):
    # Lt. Colonel and above can add shifts for others
    member_role_ids = {role.id for role in member.roles}
    allowed_roles = set(RANK_ORDER[:5])  # Top 5 roles (0-based indexing)
    return bool(member_role_ids.intersection(allowed_roles))

@bot.tree.command(name="logshift", description="Log your WSP shift or for others (if authorized)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    user="The user to log shift for (optional, requires Lt. Colonel+)",
    session_host="Who hosted the session?",
    time_started="Start time (e.g. 1:00 PM)",
    time_ended="End time (e.g. 3:15 PM)",
    rank="Rank during the shift",
    rating="Shift rating out of 10 (optional)",
    notes="Additional notes (optional)"
)
@app_commands.choices(rank=[app_commands.Choice(name=r, value=ROLE_IDS[r]) for r in RANK_ORDER if r in ROLE_IDS])
async def logshift(interaction: discord.Interaction, 
                   session_host: str, 
                   time_started: str, 
                   time_ended: str, 
                   rank: app_commands.Choice[int],
                   user: discord.Member = None,
                   rating: int = None,
                   notes: str = None):

    # If user is None, log for the interaction user
    target_user = user or interaction.user

    # Permission check if logging for others
    if user and not has_permission_for_others(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to log shifts for others.", ephemeral=True)
        return

    # Validate rating if provided
    if rating is not None and (rating < 1 or rating > 10):
        await interaction.response.send_message("❌ Rating must be between 1 and 10.", ephemeral=True)
        return

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

    c.execute("INSERT INTO shifts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        str(target_user.id), str(target_user), session_host, time_started, time_ended, rank.value, round(duration, 2),
        rating, notes
    ))
    conn.commit()

    rank_name = None
    for name, rid in ROLE_IDS.items():
        if rid == rank.value:
            rank_name = name
            break

    embed = discord.Embed(title="🚓 Shift Logged", color=discord.Color.blue())
    embed.add_field(name="User", value=target_user.mention, inline=True)
    embed.add_field(name="Rank", value=rank_name or "Unknown", inline=True)
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

@bot.tree.command(name="countallquota", description="Check everyone's quota", guild=discord.Object(id=GUILD_ID))
async def countallquota(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    # Check if user has Lieutenant Colonel+ roles by ID
    member_role_ids = [role.id for role in interaction.user.roles]
    allowed_ids = set([
        1393357571892445206,  # Lieutenant Colonel
        1393070827934580786,  # Colonel
        1393344391522943206,  # Deputy Superintendent
        1393070510040154196,  # Superintendent
        1393071057279258806,  # Major
        1393070960206413824   # Captain
    ])
    if not any(rid in allowed_ids for rid in member_role_ids):
        await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)
        return

    # Query shifts data, excluding rating and notes from duration sum
    c.execute("""
    SELECT user_id, SUM(duration), (
        SELECT rank_role_id FROM shifts s2 WHERE s2.user_id = s.user_id ORDER BY ROWID DESC LIMIT 1
    )
    FROM shifts s
    GROUP BY user_id
    """)
    results = c.fetchall()
    logged_users = {uid: (total or 0, rank or 0) for uid, total, rank in results}

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
        ranks = [role.id for role in member.roles if role.id in RANK_ROLE_IDS]
        if not ranks:
            continue

        # Highest rank based on order in RANK_ROLE_IDS list
        main_rank_id = sorted(ranks, key=lambda x: RANK_ROLE_IDS.index(x))[0]
        main_rank_name = RANKS[RANK_ROLE_IDS.index(main_rank_id)]

        uid = str(member.id)
        total_hours = logged_users.get(uid, (0, main_rank_id))[0]

        has_loa = any(role.id == LOA_ROLE_ID for role in member.roles)
        has_roa = any(role.id == ROA_ROLE_ID for role in member.roles)

        if main_rank_name in EXEMPT:
            symbol = "✴️ Exempt"
            time_str = ""  # Hide time for exempt
        elif has_loa:
            symbol = "📘 Leave of Absence"
            h = int(total_hours)
            m = int(round((total_hours - h) * 60))
            time_str = f"{h}h {m}m"
        elif main_rank_name in QUOTAS:
            required = QUOTAS[main_rank_name]
            if has_roa:
                required /= 2  # 50% quota for ROA
            passed = total_hours >= required
            symbol = "<:ROA:1394778057822441542>" if passed and has_roa else ("✅" if passed else "❌")
            h = int(total_hours)
            m = int(round((total_hours - h) * 60))
            time_str = f"{h}h {m}m"
        else:
            symbol = "❌"
            h = int(total_hours)
            m = int(round((total_hours - h) * 60))
            time_str = f"{h}h {m}m"

        message += f"- {member.mention} ({main_rank_name}): {time_str} {symbol}\n"
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

    member_role_ids = {role.id for role in interaction.user.roles}
    allowed_roles = set(RANK_ORDER[:6])  # Captain+
    if not member_role_ids.intersection(allowed_roles):
        await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)
        return

    c.execute("DELETE FROM shifts")
    conn.commit()

    await interaction.followup.send("✅ All quota logs have been cleared.", ephemeral=True)

bot.run(TOKEN)
