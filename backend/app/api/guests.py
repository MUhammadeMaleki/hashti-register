"""Administrative contact bank and permanent 360-degree guest profiles."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_active_admin, require_browser_origin, require_csrf
from app.models import (
    AuditLog,
    Event,
    EventCharge,
    EventDiscount,
    EventSecretary,
    Guest,
    GuestAccount,
    GuestInterestTag,
    GuestNote,
    InterestTag,
    PaymentSubmission,
    Registration,
    Setting,
    User,
    Wallet,
    WalletTransaction,
)
from app.services.auth import Actor
from app.services.finance import registration_finance
from app.services.guests import normalize_phone

router = APIRouter(prefix="/api/admin", tags=["guests"])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class GuestFields(StrictBody):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=10, max_length=32)
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, max_length=30)
    education: str | None = Field(default=None, max_length=200)
    internal_note: str | None = None
    debt_ceiling: int | None = Field(default=None, ge=0)

    @field_validator("first_name", "last_name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class GuestPatch(StrictBody):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=10, max_length=32)
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, max_length=30)
    education: str | None = Field(default=None, max_length=200)
    internal_note: str | None = None
    debt_ceiling: int | None = Field(default=None, ge=0)

    @field_validator("first_name", "last_name")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value.strip() if value is not None else None


class TagBody(StrictBody):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class TagsBody(StrictBody):
    tag_ids: list[int]


class NoteBody(StrictBody):
    type: Literal["general", "financial"]
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


def audit(session: Session, actor: Actor, action: str, guest_id: int,
          before: dict | None = None, after: dict | None = None) -> None:
    session.add(AuditLog(actor_type="user", actor_id=actor.id, action=action,
                         entity_type="guest", entity_id=guest_id,
                         before_json=before, after_json=after))


def summary(session: Session, guest: Guest) -> dict:
    wallet = session.scalar(select(Wallet).where(Wallet.guest_id == guest.id))
    return {
        "id": guest.id, "first_name": guest.first_name, "last_name": guest.last_name,
        "phone": guest.phone, "age": guest.age, "gender": guest.gender,
        "education": guest.education, "internal_note": guest.internal_note,
        "debt_ceiling": guest.debt_ceiling,
        "wallet_balance": wallet.balance if wallet else None,
        "has_account": session.scalar(select(GuestAccount.id).where(
            GuestAccount.guest_id == guest.id)) is not None,
        "created_at": guest.created_at, "updated_at": guest.updated_at,
    }


def profile(session: Session, guest: Guest) -> dict:
    data = summary(session, guest)
    data["tags"] = [{"id": tag.id, "name": tag.name} for tag in session.scalars(
        select(InterestTag).join(GuestInterestTag, GuestInterestTag.tag_id == InterestTag.id)
        .where(GuestInterestTag.guest_id == guest.id).order_by(InterestTag.name)
    )]
    notes = session.execute(select(GuestNote, User.full_name).join(
        User, User.id == GuestNote.created_by_user_id
    ).where(GuestNote.guest_id == guest.id).order_by(
        GuestNote.created_at.desc(), GuestNote.id.desc()
    )).all()
    data["notes"] = [{"id": note.id, "type": note.type, "text": note.text,
                       "created_at": note.created_at, "created_by": name}
                     for note, name in notes]
    registrations = session.execute(select(Registration, Event).join(
        Event, Event.id == Registration.event_id
    ).where(Registration.guest_id == guest.id).order_by(
        Event.event_date.desc().nulls_last(), Registration.id.desc()
    )).all()
    history = []
    for registration, event in registrations:
        secretaries = session.execute(select(User.full_name).join(
            EventSecretary, EventSecretary.user_id == User.id
        ).where(EventSecretary.event_id == event.id).order_by(User.id)).scalars().all()
        charges = session.scalars(select(EventCharge).where(
            EventCharge.registration_id == registration.id
        ).order_by(EventCharge.id)).all()
        discounts = session.scalars(select(EventDiscount).where(
            EventDiscount.registration_id == registration.id
        ).order_by(EventDiscount.id)).all()
        finance = registration_finance(session, registration.id)
        history.append({
            "id": registration.id, "status": registration.status,
            "attendance": registration.attendance, "source": registration.source,
            "created_at": registration.created_at,
            "event": {"id": event.id, "event_number": event.event_number,
                      "title": event.title, "event_date": event.event_date,
                      "is_cancelled": event.is_cancelled,
                      "hosts": event.hosts, "secretaries": secretaries},
            "charges": [{"id": charge.id, "type": charge.type,
                         "description": charge.description, "amount": charge.amount,
                         "is_cancelled": charge.is_cancelled} for charge in charges],
            "discounts": [{"id": item.id, "amount": item.amount,
                           "reason": item.reason, "actor_id": item.actor_id,
                           "actor_name": session.get(User, item.actor_id).full_name,
                           "original_discount_id": item.original_discount_id,
                           "created_at": item.created_at} for item in discounts],
            "active_charge_total": finance.active_charges,
            "settled_total": finance.active_settlements,
            "discount_total": finance.active_discounts,
            "outstanding_total": finance.debt,
        })
    data["registrations"] = history
    wallet = session.scalar(select(Wallet).where(Wallet.guest_id == guest.id))
    default_ceiling = session.scalar(select(Setting.value).where(
        Setting.key == "default_debt_ceiling"))
    ceiling = guest.debt_ceiling if guest.debt_ceiling is not None else default_ceiling
    total_debt = sum(item["outstanding_total"] for item in history
                     if item["status"] == "active")
    net_debt = total_debt - (wallet.balance if wallet else 0)
    data["finance_overview"] = {
        "total_debt": total_debt, "net_debt": net_debt, "debt_ceiling": ceiling,
        "over_ceiling": ceiling is not None and net_debt > ceiling,
    }
    data["wallet_transactions"] = [{
        "id": item.id, "type": item.type, "amount": item.amount,
        "registration_id": item.registration_id, "note": item.note,
        "reason": item.reason, "original_transaction_id": item.original_transaction_id,
        "actor_name": session.get(User, item.actor_id).full_name
        if item.actor_type == "user" and session.get(User, item.actor_id) else None,
        "created_at": item.created_at,
    } for item in session.scalars(select(WalletTransaction).where(
        WalletTransaction.wallet_id == wallet.id
    ).order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc()))] if wallet else []
    data["payments"] = [{"id": item.id, "amount": item.amount,
                          "status": item.status, "event_id": item.event_id,
                          "created_at": item.created_at}
                        for item in session.scalars(select(PaymentSubmission).where(
                            PaymentSubmission.guest_id == guest.id
                        ).order_by(PaymentSubmission.created_at.desc()))]
    return data


@router.get("/guests")
def list_guests(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    interest_tag_id: int | None = Query(default=None, ge=1),
    age_min: int | None = Query(default=None, ge=0, le=130),
    age_max: int | None = Query(default=None, ge=0, le=130),
    gender: str | None = Query(default=None, max_length=30),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(status_code=422, detail="invalid_age_range")
    search = q.strip()
    filters = []
    if interest_tag_id is not None:
        filters.append(Guest.id.in_(select(GuestInterestTag.guest_id).where(
            GuestInterestTag.tag_id == interest_tag_id)))
    if age_min is not None:
        filters.append(Guest.age >= age_min)
    if age_max is not None:
        filters.append(Guest.age <= age_max)
    if gender:
        filters.append(Guest.gender == gender)
    if search:
        normalized = None
        try:
            normalized = normalize_phone(search)
        except ValueError:
            pass
        phone_term = search.translate(str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
        )).replace(" ", "").replace("-", "")
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        escaped_phone = phone_term.replace("\\", "\\\\").replace("%", "\\%")
        escaped_phone = escaped_phone.replace("_", "\\_")
        filters.append(or_(Guest.phone == normalized if normalized else Guest.phone.ilike(
            f"%{escaped_phone}%", escape="\\"), Guest.first_name.ilike(pattern, escape="\\"),
            Guest.last_name.ilike(pattern, escape="\\"),
            (Guest.first_name + " " + Guest.last_name).ilike(pattern, escape="\\")))
    total = session.scalar(select(func.count()).select_from(Guest).where(*filters))
    guests = session.scalars(select(Guest).where(*filters).order_by(
        Guest.created_at.desc(), Guest.id.desc()
    ).limit(limit).offset(offset)).all()
    return {"items": [summary(session, guest) for guest in guests],
            "total": total, "limit": limit, "offset": offset}


@router.get("/guests/filter-options")
def guest_filter_options(
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    genders = session.scalars(select(Guest.gender).where(
        Guest.gender.is_not(None), Guest.gender != ""
    ).distinct().order_by(Guest.gender)).all()
    return {"genders": genders}


@router.get("/guests/{guest_id}")
def get_guest(
    guest_id: int, _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    guest = session.get(Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="guest_not_found")
    return profile(session, guest)


@router.post("/guests", status_code=201,
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def create_guest(
    body: GuestFields, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    try:
        phone = normalize_phone(body.phone)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_phone") from None
    try:
        with session.begin():
            guest = Guest(**{**body.model_dump(), "phone": phone})
            session.add(guest)
            session.flush()
            session.add(Wallet(guest_id=guest.id, balance=0))
            audit(session, actor, "guest.created", guest.id, after={"phone": phone})
            session.flush()
            result = profile(session, guest)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="guest_phone_exists") from None
    return result


@router.patch("/guests/{guest_id}",
              dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def update_guest(
    guest_id: int, body: GuestPatch, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(changes.get(key) is None for key in ("first_name", "last_name", "phone")
                          if key in changes):
        raise HTTPException(status_code=422, detail="invalid_guest_update")
    if "phone" in changes:
        try:
            changes["phone"] = normalize_phone(changes["phone"])
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_phone") from None
    try:
        with session.begin():
            guest = session.scalar(select(Guest).where(Guest.id == guest_id).with_for_update())
            if guest is None:
                raise HTTPException(status_code=404, detail="guest_not_found")
            before = {key: getattr(guest, key) for key in changes}
            for key, value in changes.items():
                setattr(guest, key, value)
            if "phone" in changes:
                account = session.scalar(select(GuestAccount).where(
                    GuestAccount.guest_id == guest_id).with_for_update())
                if account:
                    account.phone = changes["phone"]
            audit(session, actor, "guest.updated", guest_id, before, changes)
            session.flush()
            result = profile(session, guest)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="guest_phone_exists") from None
    return result


@router.delete("/guests/{guest_id}", status_code=204,
               dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def delete_guest(
    guest_id: int, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> None:
    with session.begin():
        guest = session.scalar(select(Guest).where(Guest.id == guest_id).with_for_update())
        if guest is None:
            raise HTTPException(status_code=404, detail="guest_not_found")
        wallet = session.scalar(select(Wallet).where(Wallet.guest_id == guest_id).with_for_update())
        if (
            session.scalar(select(GuestAccount.id).where(GuestAccount.guest_id == guest_id))
            or session.scalar(select(Registration.id).where(Registration.guest_id == guest_id))
            or session.scalar(select(PaymentSubmission.id).where(
                PaymentSubmission.guest_id == guest_id))
            or session.scalar(select(GuestNote.id).where(GuestNote.guest_id == guest_id))
            or (wallet and (wallet.balance != 0 or session.scalar(
                select(WalletTransaction.id).where(WalletTransaction.wallet_id == wallet.id))))
        ):
            raise HTTPException(status_code=409, detail="guest_has_history")
        session.execute(delete(GuestInterestTag).where(GuestInterestTag.guest_id == guest_id))
        if wallet:
            session.delete(wallet)
            session.flush()
        session.delete(guest)
        audit(session, actor, "guest.deleted", guest_id,
              before={"first_name": guest.first_name, "last_name": guest.last_name})


@router.get("/interest-tags")
def list_interest_tags(
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> list[dict]:
    return [{"id": tag.id, "name": tag.name} for tag in session.scalars(
        select(InterestTag).order_by(InterestTag.name))]


@router.post("/interest-tags", status_code=201,
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def create_interest_tag(
    body: TagBody, _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    try:
        with session.begin():
            tag = InterestTag(name=body.name)
            session.add(tag)
            session.flush()
            result = {"id": tag.id, "name": tag.name}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="tag_exists") from None
    return result


@router.put("/guests/{guest_id}/tags",
            dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def set_guest_tags(
    guest_id: int, body: TagsBody, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    ids = set(body.tag_ids)
    with session.begin():
        guest = session.scalar(select(Guest).where(Guest.id == guest_id).with_for_update())
        if guest is None:
            raise HTTPException(status_code=404, detail="guest_not_found")
        found = set(session.scalars(select(InterestTag.id).where(InterestTag.id.in_(ids))))
        if found != ids:
            raise HTTPException(status_code=422, detail="invalid_interest_tag")
        old = set(session.scalars(select(GuestInterestTag.tag_id).where(
            GuestInterestTag.guest_id == guest_id)))
        session.execute(delete(GuestInterestTag).where(GuestInterestTag.guest_id == guest_id,
                                                       GuestInterestTag.tag_id.not_in(ids)))
        session.add_all(GuestInterestTag(guest_id=guest_id, tag_id=tag_id)
                        for tag_id in sorted(ids - old))
        audit(session, actor, "guest.tags_updated", guest_id,
              before={"tag_ids": sorted(old)}, after={"tag_ids": sorted(ids)})
        session.flush()
        result = profile(session, guest)
    return result


@router.post("/guests/{guest_id}/notes", status_code=201,
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def add_guest_note(
    guest_id: int, body: NoteBody, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    with session.begin():
        guest = session.get(Guest, guest_id)
        if guest is None:
            raise HTTPException(status_code=404, detail="guest_not_found")
        note = GuestNote(guest_id=guest_id, type=body.type, text=body.text,
                         created_by_user_id=actor.id)
        session.add(note)
        session.flush()
        audit(session, actor, "guest.note_added", guest_id,
              after={"note_id": note.id, "type": note.type})
        result = {"id": note.id, "type": note.type, "text": note.text,
                  "created_at": note.created_at,
                  "created_by": session.get(User, actor.id).full_name}
    return result
