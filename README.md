# Discord Image Audit Bot

A Discord bot that detects **near-duplicate images** using **perceptual hashing**
(dHash + pHash) and logs results to a dedicated audit channel (e.g., `#audit`)
instead of spamming the channel where the image was posted.

## Features (current)
- Watches for new image attachments posted in a server
- Computes perceptual hashes (dHash + pHash)
- Compares new images against previously seen images
- Logs results to an audit channel

## Tech Stack
- Python
- discord.py
- Pillow + imagehash
- SQLite (aiosqlite)
- aiohttp (download attachments)
- python-dotenv (local env vars)

## Setup
### 1) Create a virtual environment
**macOS/Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
