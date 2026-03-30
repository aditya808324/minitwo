# backend/payments.py — Razorpay integration for Salon Bot v3
#
# Setup:
#   1. Create account at razorpay.com
#   2. Dashboard → Settings → API Keys → Generate Test Key
#   3. Copy Key ID and Key Secret into .env
#   4. For production: verify webhook signature

import hashlib
import hmac
import logging
import uuid

logger = logging.getLogger(__name__)

try:
    import razorpay
    RAZORPAY_AVAILABLE = True
except ImportError:
    RAZORPAY_AVAILABLE = False
    logger.warning("[PAYMENTS] razorpay not installed — run: pip install razorpay")


def get_razorpay_client():
    from config import RAZORPAY_KEY, RAZORPAY_SECRET
    if not RAZORPAY_AVAILABLE:
        return None
    return razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))


def create_payment_order(booking_id: str, amount_inr: int, client_name: str, phone: str) -> dict:
    """
    Create a Razorpay order for advance payment.
    Returns order dict with id, amount, currency.
    Amount in paise (multiply by 100).
    """
    client = get_razorpay_client()
    if not client:
        # Return mock order for testing without Razorpay
        return {
            "id":       f"order_mock_{uuid.uuid4().hex[:8]}",
            "amount":   amount_inr * 100,
            "currency": "INR",
            "mock":     True,
        }

    try:
        order = client.order.create({
            "amount":          amount_inr * 100,  # paise
            "currency":        "INR",
            "receipt":         booking_id,
            "notes": {
                "booking_id":  booking_id,
                "client_name": client_name,
                "phone":       phone,
            },
            "payment_capture": 1,
        })
        logger.info(f"[PAYMENTS] Order created: {order['id']} for {booking_id}")
        return order
    except Exception as e:
        logger.error(f"[PAYMENTS] Order creation failed: {e}")
        return None


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature."""
    from config import RAZORPAY_SECRET
    try:
        expected = hmac.new(
            RAZORPAY_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"[PAYMENTS] Signature verification failed: {e}")
        return False


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature from client-side callback."""
    from config import RAZORPAY_SECRET
    try:
        msg = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(
            RAZORPAY_SECRET.encode(), msg, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"[PAYMENTS] Payment signature failed: {e}")
        return False


def create_upi_link(amount_inr: int, booking_id: str, upi_id: str = "salon@upi") -> str:
    """
    Generate a UPI deep link as fallback payment option.
    Works without Razorpay account.
    """
    from config import get_setting
    name = "Shringar+Studio"
    return (
        f"upi://pay?pa={upi_id}&pn={name}"
        f"&am={amount_inr}&cu=INR"
        f"&tn=Advance+for+{booking_id}"
    )
