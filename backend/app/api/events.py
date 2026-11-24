"""Event and shared-location management, guarded by assignment."""

from datetime import date, datetime, time
from io import BytesIO
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    require_active_admin,
    require_browser_origin,
    require_csrf,
    require_event_secretary,
)
from app.core.storage import uploads_root
from app.models import (
    AuditLog,
    Event,
    EventSecretary,
    Location,
    PaymentSubmission,
    Registration,
    User,
)
from app.services.auth import Actor

router = APIRouter(prefix="/api/admin", tags=["events"])
POSTER_DIR = uploads_root() / "posters"
MAX_POSTER_BYTES = 5 * 1024 * 1024
MAX_POSTER_PIXELS = 20_000_000
POSTER_MIMES = {
    "image/jpeg": {"JPEG"}, "image/png": {"PNG"}, "image/webp": {"WEBP"},
    "image/heic": {"HEIF"}, "image/heif": {"HEIF"},
}
register_heif_opener()


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class LocationBody(StrictBody):
    title: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1)
    map_link: str | None = None

    @field_validator("title", "address")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class EventFields(StrictBody):
    event_number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_date: date | None = None
    start_time: time | None = None
    time_text: str | None = Field(default=None, max_length=200)
    time_mode: Literal["exact", "approximate", "tba"] = "tba"
    location_id: int | None = None
    location_mode: Literal["exact", "approximate", "tba"] = "tba"
    location_text: str | None = None
    hosts: str | None = None
    entry_fee: int = Field(default=0, ge=0)
    capacity: int | None = Field(default=None, ge=0)
    public_note: str | None = None
    registration_status: Literal["open", "closed"] = "closed"

    @field_validator("title")
    @classmethod
    def title_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class CreateEvent(EventFields):
    secretary_ids: list[int] = Field(default_factory=list)


class UpdateEvent(StrictBody):
    event_number: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    event_date: date | None = None
    start_time: time | None = None
    time_text: str | None = Field(default=None, max_length=200)
    time_mode: Literal["exact", "approximate", "tba"] | None = None
    location_id: int | None = None
    location_mode: Literal["exact", "approximate", "tba"] | None = None
    location_text: str | None = None
    hosts: str | None = None
    entry_fee: int | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, ge=0)
    public_note: str | None = None
    registration_status: Literal["open", "closed"] | None = None

    @field_validator("title")
    @classmethod
    def title_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value.strip() if value is not None else None


class SecretariesBody(StrictBody):
    user_ids: list[int] = Field(min_length=1)


EVENT_FIELDS = set(EventFields.model_fields)
NON_NULLABLE = {
    "event_number", "title", "time_mode", "location_mode", "entry_fee", "registration_status"
}


def log_change(
    session: Session, *, actor: Actor, action: str, entity_type: str, entity_id: int,
    before: dict | None = None, after: dict | None = None,
) -> None:
    session.add(AuditLog(
        actor_type="user", actor_id=actor.id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        before_json=before, after_json=after,
    ))


def location_view(session: Session, location: Location) -> dict:
    count = session.scalar(
        select(func.count()).select_from(Event).where(Event.location_id == location.id)
    )
    return {
        "id": location.id, "title": location.title, "address": location.address,
        "map_link": location.map_link, "linked_event_count": count,
    }


def event_view(session: Session, event: Event) -> dict:
    location = session.get(Location, event.location_id) if event.location_id else None
    secretaries = session.execute(
        select(User.id, User.full_name, User.is_active).join(
            EventSecretary, EventSecretary.user_id == User.id
        ).where(EventSecretary.event_id == event.id).order_by(User.id)
    ).all()
    return {
        "id": event.id, "event_number": event.event_number, "title": event.title,
        "poster_url": f"/api/public/events/{event.id}/poster" if event.poster_path else None,
        "description": event.description, "event_date": event.event_date,
        "start_time": event.start_time, "time_text": event.time_text,
        "time_mode": event.time_mode,
        "location_id": event.location_id, "location_mode": event.location_mode,
        "location_text": event.location_text,
        "location": location_view(session, location) if location else None,
        "hosts": event.hosts, "entry_fee": event.entry_fee, "capacity": event.capacity,
        "public_note": event.public_note, "registration_status": event.registration_status,
        "is_cancelled": event.is_cancelled,
        "secretaries": [
            {"id": user_id, "full_name": name, "is_active": active}
            for user_id, name, active in secretaries
        ],
        "created_at": event.created_at, "updated_at": event.updated_at,
    }


def validate_event(session: Session, data: dict) -> None:
    if data["time_mode"] == "exact":
        if not data.get("event_date") or not data.get("start_time"):
            raise HTTPException(status_code=422, detail="exact_time_incomplete")
    elif data["time_mode"] == "approximate":
        if not data.get("time_text") or not data["time_text"].strip():
            raise HTTPException(status_code=422, detail="approximate_time_incomplete")
    if data["location_mode"] == "exact":
        if not data.get("location_id"):
            raise HTTPException(status_code=422, detail="exact_location_incomplete")
    elif data["location_mode"] == "approximate":
        if not data.get("location_text") or not data["location_text"].strip():
            raise HTTPException(status_code=422, detail="approximate_location_incomplete")
    if data.get("location_id") is not None and session.get(Location, data["location_id"]) is None:
        raise HTTPException(status_code=422, detail="location_not_found")


def active_secretaries(session: Session, ids: set[int]) -> None:
    if not ids:
        raise HTTPException(status_code=422, detail="secretary_required")
    found = set(session.scalars(select(User.id).where(
        User.id.in_(ids), User.role == "secretary", User.is_active.is_(True)
    )))
    if found != ids:
        raise HTTPException(status_code=422, detail="inactive_or_invalid_secretary")


@router.get("/secretaries")
def list_active_secretaries(
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db)
) -> list[dict]:
    rows = session.scalars(select(User).where(
        User.role == "secretary", User.is_active.is_(True)
    ).order_by(User.full_name, User.id)).all()
    return [{"id": user.id, "full_name": user.full_name} for user in rows]


@router.get("/events/next-number")
def next_event_number(
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db)
) -> dict:
    # Advisory only: the database unique constraint resolves concurrent creates.
    return {"suggested_number": (session.scalar(select(func.max(Event.event_number))) or 0) + 1}


@router.get("/events")
def list_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    cancelled: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    period: Literal["all", "upcoming", "archive", "cancelled"] = "all",
    registration_status: Literal["open", "closed"] | None = None,
    q: str = Query(default="", max_length=100),
    _: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    filters = []
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    today = now.date()
    current_time = now.time().replace(tzinfo=None)
    started_today = and_(Event.event_date == today, Event.start_time.is_not(None),
                         Event.start_time < current_time)
    if period == "upcoming":
        filters.extend([Event.is_cancelled.is_(False), Event.is_historical_import.is_(False),
                        or_(Event.event_date > today, Event.event_date.is_(None),
                            and_(Event.event_date == today,
                                 or_(Event.start_time.is_(None),
                                     Event.start_time >= current_time)))])
    elif period == "archive":
        filters.extend([Event.is_cancelled.is_(False),
                        or_(Event.is_historical_import.is_(True), Event.event_date < today,
                            started_today)])
    elif period == "cancelled":
        filters.append(Event.is_cancelled.is_(True))
    if cancelled is not None:
        filters.append(Event.is_cancelled.is_(cancelled))
    if registration_status is not None:
        filters.append(Event.registration_status == registration_status)
    if date_from is not None:
        filters.append(Event.event_date >= date_from)
    if date_to is not None:
        filters.append(Event.event_date <= date_to)
    search = q.strip()
    if search:
        normalized = search.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = [Event.title.ilike(f"%{escaped}%", escape="\\"),
                   Event.hosts.ilike(f"%{escaped}%", escape="\\")]
        if normalized.isdecimal():
            matches.append(Event.event_number == int(normalized))
        filters.append(or_(*matches))
    total = session.scalar(select(func.count()).select_from(Event).where(*filters))
    rows = session.scalars(select(Event).where(*filters).order_by(Event.event_number.desc())
                           .limit(limit).offset(offset)).all()
    return {"items": [event_view(session, row) for row in rows],
            "total": total, "limit": limit, "offset": offset}


@router.get("/events/{event_id}")
def get_event(
    event_id: int, _: Actor = Depends(require_active_admin), session: Session = Depends(get_db)
) -> dict:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return event_view(session, event)


@router.post(
    "/events", status_code=201,
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def create_event(
    body: CreateEvent, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    data = body.model_dump(exclude={"secretary_ids"})
    ids = set(body.secretary_ids)
    if actor.role == "secretary":
        ids.add(actor.id)
    try:
        with session.begin():
            active_secretaries(session, ids)
            validate_event(session, data)
            event = Event(**data)
            session.add(event)
            session.flush()
            session.add_all(EventSecretary(event_id=event.id, user_id=user_id)
                            for user_id in sorted(ids))
            log_change(session, actor=actor, action="event.created", entity_type="event",
                       entity_id=event.id, after={"event_number": event.event_number})
            session.flush()
            result = event_view(session, event)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="event_number_exists") from None
    return result


@router.post(
    "/events/{event_id}/poster",
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def upload_event_poster(
    event_id: int, poster: UploadFile = File(...),
    actor: Actor = Depends(require_event_secretary), session: Session = Depends(get_db),
) -> dict:
    allowed = POSTER_MIMES.get(poster.content_type or "")
    if allowed is None:
        raise HTTPException(status_code=422, detail="invalid_poster_type")
    data = poster.file.read(MAX_POSTER_BYTES + 1)
    if not data or len(data) > MAX_POSTER_BYTES:
        raise HTTPException(status_code=422, detail="invalid_poster_size")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in allowed or source.width * source.height > MAX_POSTER_PIXELS:
                raise HTTPException(status_code=422, detail="invalid_poster_image")
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            if image.width > 5000 or image.height > 5000:
                raise HTTPException(status_code=422, detail="invalid_poster_dimensions")
            preview = BytesIO()
            image.save(preview, format="JPEG", quality=88, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="invalid_poster_image") from None

    poster_id = uuid4().hex
    preview_name = f"{poster_id}.jpg"
    preview_path = POSTER_DIR / preview_name
    original_path = POSTER_DIR / f"{poster_id}.original"
    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with session.begin():
            event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
            if event is None:
                raise HTTPException(status_code=404, detail="event_not_found")
            if event.is_cancelled:
                raise HTTPException(status_code=409, detail="event_cancelled")
            preview_path.write_bytes(preview.getvalue())
            original_path.write_bytes(data)
            before = {"poster_path": event.poster_path}
            event.poster_path = preview_name
            log_change(session, actor=actor, action="event.poster_updated", entity_type="event",
                       entity_id=event.id, before=before, after={"poster_path": preview_name})
            session.flush()
            result = event_view(session, event)
    except Exception:
        preview_path.unlink(missing_ok=True)
        original_path.unlink(missing_ok=True)
        raise
    return result


@router.patch(
    "/events/{event_id}",
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def update_event(
    event_id: int, body: UpdateEvent,
    actor: Actor = Depends(require_event_secretary),
    session: Session = Depends(get_db),
) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(changes.get(field) is None for field in NON_NULLABLE if field in changes):
        raise HTTPException(status_code=422, detail="invalid_update")
    try:
        with session.begin():
            event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
            if event is None:
                raise HTTPException(status_code=404, detail="event_not_found")
            if event.is_cancelled:
                raise HTTPException(status_code=409, detail="event_cancelled")
            changing_fee = "entry_fee" in changes and changes["entry_fee"] != event.entry_fee
            has_registration = session.scalar(
                select(Registration.id).where(Registration.event_id == event_id).limit(1)
            ) is not None
            if changing_fee and has_registration:
                raise HTTPException(status_code=409, detail="entry_fee_has_registrations")
            merged = {key: getattr(event, key) for key in EVENT_FIELDS}
            merged.update(changes)
            validate_event(session, merged)
            before = {key: str(getattr(event, key)) for key in changes}
            for key, value in changes.items():
                setattr(event, key, value)
            log_change(session, actor=actor, action="event.updated", entity_type="event",
                       entity_id=event.id, before=before,
                       after={key: str(value) for key, value in changes.items()})
            session.flush()
            result = event_view(session, event)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="event_number_exists") from None
    return result


@router.put(
    "/events/{event_id}/secretaries",
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def replace_event_secretaries(
    event_id: int, body: SecretariesBody,
    actor: Actor = Depends(require_event_secretary),
    session: Session = Depends(get_db),
) -> dict:
    ids = set(body.user_ids)
    with session.begin():
        event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
        active_secretaries(session, ids)
        old = set(session.scalars(select(EventSecretary.user_id).where(
            EventSecretary.event_id == event_id
        )))
        inactive_historical = set(session.scalars(select(User.id).join(
            EventSecretary, EventSecretary.user_id == User.id
        ).where(EventSecretary.event_id == event_id, User.is_active.is_(False))))
        preserved = ids | inactive_historical
        session.execute(delete(EventSecretary).where(
            EventSecretary.event_id == event_id,
            EventSecretary.user_id.not_in(preserved),
        ))
        session.add_all(EventSecretary(event_id=event_id, user_id=user_id)
                        for user_id in sorted(preserved - old))
        log_change(session, actor=actor, action="event.secretaries_updated",
                   entity_type="event", entity_id=event_id,
                   before={"user_ids": sorted(old)}, after={"user_ids": sorted(preserved)})
        session.flush()
        result = event_view(session, event)
    return result


@router.delete(
    "/events/{event_id}", status_code=204,
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def delete_event(
    event_id: int, actor: Actor = Depends(require_event_secretary),
    session: Session = Depends(get_db),
) -> None:
    try:
        with session.begin():
            event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
            has_registration = session.scalar(select(Registration.id).where(
                Registration.event_id == event_id).limit(1)) is not None
            has_payment = session.scalar(select(PaymentSubmission.id).where(
                PaymentSubmission.event_id == event_id).limit(1)) is not None
            if has_registration or has_payment:
                raise HTTPException(status_code=409, detail="event_has_history")
            snapshot = {"event_number": event.event_number, "title": event.title,
                        "event_date": str(event.event_date), "location_id": event.location_id}
            session.execute(delete(EventSecretary).where(EventSecretary.event_id == event_id))
            session.delete(event)
            log_change(session, actor=actor, action="event.deleted", entity_type="event",
                       entity_id=event_id, before=snapshot)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="event_has_history") from None


@router.get("/locations")
def list_locations(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    total = session.scalar(select(func.count()).select_from(Location))
    rows = session.scalars(select(Location).order_by(Location.title, Location.id)
                           .limit(limit).offset(offset)).all()
    return {"items": [location_view(session, row) for row in rows],
            "total": total, "limit": limit, "offset": offset}


@router.post(
    "/locations", status_code=201,
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def create_location(
    body: LocationBody, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    with session.begin():
        location = Location(**body.model_dump())
        session.add(location)
        session.flush()
        log_change(session, actor=actor, action="location.created", entity_type="location",
                   entity_id=location.id, after=body.model_dump())
        result = location_view(session, location)
    return result


@router.get("/locations/{location_id}")
def get_location(
    location_id: int, _: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    location = session.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="location_not_found")
    return location_view(session, location)


@router.patch(
    "/locations/{location_id}",
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def update_location(
    location_id: int, body: LocationBody,
    actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    with session.begin():
        location = session.scalar(
            select(Location).where(Location.id == location_id).with_for_update()
        )
        if location is None:
            raise HTTPException(status_code=404, detail="location_not_found")
        linked = set(session.scalars(select(Event.id).where(Event.location_id == location_id)))
        if linked and actor.role != "super_admin":
            assigned = set(session.scalars(select(EventSecretary.event_id).where(
                EventSecretary.user_id == actor.id,
                EventSecretary.event_id.in_(linked),
            )))
            if assigned != linked:
                raise HTTPException(status_code=403, detail="forbidden")
        before = {key: getattr(location, key) for key in LocationBody.model_fields}
        for key, value in body.model_dump().items():
            setattr(location, key, value)
        log_change(session, actor=actor, action="location.updated", entity_type="location",
                   entity_id=location.id, before=before, after=body.model_dump())
        session.flush()
        result = location_view(session, location)
    return result


@router.delete(
    "/locations/{location_id}", status_code=204,
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def delete_location(
    location_id: int, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> None:
    try:
        with session.begin():
            location = session.scalar(
                select(Location).where(Location.id == location_id).with_for_update()
            )
            if location is None:
                raise HTTPException(status_code=404, detail="location_not_found")
            if session.scalar(select(Event.id).where(Event.location_id == location_id).limit(1)):
                raise HTTPException(status_code=409, detail="location_has_events")
            snapshot = {"title": location.title, "address": location.address,
                        "map_link": location.map_link}
            session.delete(location)
            log_change(session, actor=actor, action="location.deleted", entity_type="location",
                       entity_id=location_id, before=snapshot)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="location_has_events") from None
