"""Read-only reporting projections from active charges and the wallet ledger."""

from collections import Counter, defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Event,
    EventCharge,
    EventDiscount,
    Guest,
    GuestInterestTag,
    InterestTag,
    PaymentSubmission,
    Registration,
    Wallet,
    WalletTransaction,
)


def registration_rows(session: Session) -> list[dict]:
    charges = select(
        EventCharge.registration_id.label("registration_id"),
        func.sum(EventCharge.amount).filter(EventCharge.type == "entry").label("entry"),
        func.sum(EventCharge.amount).filter(EventCharge.type == "order").label("orders"),
    ).where(EventCharge.is_cancelled.is_(False)).group_by(
        EventCharge.registration_id).subquery()
    settlements = select(
        WalletTransaction.registration_id.label("registration_id"),
        (-func.sum(WalletTransaction.amount)).label("amount"),
    ).where(WalletTransaction.type.in_(["settlement", "refund"])).group_by(
        WalletTransaction.registration_id).subquery()
    discounts = select(
        EventDiscount.registration_id.label("registration_id"),
        func.sum(EventDiscount.amount).label("amount"),
    ).group_by(EventDiscount.registration_id).subquery()
    rows = session.execute(select(
        Registration.id, Registration.guest_id, Registration.status,
        Registration.attendance, Registration.created_at,
        Event.id, Event.event_number, Event.title, Event.event_date, Event.is_cancelled,
        Guest.first_name, Guest.last_name, Guest.phone,
        func.coalesce(charges.c.entry, 0), func.coalesce(charges.c.orders, 0),
        func.coalesce(settlements.c.amount, 0),
        func.coalesce(discounts.c.amount, 0),
    ).join(Event, Event.id == Registration.event_id)
        .join(Guest, Guest.id == Registration.guest_id)
        .outerjoin(charges, charges.c.registration_id == Registration.id)
        .outerjoin(settlements, settlements.c.registration_id == Registration.id)
        .outerjoin(discounts, discounts.c.registration_id == Registration.id)
        .order_by(Registration.id)).all()
    result = []
    for (registration_id, guest_id, status, attendance, created_at,
         event_id, event_number, title, event_date, is_cancelled,
         first_name, last_name, phone, entry, orders, settled, discount) in rows:
        entry, orders, settled, discount = int(entry), int(orders), int(settled), int(discount)
        result.append({
            "id": registration_id, "guest_id": guest_id, "status": status,
            "attendance": attendance, "created_at": created_at,
            "event_id": event_id, "event_number": event_number,
            "event_title": title, "event_date": event_date,
            "event_cancelled": is_cancelled, "guest_name": f"{first_name} {last_name}",
            "phone": phone, "entry": entry, "orders": orders,
            "charges": entry + orders, "settled": settled, "discount": discount,
            "debt": entry + orders - settled - discount,
        })
    return result


def within_period(row: dict, date_from: date | None, date_to: date | None) -> bool:
    event_date = row["event_date"]
    return (date_from is None or event_date is not None and event_date >= date_from) and (
        date_to is None or event_date is not None and event_date <= date_to)


def event_report(rows: list[dict], event: Event, search: str = "") -> dict:
    active = [row for row in rows if row["event_id"] == event.id and row["status"] == "active"]
    debtors = [row for row in active if row["debt"] > 0 and
               search.casefold() in f'{row["guest_name"]} {row["phone"]}'.casefold()]
    debtors.sort(key=lambda row: (-row["debt"], row["guest_id"]))
    return {
        "event": {"id": event.id, "event_number": event.event_number,
                  "title": event.title, "event_date": event.event_date,
                  "is_cancelled": event.is_cancelled},
        "present_count": sum(row["attendance"] == "present" for row in active),
        "entry_total": sum(row["entry"] for row in active),
        "orders_total": sum(row["orders"] for row in active),
        "charges_total": sum(row["charges"] for row in active),
        "settled_total": sum(row["settled"] for row in active),
        "discount_total": sum(row["discount"] for row in active),
        "debt_total": sum(row["debt"] for row in active),
        "unsettled_count": sum(row["debt"] > 0 for row in active),
        "debtors": [{"guest_id": row["guest_id"], "name": row["guest_name"],
                     "phone": row["phone"], "registration_id": row["id"],
                     "charges": row["charges"], "settled": row["settled"],
                     "discount": row["discount"],
                     "debt": row["debt"]} for row in debtors],
    }


def financial_guests(session: Session, rows: list[dict]) -> list[dict]:
    debts = defaultdict(int)
    unsettled = Counter()
    for row in rows:
        if row["status"] == "active":
            debts[row["guest_id"]] += row["debt"]
            unsettled[row["guest_id"]] += row["debt"] > 0
    latest = {}
    for guest_id, created_at in session.execute(select(
        Wallet.guest_id, func.max(WalletTransaction.created_at)
    ).join(WalletTransaction, WalletTransaction.wallet_id == Wallet.id)
        .group_by(Wallet.guest_id)):
        latest[guest_id] = created_at
    guests = session.execute(select(
        Guest.id, Guest.first_name, Guest.last_name, Guest.phone, Wallet.balance
    ).join(Wallet, Wallet.guest_id == Guest.id).order_by(Guest.id)).all()
    result = []
    for guest_id, first, last, phone, balance in guests:
        debt = debts[guest_id]
        result.append({"guest_id": guest_id, "name": f"{first} {last}",
                       "phone": phone, "wallet_balance": balance, "debt": debt,
                       "net_debt": debt - balance, "unsettled_events": unsettled[guest_id],
                       "last_transaction_at": latest.get(guest_id)})
    return result


def guest_report(
    session: Session, rows: list[dict], *, date_from: date | None = None,
    date_to: date | None = None, event_id: int | None = None,
    min_attendance: int = 0, min_absence: int = 0,
    interest_tag_id: int | None = None, guest_kind: str | None = None,
    attendance: str | None = None, financial_status: str | None = None,
    search: str = "", limit: int = 50, offset: int = 0,
) -> dict:
    finance = financial_guests(session, rows)
    active = [row for row in rows if row["status"] == "active" and not row["event_cancelled"]]
    selected = [row for row in active if within_period(row, date_from, date_to) and
                (event_id is None or row["event_id"] == event_id)]
    by_guest = defaultdict(list)
    for row in selected:
        by_guest[row["guest_id"]].append(row)
    global_present = Counter(row["guest_id"] for row in active
                             if row["attendance"] == "present")
    tagged_ids = None
    if interest_tag_id is not None:
        tagged_ids = set(session.scalars(select(GuestInterestTag.guest_id).where(
            GuestInterestTag.tag_id == interest_tag_id)))
    items = []
    for guest in finance:
        guest_id = guest["guest_id"]
        history = by_guest[guest_id]
        present = sum(row["attendance"] == "present" for row in history)
        absent = sum(row["attendance"].startswith("absent") for row in history)
        if (event_id is not None or date_from is not None or date_to is not None) and not history:
            continue
        if present < min_attendance or absent < min_absence:
            continue
        if tagged_ids is not None and guest_id not in tagged_ids:
            continue
        if guest_kind == "new" and global_present[guest_id] > 1:
            continue
        if guest_kind == "returning" and global_present[guest_id] <= 1:
            continue
        if attendance is not None and not any(row["attendance"] == attendance for row in history):
            continue
        if financial_status == "debtor" and guest["net_debt"] <= 0:
            continue
        if financial_status == "credit" and guest["net_debt"] >= 0:
            continue
        if financial_status == "balanced" and guest["net_debt"] != 0:
            continue
        if search.casefold() not in f'{guest["name"]} {guest["phone"]}'.casefold():
            continue
        items.append({**guest, "attendance_count": present, "absence_count": absent,
                      "guest_kind": "returning" if global_present[guest_id] > 1 else "new"})
    items.sort(key=lambda item: (-item["net_debt"], item["guest_id"]))
    return {"items": items[offset:offset + limit], "total": len(items),
            "limit": limit, "offset": offset}


def dashboard(session: Session, rows: list[dict]) -> dict:
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    today = now.date()
    current_time = now.time().replace(tzinfo=None)
    events = session.scalars(select(Event)).all()
    finance = financial_guests(session, rows)
    pending = session.scalar(select(func.count()).select_from(PaymentSubmission).where(
        PaymentSubmission.status == "pending")) or 0
    active = [row for row in rows if row["status"] == "active"]
    upcoming_ids = {event.id for event in events if not event.is_cancelled and
                    not event.is_historical_import and (
                        event.event_date is None or event.event_date > today or
                        event.event_date == today and (
                            event.start_time is None or event.start_time >= current_time
                        )
                    )}
    return {
        "guest_count": len(finance),
        "upcoming_event_count": len(upcoming_ids),
        "upcoming_registration_count": sum(row["event_id"] in upcoming_ids for row in active),
        "pending_receipt_count": pending,
        "debtor_count": sum(row["debt"] > 0 for row in finance),
        "total_debt": sum(row["debt"] for row in finance),
        "held_event_count": sum(not event.is_cancelled and (
            event.is_historical_import or event.event_date is not None and (
                event.event_date < today or event.event_date == today and
                event.start_time is not None and event.start_time < current_time
            )
        ) for event in events),
    }


def charts(session: Session, rows: list[dict], date_from: date | None,
           date_to: date | None, *, guest_ids: set[int] | None = None,
           event_id: int | None = None) -> dict:
    active = [row for row in rows if row["status"] == "active" and
              not row["event_cancelled"] and
              (guest_ids is None or row["guest_id"] in guest_ids)]
    selected = [row for row in active if within_period(row, date_from, date_to) and
                (event_id is None or row["event_id"] == event_id)]
    present = [row for row in selected if row["attendance"] == "present"]
    attendance_count = Counter(row["guest_id"] for row in present)
    buckets = {"1-2": 0, "3-4": 0, "5-9": 0, "10+": 0}
    for count in attendance_count.values():
        bucket = "1-2" if count <= 2 else "3-4" if count <= 4 else "5-9" if count <= 9 else "10+"
        buckets[bucket] += 1
    trend = Counter(row["event_date"].isoformat() for row in present if row["event_date"])
    popular = Counter((row["event_id"], row["event_title"]) for row in present)
    lifetime_present = Counter(row["guest_id"] for row in active
                               if row["attendance"] == "present")
    new_count = sum(lifetime_present[guest_id] == 1 for guest_id in attendance_count)
    returning_count = len(attendance_count) - new_count
    participant_ids = {row["guest_id"] for row in selected}
    tags = Counter()
    if participant_ids:
        for name in session.scalars(select(InterestTag.name).join(
            GuestInterestTag, GuestInterestTag.tag_id == InterestTag.id
        ).where(GuestInterestTag.guest_id.in_(participant_ids))):
            tags[name] += 1
    absent_kept = sum(row["attendance"] == "absent_kept" for row in selected)
    absent_forfeited = sum(row["attendance"] == "absent_forfeited" for row in selected)
    return {
        "attendance_buckets": buckets,
        "trend": [{"date": day, "count": count} for day, count in sorted(trend.items())],
        "new_vs_returning": {"new": new_count, "returning": returning_count},
        "attendance_ratio": {"present": len(present),
                             "absent": absent_kept + absent_forfeited},
        "absences": {"kept": absent_kept, "forfeited": absent_forfeited},
        "popular_events": [{"event_id": event_id, "title": title, "count": count}
                           for (event_id, title), count in popular.most_common(8)],
        "interests": [{"name": name, "count": count} for name, count in tags.most_common()],
    }
