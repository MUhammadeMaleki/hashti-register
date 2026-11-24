"""Guest creation keeps the profile and zero-balance wallet in one transaction."""

import re
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.models import Guest, Wallet


class GuestProfile(NamedTuple):
    guest_id: int
    wallet_id: int


def normalize_phone(value: str) -> str:
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    phone = re.sub(r"[\s\-]", "", value.translate(digits))
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    if not re.fullmatch(r"09[0-9]{9}", phone):
        raise ValueError("A valid Iranian mobile number is required")
    return phone


def create_guest_with_wallet(
    session: Session, *, first_name: str, last_name: str, phone: str
) -> GuestProfile:
    """Owns a transaction; an insert failure rolls back both records."""
    normalized = normalize_phone(phone)
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not first_name or not last_name:
        raise ValueError("First and last name are required")
    with session.begin():
        guest = Guest(first_name=first_name, last_name=last_name, phone=normalized)
        session.add(guest)
        session.flush()
        wallet = Wallet(guest_id=guest.id, balance=0)
        session.add(wallet)
        session.flush()
        return GuestProfile(guest.id, wallet.id)
