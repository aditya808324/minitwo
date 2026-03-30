# backend/sheets.py — Google Sheets integration for Salon Bot v3
#
# Setup:
#   1. Go to console.cloud.google.com → New Project
#   2. Enable Google Sheets API
#   3. Create Service Account → download JSON key → save as config/google_credentials.json
#   4. Share your Google Sheet with the service account email (editor access)
#   5. Copy the Sheet ID from the URL and set SHEET_ID in .env

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("[SHEETS] gspread not installed — run: pip install gspread google-auth")


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column headers — must match append_booking() order
HEADERS = [
    "Timestamp", "Booking ID", "Client Name", "Phone",
    "Service", "Staff", "Date", "Slot",
    "Duration (min)", "Total Price", "Advance Paid",
    "Payment Status", "Payment ID", "Conflict Flag", "Status"
]


def _get_client():
    """Authenticate and return gspread client."""
    from config import GOOGLE_CREDS
    creds = Credentials.from_service_account_file(GOOGLE_CREDS, scopes=SCOPES)
    return gspread.authorize(creds)


def ensure_headers(sheet):
    """Add header row if sheet is empty."""
    try:
        if not sheet.row_values(1):
            sheet.append_row(HEADERS, value_input_option="USER_ENTERED")
            logger.info("[SHEETS] Headers added")
    except Exception as e:
        logger.warning(f"[SHEETS] Could not check headers: {e}")


def append_booking(booking: dict) -> bool:
    """
    Append a booking row to Google Sheets.
    Returns True on success, False on failure.
    Failure is graceful — booking is already saved in SQLite.
    """
    if not GSPREAD_AVAILABLE:
        logger.warning("[SHEETS] gspread not available — skipping sheet append")
        return False

    from config import SHEET_ID, SHEET_NAME
    try:
        client = _get_client()
        sh     = client.open_by_key(SHEET_ID)
        sheet  = sh.worksheet(SHEET_NAME)
        ensure_headers(sheet)

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            booking.get("id", ""),
            booking.get("client_name", ""),
            booking.get("phone", ""),
            booking.get("service", ""),
            booking.get("staff", ""),
            booking.get("date", ""),
            booking.get("slot", ""),
            booking.get("duration", ""),
            f"₹{booking.get('total_price', 0)}",
            f"₹{booking.get('advance_amount', 0)}",
            booking.get("payment_status", "pending"),
            booking.get("payment_id", ""),
            "⚠️ CONFLICT" if booking.get("conflict_flag") else "OK",
            booking.get("status", "confirmed"),
        ]

        sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"[SHEETS] ✅ Booking {booking.get('id')} appended")
        return True

    except Exception as e:
        logger.error(f"[SHEETS] ❌ Failed to append booking: {e}")
        return False


def update_payment_in_sheet(booking_id: str, payment_id: str, status: str) -> bool:
    """Find booking row by ID and update payment columns."""
    if not GSPREAD_AVAILABLE:
        return False

    from config import SHEET_ID, SHEET_NAME
    try:
        client = _get_client()
        sh     = client.open_by_key(SHEET_ID)
        sheet  = sh.worksheet(SHEET_NAME)

        # Find the row with this booking ID (column B = index 2)
        cell = sheet.find(booking_id, in_column=2)
        if cell:
            sheet.update_cell(cell.row, 12, status)      # Payment Status col
            sheet.update_cell(cell.row, 13, payment_id)  # Payment ID col
            logger.info(f"[SHEETS] ✅ Payment updated for {booking_id}")
            return True
        else:
            logger.warning(f"[SHEETS] Booking {booking_id} not found in sheet")
            return False

    except Exception as e:
        logger.error(f"[SHEETS] ❌ Payment update failed: {e}")
        return False
