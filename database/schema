# database/schema.py — SQLite schema + helpers for Salon Bot v3

import sqlite3
import logging
from contextlib import contextmanager
from config import DB_PATH
import os

logger = logging.getLogger(__name__)


@contextmanager
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables and seed default data."""
    with get_db() as db:

        # ── clients ───────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                name        TEXT NOT NULL,
                phone       TEXT,
                visit_count INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                last_seen   TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── services ──────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                duration    INTEGER NOT NULL DEFAULT 30,
                price       INTEGER NOT NULL DEFAULT 0,
                active      INTEGER DEFAULT 1
            )
        """)

        # ── staff ─────────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                active      INTEGER DEFAULT 1
            )
        """)

        # ── bookings ──────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id              TEXT PRIMARY KEY,
                telegram_id     INTEGER,
                client_name     TEXT NOT NULL,
                phone           TEXT,
                service         TEXT NOT NULL,
                staff           TEXT NOT NULL,
                date            TEXT NOT NULL,
                slot            TEXT NOT NULL,
                duration        INTEGER DEFAULT 30,
                total_price     INTEGER DEFAULT 0,
                advance_amount  INTEGER DEFAULT 0,
                payment_status  TEXT DEFAULT 'pending',
                payment_id      TEXT,
                conflict_flag   INTEGER DEFAULT 0,
                status          TEXT DEFAULT 'confirmed',
                reminder_sent   INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── payments ──────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id              TEXT PRIMARY KEY,
                booking_id      TEXT REFERENCES bookings(id),
                razorpay_id     TEXT,
                amount          INTEGER NOT NULL,
                status          TEXT DEFAULT 'created',
                method          TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── settings ──────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            )
        """)

        # ── Seed default services ─────────────────────────────────────
        default_services = [
            ("Haircut",   30, 200),
            ("Beard Trim", 20, 100),
            ("Facial",    60, 500),
            ("Hair Spa",  90, 700),
        ]
        for name, dur, price in default_services:
            db.execute(
                "INSERT OR IGNORE INTO services (name, duration, price) VALUES (?, ?, ?)",
                (name, dur, price)
            )

        # ── Seed default staff ────────────────────────────────────────
        for name in ["Priya", "Rahul", "Neha"]:
            db.execute("INSERT OR IGNORE INTO staff (name) VALUES (?)", (name,))

        # ── Default settings ──────────────────────────────────────────
        defaults = {
            "salon_name":    "Shringar Beauty Studio",
            "salon_address": "Connaught Place, New Delhi",
            "salon_phone":   "+91 98765 43210",
            "open_time":     "09:00",
            "close_time":    "20:00",
            "slot_interval": "30",
            "currency":      "₹",
            "working_days":  "1,2,3,4,5,6",
        }
        for k, v in defaults.items():
            db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    logger.info(f"[DB] Initialized: {DB_PATH}")


# ── Helper functions ──────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))

def get_services() -> list:
    with get_db() as db:
        return db.execute("SELECT * FROM services WHERE active=1 ORDER BY id").fetchall()

def get_staff() -> list:
    with get_db() as db:
        return db.execute("SELECT * FROM staff WHERE active=1 ORDER BY id").fetchall()

def get_booked_slots(date: str, staff_name: str = None) -> list:
    with get_db() as db:
        if staff_name and staff_name != "Any Available":
            rows = db.execute(
                "SELECT slot, duration FROM bookings WHERE date=? AND staff=? AND status!='cancelled'",
                (date, staff_name)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT slot, duration FROM bookings WHERE date=? AND status!='cancelled'",
                (date,)
            ).fetchall()
        return [(r["slot"], r["duration"]) for r in rows]

def check_conflict(date: str, slot: str, staff_name: str) -> bool:
    """Returns True if this slot is already booked for this staff."""
    booked = get_booked_slots(date, staff_name)
    return any(s == slot for s, _ in booked)

def save_booking(data: dict) -> str:
    import uuid
    ref = "SHR-" + uuid.uuid4().hex[:6].upper()
    conflict = check_conflict(data["date"], data["slot"], data["staff"])

    with get_db() as db:
        db.execute("""
            INSERT INTO bookings
              (id, telegram_id, client_name, phone, service, staff, date, slot,
               duration, total_price, advance_amount, payment_status, conflict_flag)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ref, data.get("telegram_id"), data["client_name"], data.get("phone"),
            data["service"], data["staff"], data["date"], data["slot"],
            data.get("duration", 30), data.get("total_price", 0),
            data.get("advance_amount", 0), data.get("payment_status", "pending"),
            1 if conflict else 0,
        ))
        # Upsert client
        db.execute("""
            INSERT INTO clients (telegram_id, name, phone, visit_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
              name=excluded.name, phone=excluded.phone,
              visit_count=visit_count+1, last_seen=datetime('now')
        """, (data.get("telegram_id"), data["client_name"], data.get("phone")))

    return ref, conflict

def get_todays_bookings() -> list:
    from datetime import date
    today = date.today().isoformat()
    with get_db() as db:
        return db.execute(
            "SELECT * FROM bookings WHERE date=? AND status!='cancelled' ORDER BY slot",
            (today,)
        ).fetchall()

def get_recent_clients(limit=10) -> list:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM clients ORDER BY last_seen DESC LIMIT ?", (limit,)
        ).fetchall()

def get_revenue_today() -> dict:
    from datetime import date
    today = date.today().isoformat()
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) as count, COALESCE(SUM(advance_amount),0) as revenue "
            "FROM bookings WHERE date=? AND status!='cancelled'", (today,)
        ).fetchone()
    return {"count": row["count"], "revenue": row["revenue"]}

def update_payment(booking_id: str, payment_id: str, status: str):
    with get_db() as db:
        db.execute(
            "UPDATE bookings SET payment_id=?, payment_status=? WHERE id=?",
            (payment_id, status, booking_id)
        )
        db.execute(
            "UPDATE payments SET razorpay_id=?, status=?, updated_at=datetime('now') WHERE booking_id=?",
            (payment_id, status, booking_id)
        )
