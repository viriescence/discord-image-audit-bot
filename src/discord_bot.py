import os
import io
import asyncio
from datetime import datetime, timezone

import discord
import aiohttp
import aiosqlite
from PIL import Image
import imagehash
from dotenv import load_dotenv

from collections import defaultdict
import asyncio
import time

# -----------------------
# Config
# -----------------------
load_dotenv()

TOKEN = os.getenv ("DISCORD_TOKEN")
AUDIT_CHANNEL_NAME = os.getenv ("AUDIT_CHANNEL_NAME", "audit")
DB_PATH = os.getenv ("DB_PATH", "output/audit.sqlite")
SIMILARITY_THRESHOLD = int (os.getenv("SIMILARITY_THRESHOLD", "8"))  # lower = stricter

if not TOKEN:
    raise RuntimeError ("DISCORD_TOKEN not found in .env")

# ------------------
# Audit throttle helper
# ------------------
import time
import asyncio

AUDIT_COOLDOWN_SECONDS = float (os.getenv("AUDIT_COOLDOWN_SECONDS", "1.0"))
_last_audit_sent_at = 0.0

async def send_audit_throttled (channel, content: str):
    global _last_audit_sent_at
    now = time.time()
    wait = (_last_audit_sent_at + AUDIT_COOLDOWN_SECONDS) - now
    if wait > 0:
        await asyncio.sleep (wait)
    await channel.send (content)
    _last_audit_sent_at = time.time()



# -----------------------
# DB helpers
# -----------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    attachment_url TEXT NOT NULL,
    filename TEXT NOT NULL,
    phash TEXT NOT NULL,
    dhash TEXT NOT NULL
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_images_guild_time ON images (guild_id, created_at);
"""


async def init_db():
    os.makedirs (os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute (CREATE_TABLE_SQL)
        await db.execute (CREATE_INDEX_SQL)
        await db.commit()


async def insert_image_record (
    guild_id: int,
    channel_id: int,
    message_id: int,
    author_id: int,
    author_name: str,
    attachment_url: str,
    filename: str,
    phash_hex: str,
    dhash_hex: str,
):
    now = datetime.now (timezone.utc).isoformat()
    async with aiosqlite.connect (DB_PATH) as db:
        await db.execute (
            """
            INSERT INTO images
            (created_at, guild_id, channel_id, message_id, author_id, author_name,
             attachment_url, filename, phash, dhash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                guild_id,
                channel_id,
                message_id,
                author_id,
                author_name,
                attachment_url,
                filename,
                phash_hex,
                dhash_hex,
            ),
        )
        await db.commit()


async def fetch_recent_hashes (guild_id: int, limit: int = 2000):
    # For MVP: compare against the most recent N images in this guild
    async with aiosqlite.connect (DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute (
            """
            SELECT created_at, channel_id, message_id, author_name, attachment_url, filename, phash, dhash
            FROM images
            WHERE guild_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cur.fetchall()
        return rows


# -----------------------
# Image helpers
# -----------------------
def is_image_attachment (att: discord.Attachment) -> bool:
    # Discord often provides content_type like "image/png"
    if att.content_type and att.content_type.startswith("image/"):
        return True
    # Fallback: extension check
    name = (att.filename or "").lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


async def download_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


def compute_hashes (image_bytes: bytes) -> tuple[str, str]:
    # Convert to a consistent format for hashing
    with Image.open (io.BytesIO(image_bytes)) as img:
        img = img.convert ("RGB")
        ph = imagehash.phash (img, hash_size=8)  # 64-bit
        dh = imagehash.dhash (img, hash_size=8)  # 64-bit
        return str(ph), str(dh)  # hex strings


def hash_distance (a_hex: str, b_hex: str) -> int:
    # Convert back to hash objects and compute Hamming distance
    a = imagehash.hex_to_hash(a_hex)
    b = imagehash.hex_to_hash(b_hex)
    return a - b


# -----------------------
# Discord bot
# -----------------------
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client (intents=intents)


@client.event
async def on_ready():
    await init_db()
    print (f"✅ Logged in as {client.user} | DB={DB_PATH} | threshold={SIMILARITY_THRESHOLD}")


@client.event
async def on_message (message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return  # ignore DMs for now
    if not message.attachments:
        return

    audit_channel = discord.utils.get (
        message.guild.text_channels,
        name=AUDIT_CHANNEL_NAME,
    )

    alerts = []
    seen_in_message = {}  # (phash, dhash) -> count


    # Process each image attachment
    for att in message.attachments:
        if not is_image_attachment (att):
            continue

        try:
            img_bytes = await download_bytes (att.url)
            new_phash, new_dhash = compute_hashes (img_bytes)

            # Compare against recent hashes
            rows = await fetch_recent_hashes (message.guild.id, limit=2000)

            best_match = None
            best_score = 999

            for r in rows:
                ph_dist = hash_distance (new_phash, r["phash"])
                dh_dist = hash_distance (new_dhash, r["dhash"])
                score = min (ph_dist, dh_dist)  # conservative "closest" metric

                if score < best_score:
                    best_score = score
                    best_match = r

            # Store the new image no matter what (so future compares work)
            await insert_image_record (
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                message_id=message.id,
                author_id=message.author.id,
                author_name=str(message.author),
                attachment_url=att.url,
                filename=att.filename or "unknown",
                phash_hex=new_phash,
                dhash_hex=new_dhash,
            )

            # Alert if similar (collect; send once after loop)
            if best_match and best_score <= SIMILARITY_THRESHOLD:
                alerts.append ({
                    "filename": att.filename or "unknown",
                    "url": att.url,
                    "score": best_score,
                    "best": best_match,
                })
                                      
            
        except Exception as e:
            if audit_channel:
                await send_audit_throttled (
                    audit_channel,
                    f"❌ Error processing `{att.filename}`: {type(e).__name__}: {e}"
)

            else:
                print(f"Error processing {att.filename}: {e}")

            # ✅ SEND ONCE, after loop ends
            if alerts and audit_channel:
                lines = ["⚠️ **Possible near-duplicate images detected**"]
                lines.append (f"Posted by {message.author.mention} in {message.channel.mention}")

                for a in alerts:
                    lines.extend ([
                        "",
                        f"**File:** {a['filename']}",
                        f"**Match score:** {a['score']} (≤ {SIMILARITY_THRESHOLD} = similar)",
                        f"**New image:** {a['url']}",
                        f"**Closest previous:** {a['best']['filename']} by **{a['best']['author_name']}**",
                        f"**Previous image:** {a['best']['attachment_url']}",
                    ])

                await send_audit_throttled (audit_channel, "\n".join(lines))

client.run (TOKEN)
