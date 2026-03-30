# config.py — Salon Bot v3 Configuration
# Copy to .env and fill in your values

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN",      "YOUR_BOT_TOKEN")
ADMIN_CHAT_ID  = int(os.getenv("ADMIN_CHAT_ID", "0"))
MINI_APP_URL   = os.getenv("MINI_APP_URL",   "https://your-vercel-app.vercel.app")

# ── Backend ───────────────────────────────────────────────────────────
BACKEND_URL    = os.getenv("BACKEND_URL",    "http://localhost:8000")
SECRET_KEY     = os.getenv("SECRET_KEY",     "change-this-secret")

# ── Database ──────────────────────────────────────────────────────────
DB_PATH        = os.getenv("DB_PATH",        "database/salon.db")

# ── Google Sheets ─────────────────────────────────────────────────────
SHEET_ID       = os.getenv("SHEET_ID",       "YOUR_GOOGLE_SHEET_ID")
SHEET_NAME     = os.getenv("SHEET_NAME",     "Bookings")
GOOGLE_CREDS   = os.getenv("GOOGLE_CREDS",   "config/google_credentials.json")

# ── Razorpay ──────────────────────────────────────────────────────────
RAZORPAY_KEY   = os.getenv("RAZORPAY_KEY",   "rzp_test_YOUR_KEY")
RAZORPAY_SECRET= os.getenv("RAZORPAY_SECRET","YOUR_RAZORPAY_SECRET")
ADVANCE_AMOUNT = int(os.getenv("ADVANCE_AMOUNT", "100"))  # ₹100 advance

# ── Backup ────────────────────────────────────────────────────────────
BACKUP_DIR     = os.getenv("BACKUP_DIR",     "backups")
