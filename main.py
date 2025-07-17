import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask
import threading
import datetime
import asyncio
import requests

intents = discord.Intents.default()
intents.message_content = True
tree = app_commands.CommandTree(discord.Client(intents=intents))
client = commands.Bot(command_prefix="/", intents=intents)

app = Flask('')

@app.route('/')
def home():
    return "Shift Logger is active."

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()

# Store shift logs here
shift_logs = {}

# Background task to ping the site
@tasks.loop(minutes=5)
async def ping_self():
    try:
        r = requests.get("https://shift-logger-bot.onrender.com")
        print(f"Self-ping response: {r.status_code} at {datetime.datetime.utcnow()}")
    except Exception as e:
        print("Ping failed:", e)

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is online as {client.user}")
    ping_self.start()
    print("🔁 Background task running...")

@tree.command(name="logshift", description="Log a patrol shift")
@app_commands.describe(
    minutes="How many minutes was your shift?",
    rating="Rate your shift from 1 to 5 (optional)",
    notes="Any notes about the shift (optional)"
)
async def logshift(interaction: discord.Interaction, minutes: int, rating: int = None, notes: str = None):
    user_id = interaction.user.id
    timestamp = datetime.datetime.utcnow()

    if user_id not in shift_logs:
        shift_logs[user_id] = []

    shift_entry = {
        "minutes": minutes,
        "timestamp": timestamp,
    }

    if rating:
        shift_entry["rating"] = rating
    if notes:
        shift_entry["notes"] = notes

    shift_logs[user_id].append(shift_entry)
    await interaction.response.send_message(f"✅ Logged {minutes} minutes for your shift.", ephemeral=True)

@tree.command(name="countquota", description="See how many minutes you've logged in the past 2 weeks")
async def count_quota(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.utcnow()
    two_weeks_ago = now - datetime.timedelta(days=14)

    if user_id not in shift_logs:
        await interaction.response.send_message("❌ You haven't logged any shifts yet.", ephemeral=True)
        return

    total_minutes = sum(entry["minutes"] for entry in shift_logs[user_id] if entry["timestamp"] >= two_weeks_ago)
    await interaction.response.send_message(f"⏱️ You've logged {total_minutes} minutes in the past 2 weeks.", ephemeral=True)

@tree.command(name="countallquota", description="View shift logs of everyone")
@app_commands.default_permissions(administrator=True)
async def count_all_quota(interaction: discord.Interaction):
    now = datetime.datetime.utcnow()
    two_weeks_ago = now - datetime.timedelta(days=14)

    if not shift_logs:
        await interaction.response.send_message("❌ No shifts have been logged yet.", ephemeral=True)
        return

    message = "📋 **2 Week Quota Summary:**\n"
    for user_id, logs in shift_logs.items():
        total_minutes = sum(entry["minutes"] for entry in logs if entry["timestamp"] >= two_weeks_ago)
        user = await client.fetch_user(user_id)
        message += f"- {user.name}: {total_minutes} minutes\n"

    await interaction.response.send_message(message, ephemeral=True)

keep_alive()
client.run(os.getenv("TOKEN"))
