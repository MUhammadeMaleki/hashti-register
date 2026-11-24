"""Public catalogue and aggregate counts; no personal guest data is exposed."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.events import POSTER_DIR
from app.models import Event, Guest, Location, Setting

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/stats")
def public_stats(session: Session = Depends(get_db)) -> dict:
    return {
        "cafe_count": session.scalar(select(func.count()).select_from(Location)),
        "guest_count": session.scalar(select(func.count()).select_from(Guest)),
        "event_count": session.scalar(select(func.count()).select_from(Event).where(
            Event.is_cancelled.is_(False)
        )),
    }


def public_event(session: Session, event: Event) -> dict:
    location = session.get(Location, event.location_id) if event.location_id else None
    return {
        "id": event.id,
        "event_number": event.event_number,
        "title": event.title,
        "poster_url": f"/api/public/events/{event.id}/poster" if event.poster_path else None,
        "description": event.description,
        "event_date": event.event_date,
        "start_time": event.start_time,
        "time_text": event.time_text,
        "time_mode": event.time_mode,
        "location_mode": event.location_mode,
        "location_text": event.location_text,
        "location": ({
            "title": location.title,
            "address": location.address,
            "map_link": location.map_link,
        } if location and event.location_mode == "exact" else None),
        "hosts": event.hosts,
        "entry_fee": event.entry_fee,
        "public_note": event.public_note,
        "registration_status": event.registration_status,
    }


@router.get("/events")
def list_public_events(
    period: str = Query(default="upcoming", pattern="^(upcoming|archive)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    today = now.date()
    current_time = now.time().replace(tzinfo=None)
    started_today = and_(Event.event_date == today, Event.start_time.is_not(None),
                         Event.start_time < current_time)
    filters = [Event.is_cancelled.is_(False)]
    if period == "archive":
        filters.append(or_(Event.is_historical_import.is_(True), Event.event_date < today,
                           started_today))
        ordering = (Event.event_date.desc().nulls_last(), Event.event_number.desc())
    else:
        filters.append(Event.is_historical_import.is_(False))
        filters.append(or_(Event.event_date > today, Event.event_date.is_(None),
                           and_(Event.event_date == today,
                                or_(Event.start_time.is_(None),
                                    Event.start_time >= current_time))))
        ordering = (Event.event_date.asc().nulls_last(), Event.event_number.asc())
    total = session.scalar(select(func.count()).select_from(Event).where(*filters))
    rows = session.scalars(select(Event).where(*filters).order_by(*ordering)
                           .limit(limit).offset(offset)).all()
    return {"items": [public_event(session, event) for event in rows],
            "total": total, "limit": limit, "offset": offset}


@router.get("/events/{event_id}")
def get_public_event(event_id: int, session: Session = Depends(get_db)) -> dict:
    event = session.scalar(select(Event).where(
        Event.id == event_id, Event.is_cancelled.is_(False)
    ))
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return public_event(session, event)


@router.get("/events/{event_id}/poster")
def get_public_poster(event_id: int, session: Session = Depends(get_db)) -> FileResponse:
    event = session.scalar(select(Event).where(
        Event.id == event_id, Event.is_cancelled.is_(False)
    ))
    if event is None or not event.poster_path:
        raise HTTPException(status_code=404, detail="poster_not_found")
    path = POSTER_DIR / event.poster_path
    if path.name != event.poster_path or not path.is_file():
        raise HTTPException(status_code=404, detail="poster_not_found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/settings/public")
def get_public_settings(session: Session = Depends(get_db)) -> dict:
    public_keys = {
        "organization_name", "telegram_support_link", "bale_support_link",
        "support_phone", "card_number", "account_holder",
    }
    values = session.scalars(select(Setting).where(Setting.key.in_(public_keys))).all()
    return {key: next((row.value for row in values if row.key == key), None)
            for key in sorted(public_keys)}
