"""Public and administrative event registration without financial side effects."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    require_browser_origin,
    require_csrf,
    require_event_secretary,
)
from app.models import AuditLog, Event, Guest, Registration, Wallet
from app.services.auth import Actor
from app.services.guests import normalize_phone

public_router = APIRouter(prefix="/api/public", tags=["registrations"])
admin_router = APIRouter(prefix="/api/admin", tags=["registrations"])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Member(StrictBody):
    first_name: str = ""
    last_name: str = ""
    phone: str = ""


class GroupBody(StrictBody):
    members: list[Member] = Field(min_length=1, max_length=20)


class AdminRegistration(StrictBody):
    guest_id: int | None = Field(default=None, gt=0)
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None


def register_one(
    session: Session, event_id: int, *, member: Member | None = None,
    guest_id: int | None = None, actor: Actor | None = None,
) -> int:
    if guest_id is None:
        if member is None or not member.first_name.strip() or not member.last_name.strip():
            raise HTTPException(status_code=422, detail="invalid_registration")
        if len(member.first_name.strip()) > 100 or len(member.last_name.strip()) > 100:
            raise HTTPException(status_code=422, detail="invalid_registration")
        try:
            phone = normalize_phone(member.phone)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_phone") from None
    for attempt in range(2):
        try:
            with session.begin():
                event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
                if event is None or (actor is None and event.is_cancelled):
                    raise HTTPException(status_code=404, detail="event_not_found")
                if event.is_cancelled:
                    raise HTTPException(status_code=409, detail="event_cancelled")
                if event.registration_status != "open":
                    raise HTTPException(status_code=409, detail="registration_closed")
                if guest_id is not None:
                    guest = session.get(Guest, guest_id)
                    if guest is None:
                        raise HTTPException(status_code=404, detail="guest_not_found")
                else:
                    guest = session.scalar(select(Guest).where(Guest.phone == phone))
                    if guest is None:
                        guest = Guest(first_name=member.first_name.strip(),
                                      last_name=member.last_name.strip(), phone=phone)
                        session.add(guest)
                        session.flush()
                        session.add(Wallet(guest_id=guest.id, balance=0))
                if session.scalar(select(Registration.id).where(
                    Registration.event_id == event_id, Registration.guest_id == guest.id
                )) is not None:
                    raise HTTPException(status_code=409, detail="already_registered")
                registration = Registration(event_id=event_id, guest_id=guest.id,
                                            status="active", attendance="pending",
                                            source="admin" if actor else "public")
                session.add(registration)
                session.flush()
                session.add(AuditLog(actor_type="user" if actor else "system",
                                     actor_id=actor.id if actor else None,
                                     action="registration.created", entity_type="registration",
                                     entity_id=registration.id,
                                     after_json={"event_id": event_id, "guest_id": guest.id,
                                                 "source": registration.source}))
                result = registration.id
            return result
        except IntegrityError:
            session.rollback()
            if attempt == 1:
                raise HTTPException(status_code=409, detail="already_registered") from None
    raise HTTPException(status_code=409, detail="already_registered")


@public_router.post("/events/{event_id}/register",
                    dependencies=[Depends(require_browser_origin)])
def register_public(
    event_id: int, body: GroupBody, session: Session = Depends(get_db),
) -> dict:
    event = session.get(Event, event_id)
    if event is None or event.is_cancelled:
        raise HTTPException(status_code=404, detail="event_not_found")
    if event.registration_status != "open":
        raise HTTPException(status_code=409, detail="registration_closed")
    session.rollback()
    results = []
    for index, member in enumerate(body.members):
        try:
            registration_id = register_one(session, event_id, member=member)
            results.append({"index": index, "status": "created",
                            "registration_id": registration_id})
        except HTTPException as error:
            results.append({"index": index, "status": "error", "code": error.detail})
    return {"results": results}


@admin_router.post("/events/{event_id}/registrations", status_code=201,
                   dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def register_admin(
    event_id: int, body: AdminRegistration,
    actor: Actor = Depends(require_event_secretary),
    session: Session = Depends(get_db),
) -> dict:
    member = None
    if body.guest_id is None:
        if body.first_name is None or body.last_name is None or body.phone is None:
            raise HTTPException(status_code=422, detail="invalid_registration")
        member = Member(first_name=body.first_name, last_name=body.last_name, phone=body.phone)
    elif any(value is not None for value in (body.first_name, body.last_name, body.phone)):
        raise HTTPException(status_code=422, detail="invalid_registration")
    registration_id = register_one(session, event_id, member=member,
                                   guest_id=body.guest_id, actor=actor)
    return {"id": registration_id, "event_id": event_id, "status": "active",
            "attendance": "pending"}
