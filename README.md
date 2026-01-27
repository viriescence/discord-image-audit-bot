# Discord Image Audit Bot

A Discord bot that detects **near-duplicate images** using **perceptual hashing**
(dHash + pHash) and logs results to a dedicated **audit channel** (e.g. `#audit`)
instead of spamming the channel where the image was posted. Owner(s) or admin(s) can take action based on these reports.

---

## 🚀 Features (Current)

- Watches for new **image attachments** posted in a server
- Computes perceptual hashes (**dHash + pHash**) for each image
- Compares new images against previously seen images
- Stores image metadata and hashes in a **SQLite database**
- Detects **near-duplicate images** using a configurable similarity threshold
- Sends alerts to a dedicated **audit channel**
- **Batches alerts** when multiple images are posted in a single message  
  → sends **one audit message per user message** (prevents spam & rate-limits)

---

## 🧠 How It Works (High Level)

1. Detect image attachments in messages
2. Download image bytes
3. Compute perceptual hashes (dHash + pHash)
4. Compare against recent images stored in SQLite
5. Store the new image (always, for future comparisons)
6. If duplicates are found:
   - Collect all matches for the message
   - Send **one consolidated audit alert**

---

## 🚦 Alert Batching (Important)

If a user uploads **multiple images in a single message**, the bot:

- Processes each image individually
- Logs every image to the database
- Sends **one audit message summarizing all duplicates**

This prevents:
- Audit-channel spam
- Discord rate-limit violations
- Account verification / temporary lockouts during testing

---

## 🧰 Tech Stack

- **Python**
- **discord.py**
- **Pillow** + **imagehash**
- **SQLite** (`aiosqlite`)
- **aiohttp** (download attachments)
- **python-dotenv** (local environment variables)

---

## ⚙️ Configuration

Create a `.env` file (never commit this, obviously.):

```env
DISCORD_TOKEN=your_bot_token_here
AUDIT_CHANNEL_NAME=audit
SIMILARITY_THRESHOLD=8
DB_PATH=output/audit.sqlite