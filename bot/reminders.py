# bot/reminders.py — Automated booking reminders for Salon Bot v3

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def send_reminders(bot):
    """
    Called every 15 minutes by APScheduler.
    Sends 24-hour and 1-hour reminders to clients.
    """
    from database.schema import get_db, get_setting

    salon = get_setting("salon_name", "Shringar Studio")
    cur   = get_setting("currency", "₹")
    now   = datetime.now()

    with get_db() as db:
        upcoming = db.execute("""
            SELECT * FROM bookings
            WHERE status = 'confirmed'
              AND reminder_sent < 2
              AND date >= date('now')
        """).fetchall()

    for b in upcoming:
        try:
            slot_dt = datetime.strptime(f"{b['date']} {b['slot']}", "%Y-%m-%d %H:%M")
            diff    = slot_dt - now
            hours   = diff.total_seconds() / 3600
            sent    = b["reminder_sent"]
            tid     = b["telegram_id"]

            if not tid or tid == 0:
                continue

            # 24-hour reminder
            if sent < 1 and 23 <= hours <= 25:
                text = (
                    f"🔔 *Reminder — {salon}*\n\n"
                    f"Your appointment is *tomorrow*!\n\n"
                    f"🪄 {b['service']}\n"
                    f"👩‍🎨 {b['staff']}\n"
                    f"📅 {b['date']}  ⏰ {b['slot']}\n\n"
                    f"🔖 `{b['id']}`\n"
                    f"_To cancel: /cancel {b['id']}_"
                )
                await bot.send_message(chat_id=tid, text=text, parse_mode="Markdown")
                with get_db() as db:
                    db.execute("UPDATE bookings SET reminder_sent=1 WHERE id=?", (b["id"],))
                logger.info(f"[REMINDER] 24h sent to {tid} for {b['id']}")

            # 1-hour reminder
            elif sent < 2 and 0.75 <= hours <= 1.25:
                text = (
                    f"⏰ *In 1 hour — {salon}*\n\n"
                    f"Your appointment is almost here!\n\n"
                    f"🪄 {b['service']}\n"
                    f"👩‍🎨 {b['staff']}  ⏰ {b['slot']}\n\n"
                    f"📍 {get_setting('salon_address', 'Salon Address')}\n"
                    f"📞 {get_setting('salon_phone', '')}\n\n"
                    f"_See you soon! 🌸_"
                )
                await bot.send_message(chat_id=tid, text=text, parse_mode="Markdown")
                with get_db() as db:
                    db.execute("UPDATE bookings SET reminder_sent=2 WHERE id=?", (b["id"],))
                logger.info(f"[REMINDER] 1h sent to {tid} for {b['id']}")

        except Exception as e:
            logger.warning(f"[REMINDER] Failed for {b['id']}: {e}")
