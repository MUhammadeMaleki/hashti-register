"""Display-number lifecycle, independent of stable event IDs."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import AuditLog, Event

TEHRAN = ZoneInfo("Asia/Tehran")


def lock_numbers(session: Session) -> None:
    """Serialize all number writes within the current PostgreSQL transaction."""
    session.execute(text("SELECT pg_advisory_xact_lock(720284511)"))


def is_archived(event: Event, now: datetime | None = None) -> bool:
    now = now or datetime.now(TEHRAN)
    return bool(event.is_historical_import or event.event_date and (
        event.event_date < now.date() or
        event.event_date == now.date() and event.start_time is not None and
        event.start_time < now.time().replace(tzinfo=None)
    ))


def next_number(session: Session) -> int:
    return (session.scalar(select(func.max(Event.event_number)).where(
        Event.number_released.is_(False))) or 0) + 1


def release_and_compact(session: Session, event: Event, *, actor_id: int) -> None:
    """Free a canceled future event's number and shift later future events down."""
    if event.number_released or is_archived(event):
        return
    freed = event.event_number
    event.number_released = True
    session.flush()
    movable = session.scalars(select(Event).where(
        Event.number_released.is_(False), Event.is_cancelled.is_(False),
        Event.event_number > freed,
    ).order_by(Event.event_number, Event.id).with_for_update()).all()
    movable = [row for row in movable if not is_archived(row)]
    if not movable:
        return
    moving_ids = {row.id for row in movable}
    occupied = set(session.scalars(select(Event.event_number).where(
        Event.number_released.is_(False), Event.id.not_in(moving_ids))))
    changes = []
    slot = freed
    for row in movable:
        while slot in occupied:
            slot += 1
        moved = slot < row.event_number
        if moved:
            changes.append((row, row.event_number, slot))
        else:
            occupied.add(row.event_number)
        slot = row.event_number if moved else row.event_number + 1
    if not changes:
        return
    temporary = next_number(session)
    for offset, (row, _, _) in enumerate(changes):
        row.event_number = temporary + offset
    session.flush()
    for row, old, new in changes:
        row.event_number = new
        session.add(AuditLog(actor_type="user", actor_id=actor_id,
                             action="event.renumbered", entity_type="event", entity_id=row.id,
                             before_json={"event_number": old},
                             after_json={"event_number": new}))
    session.flush()
