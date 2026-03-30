# backend/slots.py — Slot engine for Salon Bot v3

from datetime import datetime, timedelta, date as date_type
from database.schema import get_setting, get_booked_slots


def generate_all_slots(open_time: str, close_time: str, interval_mins: int) -> list[str]:
    """Generate all possible time slots between open and close."""
    slots = []
    fmt   = "%H:%M"
    cur   = datetime.strptime(open_time, fmt)
    end   = datetime.strptime(close_time, fmt)
    while cur < end:
        slots.append(cur.strftime(fmt))
        cur += timedelta(minutes=interval_mins)
    return slots


def get_slots_for_date(date_str: str, staff_name: str = None) -> dict:
    """
    Returns available and booked slots for a date+staff combination.
    Structure: { "available": [...], "booked": [...], "all": [...] }
    """
    open_t    = get_setting("open_time",     "09:00")
    close_t   = get_setting("close_time",    "20:00")
    interval  = int(get_setting("slot_interval", "30"))
    working   = [int(d) for d in get_setting("working_days", "1,2,3,4,5,6").split(",")]

    # Check if working day
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    if date_obj.weekday() not in working:
        return {"available": [], "booked": [], "all": [], "closed": True}

    all_slots   = generate_all_slots(open_t, close_t, interval)
    booked_data = get_booked_slots(date_str, staff_name)
    booked_set  = {slot for slot, _ in booked_data}

    # Block past slots for today
    now = datetime.now()
    if date_str == now.strftime("%Y-%m-%d"):
        all_slots = [
            s for s in all_slots
            if datetime.strptime(s, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            ) > now + timedelta(minutes=30)
        ]

    available = [s for s in all_slots if s not in booked_set]
    booked    = [s for s in all_slots if s in booked_set]

    return {
        "available": available,
        "booked":    booked,
        "all":       all_slots,
        "closed":    False,
    }


def is_slot_conflicted(date_str: str, slot: str, staff_name: str) -> bool:
    """Check if slot is already taken — used for CONFLICT ALERT (not blocking)."""
    booked_data = get_booked_slots(date_str, staff_name)
    return any(s == slot for s, _ in booked_data)
