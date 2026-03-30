# bot/bot.py — Telegram Bot for Salon Bot v3
#
# Run: python -m bot.bot  (from salon-v3/ folder)

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)

from config import BOT_TOKEN, ADMIN_CHAT_ID, MINI_APP_URL
from database.schema import (
    init_db, get_todays_bookings, get_recent_clients,
    get_revenue_today, get_setting, set_setting,
    get_services, get_staff,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────

def is_admin(uid: int) -> bool:
    return uid == ADMIN_CHAT_ID

def book_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✦  Book Appointment", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin only.")
            return
        await func(update, context)
    return wrapper


# ══════════════════════════════════════════════════════════════════════
# CLIENT COMMANDS
# ══════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salon = get_setting("salon_name", "Shringar Studio")
    user  = update.effective_user
    await update.message.reply_text(
        f"🌸 *Namaste {user.first_name}!*\n\n"
        f"Welcome to *{salon}*\n\n"
        f"Book your beauty appointment instantly — "
        f"choose your service, pick a time, and pay in advance.\n\n"
        f"_Tap below to get started 👇_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✦  Book Appointment", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton("📋 My Bookings", callback_data="my_bookings"),
             InlineKeyboardButton("ℹ️ About",        callback_data="about")],
        ])
    )


async def book_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✦ *Book your appointment*\n\nTap below to open the booking app.",
        parse_mode="Markdown",
        reply_markup=book_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✦ *Commands*\n\n"
        "/start — Welcome screen\n"
        "/book — Open booking app\n"
        "/mybookings — Your appointments\n"
        "/cancel ID — Cancel a booking\n"
        "/help — This message",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════

@admin_only
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salon = get_setting("salon_name", "Salon")
    r     = get_revenue_today()
    cur   = get_setting("currency", "₹")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Today's Schedule",  callback_data="admin_today"),
         InlineKeyboardButton("💰 Revenue Today",     callback_data="admin_revenue")],
        [InlineKeyboardButton("👥 Recent Clients",    callback_data="admin_clients"),
         InlineKeyboardButton("📤 Export Report",     callback_data="admin_export")],
        [InlineKeyboardButton("⚙️ Settings",          callback_data="admin_settings")],
    ])
    await update.message.reply_text(
        f"⚙️ *Admin Panel — {salon}*\n\n"
        f"📅 Today: *{r['count']} bookings*\n"
        f"💰 Revenue: *{cur}{r['revenue']:,}*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@admin_only
async def bookings_today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_today(update.message)


@admin_only
async def revenue_today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_revenue(update.message)


@admin_only
async def clients_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_clients(update.message)


@admin_only
async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_export(update.message, context)


@admin_only
async def setname_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = " ".join(context.args)
    if not val:
        await update.message.reply_text("Usage: /setname My Salon Name")
        return
    set_setting("salon_name", val)
    await update.message.reply_text(f"✅ Salon name: *{val}*", parse_mode="Markdown")


@admin_only
async def sethours_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /sethours 09:00 20:00")
        return
    set_setting("open_time",  context.args[0])
    set_setting("close_time", context.args[1])
    await update.message.reply_text(
        f"✅ Hours: *{context.args[0]}* – *{context.args[1]}*", parse_mode="Markdown"
    )


@admin_only
async def addservice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw   = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await update.message.reply_text("Usage: /addservice Haircut|30|200")
        return
    name, dur, price = parts
    from database.schema import get_db
    with get_db() as db:
        db.execute("INSERT INTO services (name, duration, price) VALUES (?,?,?)",
                   (name, int(dur), int(price)))
    await update.message.reply_text(f"✅ Service added: *{name}*", parse_mode="Markdown")


@admin_only
async def addstaff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Usage: /addstaff Priya")
        return
    from database.schema import get_db
    with get_db() as db:
        db.execute("INSERT INTO staff (name) VALUES (?)", (name,))
    await update.message.reply_text(f"✅ Staff added: *{name}*", parse_mode="Markdown")


@admin_only
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salon = get_setting("salon_name")
    r     = get_revenue_today()
    cur   = get_setting("currency", "₹")
    from database.schema import get_db
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as c FROM bookings").fetchone()["c"]
        clients = db.execute("SELECT COUNT(*) as c FROM clients").fetchone()["c"]

    await update.message.reply_text(
        f"🔧 *Bot Status — v3.0*\n\n"
        f"✅ Bot running\n"
        f"🏪 *{salon}*\n\n"
        f"📅 Today: {r['count']} bookings\n"
        f"💰 Today revenue: {cur}{r['revenue']:,}\n"
        f"📋 Total bookings: {total}\n"
        f"👥 Total clients: {clients}\n\n"
        f"_Mini App: {MINI_APP_URL}_",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════
# CALLBACK QUERIES
# ══════════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    await q.answer()

    if data == "admin_today":
        await _show_today(q.message, edit=True)
    elif data == "admin_revenue":
        await _show_revenue(q.message, edit=True)
    elif data == "admin_clients":
        await _show_clients(q.message, edit=True)
    elif data == "admin_export":
        await _send_export(q.message, context)
    elif data == "admin_settings":
        await _show_settings(q.message, edit=True)
    elif data == "my_bookings":
        await _show_my_bookings(update, context)
    elif data == "about":
        await _show_about(q.message, edit=True)


# ══════════════════════════════════════════════════════════════════════
# INNER HELPERS
# ══════════════════════════════════════════════════════════════════════

async def _show_today(msg, edit=False):
    bookings = get_todays_bookings()
    cur = get_setting("currency", "₹")
    from datetime import date
    today = date.today().strftime("%A, %d %B %Y")

    if not bookings:
        text = f"📅 *{today}*\n\nNo appointments today. 🎉"
    else:
        total = sum(b["advance_amount"] for b in bookings if b["payment_status"] == "paid")
        lines = [f"📅 *Today — {today}*\n_{len(bookings)} appointments_\n"]
        for b in bookings:
            conflict = " ⚠️" if b["conflict_flag"] else ""
            paid     = "✅" if b["payment_status"] == "paid" else "⏳"
            lines.append(
                f"{paid} *{b['slot']}* — {b['service']}{conflict}\n"
                f"   👤 {b['client_name']}  📞 {b['phone'] or '—'}\n"
                f"   👩‍🎨 {b['staff']}  💰 {cur}{b['total_price']}"
            )
        lines.append(f"\n💳 *Advance collected: {cur}{total:,}*")
        text = "\n\n".join(lines)

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_back")]])
    if edit:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=back_kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=back_kb)


async def _show_revenue(msg, edit=False):
    r   = get_revenue_today()
    cur = get_setting("currency", "₹")
    from database.schema import get_db
    with get_db() as db:
        week   = db.execute("SELECT COALESCE(SUM(advance_amount),0) as r FROM bookings WHERE date >= date('now','-7 days') AND payment_status='paid'").fetchone()["r"]
        month  = db.execute("SELECT COALESCE(SUM(advance_amount),0) as r FROM bookings WHERE date >= date('now','start of month') AND payment_status='paid'").fetchone()["r"]
        total  = db.execute("SELECT COALESCE(SUM(advance_amount),0) as r FROM bookings WHERE payment_status='paid'").fetchone()["r"]

    text = (
        f"💰 *Revenue Report*\n\n"
        f"*Today:*   {cur}{r['revenue']:,} ({r['count']} bookings)\n"
        f"*This Week:*  {cur}{week:,}\n"
        f"*This Month:* {cur}{month:,}\n"
        f"*All Time:*   {cur}{total:,}"
    )
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_back")]])
    if edit:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=back_kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=back_kb)


async def _show_clients(msg, edit=False):
    clients = get_recent_clients(10)
    if not clients:
        text = "No clients yet."
    else:
        lines = [f"👥 *Recent Clients ({len(clients)} shown)*\n"]
        for c in clients:
            uname = f" @{c['username']}" if c.get("username") else ""
            lines.append(
                f"👤 *{c['name']}*{uname}\n"
                f"   📞 {c['phone'] or '—'}  |  🗓 {c['visit_count']} visits"
            )
        text = "\n\n".join(lines)

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_back")]])
    if edit:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=back_kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=back_kb)


async def _send_export(msg, context):
    from reports.excel import generate_report
    await msg.reply_text("⏳ Generating report...")
    try:
        path = generate_report()
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                await context.bot.send_document(
                    chat_id=ADMIN_CHAT_ID,
                    document=f,
                    filename=os.path.basename(path),
                    caption="📊 Salon Booking Report",
                )
        else:
            await msg.reply_text("❌ Report generation failed. Check openpyxl is installed.")
    except Exception as e:
        logger.error(f"[EXPORT] {e}")
        await msg.reply_text(f"❌ Error: {e}")


async def _show_settings(msg, edit=False):
    from database.schema import get_setting
    text = (
        f"⚙️ *Current Settings*\n\n"
        f"🏪 Name: {get_setting('salon_name')}\n"
        f"📍 Address: {get_setting('salon_address')}\n"
        f"📞 Phone: {get_setting('salon_phone')}\n"
        f"🕐 Hours: {get_setting('open_time')} – {get_setting('close_time')}\n\n"
        f"*Commands to update:*\n"
        f"/setname Name\n"
        f"/sethours 09:00 20:00\n"
        f"/addservice Name|Duration|Price\n"
        f"/addstaff Name"
    )
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_back")]])
    if edit:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=back_kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown")


async def _show_my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    from database.schema import get_db
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM bookings WHERE telegram_id=? ORDER BY date DESC LIMIT 5", (uid,)
        ).fetchall()

    cur = get_setting("currency", "₹")
    if not rows:
        text = "You have no bookings yet.\n\nUse /book to reserve your appointment! ✦"
    else:
        lines = [f"✦ *Your Bookings*\n"]
        for b in rows:
            icon = "✅" if b["status"] == "confirmed" else "❌"
            paid = "💳 Paid" if b["payment_status"] == "paid" else "⏳ Pending"
            lines.append(
                f"{icon} `{b['id']}`\n"
                f"🪄 {b['service']}  |  📅 {b['date']}  ⏰ {b['slot']}\n"
                f"💰 {cur}{b['total_price']}  |  {paid}"
            )
        text = "\n\n".join(lines)

    await update.callback_query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✦ Book Again", web_app=WebAppInfo(url=MINI_APP_URL))
        ]])
    )


async def _show_about(msg, edit=False):
    text = (
        f"✦ *{get_setting('salon_name')}*\n\n"
        f"📍 {get_setting('salon_address')}\n"
        f"📞 {get_setting('salon_phone')}\n"
        f"🕐 {get_setting('open_time')} – {get_setting('close_time')}\n\n"
        f"_Powered by Salon Bot v3_ 🌸"
    )
    if edit:
        await msg.edit_text(text, parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("✦ Book Now", web_app=WebAppInfo(url=MINI_APP_URL))
                            ]]))
    else:
        await msg.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.error("❌ Set BOT_TOKEN in .env")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Client commands
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("book",       book_cmd))
    app.add_handler(CommandHandler("help",       help_cmd))

    # Admin commands
    app.add_handler(CommandHandler("admin",           admin_cmd))
    app.add_handler(CommandHandler("bookings_today",  bookings_today_cmd))
    app.add_handler(CommandHandler("revenue_today",   revenue_today_cmd))
    app.add_handler(CommandHandler("clients",         clients_cmd))
    app.add_handler(CommandHandler("export",          export_cmd))
    app.add_handler(CommandHandler("status",          status_cmd))
    app.add_handler(CommandHandler("setname",         setname_cmd))
    app.add_handler(CommandHandler("sethours",        sethours_cmd))
    app.add_handler(CommandHandler("addservice",      addservice_cmd))
    app.add_handler(CommandHandler("addstaff",        addstaff_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info(f"✦ Salon Bot v3 live | Admin: {ADMIN_CHAT_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
