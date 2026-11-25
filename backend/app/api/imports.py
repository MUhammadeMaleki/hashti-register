"""Preview and confirm Excel imports into the contact bank."""

import time

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    get_settings,
    require_active_admin,
    require_browser_origin,
    require_csrf,
    require_super_admin,
)
from app.core.config import Settings
from app.models import AuditLog, Event, Guest, Location, Wallet
from app.services.auth import Actor
from app.services.event_import import parse_workbook as parse_events
from app.services.event_import import template_bytes as event_template_bytes
from app.services.event_numbers import lock_numbers
from app.services.guest_import import parse_workbook, template_bytes
from app.services.import_files import preview_token, read_xlsx, verify_preview_token

router = APIRouter(prefix="/api/admin/import", tags=["import"])
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template")
def template(_: Actor = Depends(require_active_admin)) -> Response:
    return Response(template_bytes(), media_type=XLSX_TYPE, headers={
        "Content-Disposition": 'attachment; filename="hashti-guests-template.xlsx"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/preview", dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
async def preview(
    file: UploadFile = File(...), actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> dict:
    content = await read_xlsx(file)
    candidates, errors, total = parse_workbook(content)
    phones = [item["phone"] for item in candidates]
    existing = set(session.scalars(select(Guest.phone).where(Guest.phone.in_(phones))))
    for item in candidates:
        if item["phone"] in existing:
            errors.append({"row": item["row"], "reason": "شماره موبایل از قبل ثبت شده است"})
    valid = [item for item in candidates if item["phone"] not in existing]
    expiry = int(time.time()) + 30 * 60
    return {"total": total, "valid_count": len(valid), "error_count": len(errors),
            "preview_rows": valid[:100], "errors": sorted(errors, key=lambda item: item["row"]),
            "preview_token": preview_token(content, actor, settings, expiry)}


@router.post("/confirm", dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
async def confirm(
    file: UploadFile = File(...), preview_token: str = Form(...),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    content = await read_xlsx(file)
    verify_preview_token(preview_token, content, actor, settings)
    candidates, errors, total = parse_workbook(content)
    imported = 0
    with session.begin():
        for item in candidates:
            if session.scalar(select(Guest.id).where(Guest.phone == item["phone"])):
                errors.append({"row": item["row"], "reason": "شماره موبایل از قبل ثبت شده است"})
                continue
            try:
                with session.begin_nested():
                    guest = Guest(**{key: value for key, value in item.items() if key != "row"})
                    session.add(guest)
                    session.flush()
                    session.add(Wallet(guest_id=guest.id, balance=0))
                    session.add(AuditLog(actor_type="user", actor_id=actor.id,
                                         action="guest.imported", entity_type="guest",
                                         entity_id=guest.id,
                                         after_json={"phone": guest.phone,
                                                     "source_row": item["row"]}))
                    session.flush()
                imported += 1
            except IntegrityError:
                errors.append({"row": item["row"], "reason": "شماره موبایل از قبل ثبت شده است"})
    return {"total": total, "imported_count": imported, "error_count": len(errors),
            "errors": sorted(errors, key=lambda item: item["row"])}


@router.get("/events/template")
def event_template(_: Actor = Depends(require_super_admin)) -> Response:
    return Response(event_template_bytes(), media_type=XLSX_TYPE, headers={
        "Content-Disposition": 'attachment; filename="hashti-events-template.xlsx"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/events/preview",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
async def event_preview(
    file: UploadFile = File(...), actor: Actor = Depends(require_super_admin),
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> dict:
    content = await read_xlsx(file)
    candidates, errors, total = parse_events(content)
    numbers = [item["event_number"] for item in candidates]
    existing = set(session.scalars(select(Event.event_number).where(
        Event.event_number.in_(numbers), Event.number_released.is_(False))))
    for item in candidates:
        if item["event_number"] in existing:
            errors.append({"row": item["row"], "reason": "شماره رویداد از قبل ثبت شده است"})
    valid = [item for item in candidates if item["event_number"] not in existing]
    expiry = int(time.time()) + 30 * 60
    return {"total": total, "valid_count": len(valid), "error_count": len(errors),
            "preview_rows": valid[:100], "errors": sorted(errors, key=lambda item: item["row"]),
            "preview_token": preview_token(content, actor, settings, expiry)}


@router.post("/events/confirm",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
async def event_confirm(
    file: UploadFile = File(...), preview_token: str = Form(...),
    actor: Actor = Depends(require_super_admin), session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    content = await read_xlsx(file)
    verify_preview_token(preview_token, content, actor, settings)
    candidates, errors, total = parse_events(content)
    imported = 0
    with session.begin():
        lock_numbers(session)
        locations = {(row.title.casefold(), row.address.casefold()): row.id
                     for row in session.scalars(select(Location))}
        for item in candidates:
            if session.scalar(select(Event.id).where(
                Event.event_number == item["event_number"], Event.number_released.is_(False))):
                errors.append({"row": item["row"], "reason": "شماره رویداد از قبل ثبت شده است"})
                continue
            name, address = item["location_name"], item["location_address"]
            location_key = (name.casefold(), address.casefold()) if name and address else None
            location_id = locations.get(location_key) if location_key else None
            created_location_id = None
            try:
                with session.begin_nested():
                    if location_key and location_id is None:
                        location = Location(title=name, address=address)
                        session.add(location)
                        session.flush()
                        location_id = location.id
                        created_location_id = location.id
                        session.add(AuditLog(actor_type="user", actor_id=actor.id,
                                             action="location.imported", entity_type="location",
                                             entity_id=location.id,
                                             after_json={"title": name, "address": address}))
                    exact = bool(location_id and item["event_date"] and item["start_time"])
                    place = " - ".join(part for part in (name, address) if part) or None
                    mode = "exact" if exact else "approximate" if place else "tba"
                    time_mode = ("exact" if item["event_date"] and item["start_time"]
                                 else "approximate" if item["start_time"] else "tba")
                    event = Event(
                        event_number=item["event_number"], title=item["title"],
                        event_date=item["event_date"], start_time=item["start_time"],
                        description=item["description"], location_id=location_id,
                        time_mode=time_mode,
                        location_mode=mode, location_text=None if exact else place,
                        time_text=(item["start_time"].strftime("%H:%M")
                                   if time_mode == "approximate" else None),
                        entry_fee=item["entry_fee"], public_note=item["public_note"],
                        registration_status=item["registration_status"],
                        is_historical_import=True,
                    )
                    session.add(event)
                    session.flush()
                    session.add(AuditLog(actor_type="user", actor_id=actor.id,
                                         action="event.imported", entity_type="event",
                                         entity_id=event.id,
                                         after_json={"event_number": event.event_number,
                                                     "source_row": item["row"]}))
                    session.flush()
                if location_key and created_location_id:
                    locations[location_key] = created_location_id
                imported += 1
            except IntegrityError:
                errors.append({"row": item["row"], "reason": "شماره رویداد از قبل ثبت شده است"})
    return {"total": total, "imported_count": imported, "error_count": len(errors),
            "errors": sorted(errors, key=lambda item: item["row"])}
