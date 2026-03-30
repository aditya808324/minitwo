# backend/main.py — FastAPI server for Salon Bot v3
#
# Run: uvicorn backend.main:app --reload --port 8000

import hashlib
import hmac
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from urllib.parse import parse_qs, unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from config import BOT_TOKEN, ADMIN_CHAT_ID, ADVANCE_AMOUNT, SECRET_KEY
from database.schema import (
    init_db, get_services, get_staff, get_setting,
    save_booking, update_payment, get_todays_bookings,
    get_recent_clients, get_revenue_today,
)
from backend.slots import get_slots_for_date, is_slot_conflicted
from backend.sheets import append_booking, update_payment_in_sheet
from backend.payments import create_payment_order, verify_payment_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Salon Bot v3 API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init DB on startup
@app.on_event("startup")
async def startup():
    init_db()
    logger.info("[API] Server started — DB initialized")


# ══════════════════════════════════════════════════════════════════════
# TELEGRAM INIT DATA VERIFICATION
# ══════════════════════════════════════════════════════════════════════

def verify_telegram_init_data(init_data: str) -> dict | None:
    """
    Verify Telegram WebApp initData signature.
    Returns parsed user dict on success, None on failure.
    """
    try:
        parsed  = dict(parse_qs(unquote(init_data), keep_blank_values=True))
        flat    = {k: v[0] for k, v in parsed.items()}
        hash_   = flat.pop("hash", None)
        if not hash_:
            return None

        data_check = "\n".join(
            f"{k}={v}" for k, v in sorted(flat.items())
        )
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

        if hmac.compare_digest(expected, hash_):
            user_str = flat.get("user", "{}")
            return json.loads(user_str)
        return None
    except Exception as e:
        logger.warning(f"[AUTH] initData verification failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ══════════════════════════════════════════════════════════════════════

class BookingRequest(BaseModel):
    init_data:      str
    client_name:    str
    phone:          str
    service:        str
    staff:          str
    date:           str
    slot:           str
    duration:       int
    total_price:    int
    notes:          Optional[str] = ""

class PaymentVerifyRequest(BaseModel):
    booking_id:   str
    order_id:     str
    payment_id:   str
    signature:    str


# ══════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0"}


@app.get("/api/config")
async def get_config():
    """Return public salon config for Mini App."""
    return {
        "salon_name":    get_setting("salon_name"),
        "salon_address": get_setting("salon_address"),
        "salon_phone":   get_setting("salon_phone"),
        "open_time":     get_setting("open_time"),
        "close_time":    get_setting("close_time"),
        "currency":      get_setting("currency"),
        "advance_amount": ADVANCE_AMOUNT,
        "razorpay_key":  os.getenv("RAZORPAY_KEY", ""),
    }


@app.get("/api/services")
async def api_services():
    rows = get_services()
    return [{"id": r["id"], "name": r["name"], "duration": r["duration"], "price": r["price"]} for r in rows]


@app.get("/api/staff")
async def api_staff():
    rows = get_staff()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


@app.get("/api/slots")
async def api_slots(date: str, staff: str = "Any Available"):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")
    result = get_slots_for_date(date, staff)
    return result


# ══════════════════════════════════════════════════════════════════════
# BOOKING ENDPOINT
# ══════════════════════════════════════════════════════════════════════

@app.post("/api/book")
async def create_booking(req: BookingRequest):
    # ── 1. Verify Telegram user ──────────────────────────────────────
    user = verify_telegram_init_data(req.init_data)
    if not user:
        # Fallback: accept in dev/test mode
        user = {"id": 0, "first_name": req.client_name}
        logger.warning("[API] initData verification failed — using fallback")

    telegram_id = user.get("id", 0)

    # ── 2. Check conflict (warn, don't block) ─────────────────────────
    conflict = is_slot_conflicted(req.date, req.slot, req.staff)

    # ── 3. Save to SQLite ─────────────────────────────────────────────
    booking_data = {
        "telegram_id":    telegram_id,
        "client_name":    req.client_name,
        "phone":          req.phone,
        "service":        req.service,
        "staff":          req.staff,
        "date":           req.date,
        "slot":           req.slot,
        "duration":       req.duration,
        "total_price":    req.total_price,
        "advance_amount": ADVANCE_AMOUNT,
        "payment_status": "pending",
        "conflict_flag":  1 if conflict else 0,
        "notes":          req.notes,
    }
    ref, _ = save_booking(booking_data)
    booking_data["id"] = ref

    # ── 4. Create Razorpay order ──────────────────────────────────────
    order = create_payment_order(ref, ADVANCE_AMOUNT, req.client_name, req.phone)

    # ── 5. Append to Google Sheets (non-blocking) ─────────────────────
    try:
        append_booking(booking_data)
    except Exception as e:
        logger.warning(f"[API] Sheets append failed (non-fatal): {e}")

    # ── 6. Send admin Telegram alert ──────────────────────────────────
    try:
        await send_admin_alert(booking_data, conflict)
    except Exception as e:
        logger.warning(f"[API] Admin alert failed: {e}")

    logger.info(f"[API] ✅ Booking {ref} created | conflict={conflict}")

    return {
        "booking_id":  ref,
        "conflict":    conflict,
        "order_id":    order.get("id") if order else None,
        "amount":      ADVANCE_AMOUNT,
        "currency":    "INR",
        "razorpay_key": os.getenv("RAZORPAY_KEY", ""),
    }


# ══════════════════════════════════════════════════════════════════════
# PAYMENT WEBHOOK & VERIFICATION
# ══════════════════════════════════════════════════════════════════════

@app.post("/api/payment/verify")
async def verify_payment(req: PaymentVerifyRequest):
    """Called from Mini App after Razorpay payment success."""
    valid = verify_payment_signature(req.order_id, req.payment_id, req.signature)

    if valid:
        update_payment(req.booking_id, req.payment_id, "paid")
        update_payment_in_sheet(req.booking_id, req.payment_id, "paid")
        await send_payment_alert(req.booking_id, req.payment_id)
        logger.info(f"[PAYMENT] ✅ Verified: {req.booking_id}")
        return {"status": "success"}
    else:
        logger.warning(f"[PAYMENT] ❌ Invalid signature for {req.booking_id}")
        raise HTTPException(400, "Invalid payment signature")


@app.post("/api/payment/webhook")
async def razorpay_webhook(request: Request):
    """Razorpay server-side webhook — more reliable than client callback."""
    from backend.payments import verify_webhook_signature
    body      = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    if not verify_webhook_signature(body, signature):
        raise HTTPException(400, "Invalid webhook signature")

    event = json.loads(body)
    if event.get("event") == "payment.captured":
        payment = event["payload"]["payment"]["entity"]
        booking_id = payment.get("receipt", "")
        payment_id = payment.get("id", "")
        update_payment(booking_id, payment_id, "paid")
        update_payment_in_sheet(booking_id, payment_id, "paid")
        await send_payment_alert(booking_id, payment_id)
        logger.info(f"[WEBHOOK] Payment captured: {booking_id}")

    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════
# TELEGRAM ALERT HELPERS
# ══════════════════════════════════════════════════════════════════════

async def send_admin_alert(booking: dict, conflict: bool):
    """Send booking notification to admin via Telegram Bot API."""
    import httpx
    salon = get_setting("salon_name", "Salon")
    cur   = get_setting("currency", "₹")

    conflict_banner = "\n⚠️ *DOUBLE BOOKING ALERT* — This slot was already booked!\n" if conflict else ""

    text = (
        f"🔔 *New Booking — {salon}*{conflict_banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *Client:*   {booking['client_name']}\n"
        f"📞 *Phone:*    `{booking.get('phone', '—')}`\n\n"
        f"🪄 *Service:*  {booking['service']}\n"
        f"👩‍🎨 *Staff:*    {booking['staff']}\n"
        f"📅 *Date:*     {booking['date']}\n"
        f"⏰ *Slot:*     {booking['slot']}\n"
        f"💰 *Total:*    {cur}{booking.get('total_price', 0)}\n"
        f"💳 *Advance:*  {cur}{booking.get('advance_amount', 0)} (pending)\n\n"
        f"🔖 *ID:* `{booking['id']}`"
    )
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )


async def send_payment_alert(booking_id: str, payment_id: str):
    """Notify admin when payment is confirmed."""
    import httpx
    text = (
        f"✅ *Payment Confirmed*\n\n"
        f"🔖 Booking: `{booking_id}`\n"
        f"💳 Payment: `{payment_id}`\n\n"
        f"_Advance received successfully._"
    )
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
