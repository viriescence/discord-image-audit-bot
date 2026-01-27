import os
from pathlib import Path
import discord
from dotenv import load_dotenv

# Load .env from project root (one level above /src)
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv (env_path)

TOKEN = os.getenv ("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError ("DISCORD_TOKEN not found in .env")

AUDIT_CHANNEL_NAME = os.getenv ("AUDIT_CHANNEL_NAME", "audit")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client (intents=intents)

@client.event
async def on_ready():
    print (f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.attachments:
        audit_channel = discord.utils.get (
            message.guild.text_channels,
            name=AUDIT_CHANNEL_NAME
        )

        if audit_channel:
            await audit_channel.send(
                f"📸 Image detected from **{message.author}** "
                f"in **#{message.channel}**"
            )

client.run(TOKEN)