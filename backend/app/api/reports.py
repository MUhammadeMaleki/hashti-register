"""Read-only management reports; available to every active secretary."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_active_admin
from app.models import Event, InterestTag
from app.services.auth import Actor
from app.services.report_exports import workbook_bytes
from app.services.reports import (
    charts,
    dashboard,
    event_report,
    financial_guests,
    guest_report,
    registration_rows,
)

router = APIRouter(prefix="/api/admin/reports", tags=["reports"])
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _period(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(422, "invalid_date_range")


def _download(data: bytes, name: str) -> Response:
    return Response(data, media_type=XLSX_TYPE, headers={
        "Content-Disposition": f'attachment; filename="{name}.xlsx"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


def _finance_items(session: Session, search: str, debtors_only: bool) -> list[dict]:
    query = search.strip().casefold()
    items = [row for row in financial_guests(session, registration_rows(session))
             if (not debtors_only or row["net_debt"] > 0) and
             query in f'{row["name"]} {row["phone"]}'.casefold()]
    items.sort(key=lambda row: (-row["net_debt"], row["guest_id"]))
    return items


@router.get("/options")
def options(
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    events = session.scalars(select(Event).order_by(Event.event_number.desc())).all()
    tags = session.scalars(select(InterestTag).order_by(InterestTag.name)).all()
    return {"events": [{"id": row.id, "event_number": row.event_number,
                        "title": row.title} for row in events],
            "interests": [{"id": row.id, "name": row.name} for row in tags]}


@router.get("/dashboard")
def dashboard_report(
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    return dashboard(session, registration_rows(session))


@router.get("/events/{event_id}")
def event_finance_report(
    event_id: int, q: str = Query(default="", max_length=200),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "event_not_found")
    return event_report(registration_rows(session), event, q.strip())


@router.get("/finance")
def finance_report(
    q: str = Query(default="", max_length=200), debtors_only: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    items = _finance_items(session, q, debtors_only)
    return {"items": items[offset:offset + limit], "total": len(items),
            "limit": limit, "offset": offset}


@router.get("/export/finance")
def export_finance(
    q: str = Query(default="", max_length=200), debtors_only: bool = False,
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> Response:
    items = _finance_items(session, q, debtors_only)
    columns = [("مهمان", "name"), ("موبایل", "phone"), ("موجودی (تومان)", "wallet_balance"),
               ("بدهی (تومان)", "debt"), ("خالص بدهی (تومان)", "net_debt"),
               ("رویداد تسویه‌نشده", "unsettled_events"),
               ("آخرین تراکنش", "last_transaction_at")]
    return _download(workbook_bytes("وضعیت مالی مهمان‌ها", columns, items,
                                    total_keys=("wallet_balance", "debt", "net_debt")),
                     "hashti-finance")


@router.get("/export/events/{event_id}")
def export_event(
    event_id: int, q: str = Query(default="", max_length=200),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> Response:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "event_not_found")
    report = event_report(registration_rows(session), event, q.strip())
    columns = [("مهمان بدهکار", "name"), ("موبایل", "phone"),
               ("کل هزینه (تومان)", "charges"), ("تسویه‌شده (تومان)", "settled"),
               ("مانده (تومان)", "debt")]
    return _download(workbook_bytes(
        f'گزارش بدهکاران هشتی {event.event_number} - {event.title}',
        columns, report["debtors"], total_keys=("charges", "settled", "debt")),
        f"hashti-event-{event.event_number}")


@router.get("/guests")
def guests_report(
    date_from: date | None = None, date_to: date | None = None,
    event_id: int | None = Query(default=None, gt=0),
    min_attendance: int = Query(default=0, ge=0),
    min_absence: int = Query(default=0, ge=0),
    interest_tag_id: int | None = Query(default=None, gt=0),
    guest_kind: Literal["new", "returning"] | None = None,
    attendance: Literal["pending", "present", "absent_kept", "absent_forfeited"] | None = None,
    financial_status: Literal["debtor", "credit", "balanced"] | None = None,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _period(date_from, date_to)
    return guest_report(
        session, registration_rows(session), date_from=date_from, date_to=date_to,
        event_id=event_id, min_attendance=min_attendance, min_absence=min_absence,
        interest_tag_id=interest_tag_id, guest_kind=guest_kind,
        attendance=attendance, financial_status=financial_status,
        search=q.strip(), limit=limit, offset=offset,
    )


@router.get("/export/guests")
def export_guests(
    date_from: date | None = None, date_to: date | None = None,
    event_id: int | None = Query(default=None, gt=0),
    min_attendance: int = Query(default=0, ge=0),
    min_absence: int = Query(default=0, ge=0),
    interest_tag_id: int | None = Query(default=None, gt=0),
    guest_kind: Literal["new", "returning"] | None = None,
    attendance: Literal["pending", "present", "absent_kept", "absent_forfeited"] | None = None,
    financial_status: Literal["debtor", "credit", "balanced"] | None = None,
    q: str = Query(default="", max_length=200),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> Response:
    _period(date_from, date_to)
    report = guest_report(
        session, registration_rows(session), date_from=date_from, date_to=date_to,
        event_id=event_id, min_attendance=min_attendance, min_absence=min_absence,
        interest_tag_id=interest_tag_id, guest_kind=guest_kind,
        attendance=attendance, financial_status=financial_status,
        search=q.strip(), limit=2**31 - 1,
    )
    columns = [("مهمان", "name"), ("موبایل", "phone"),
               ("حضور", "attendance_count"), ("غیبت", "absence_count"),
               ("نوع", "guest_kind"), ("بدهی خالص (تومان)", "net_debt")]
    items = [{**row, "guest_kind": "بازگشتی" if row["guest_kind"] == "returning" else "جدید"}
             for row in report["items"]]
    return _download(workbook_bytes("گزارش مهمان‌ها", columns, items,
                                    total_keys=("net_debt",)), "hashti-guests")


@router.get("/charts")
def chart_report(
    date_from: date | None = None, date_to: date | None = None,
    event_id: int | None = Query(default=None, gt=0),
    min_attendance: int = Query(default=0, ge=0),
    min_absence: int = Query(default=0, ge=0),
    interest_tag_id: int | None = Query(default=None, gt=0),
    guest_kind: Literal["new", "returning"] | None = None,
    attendance: Literal["pending", "present", "absent_kept", "absent_forfeited"] | None = None,
    financial_status: Literal["debtor", "credit", "balanced"] | None = None,
    q: str = Query(default="", max_length=200),
    _: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _period(date_from, date_to)
    rows = registration_rows(session)
    cohort = guest_report(
        session, rows, date_from=date_from, date_to=date_to, event_id=event_id,
        min_attendance=min_attendance, min_absence=min_absence,
        interest_tag_id=interest_tag_id, guest_kind=guest_kind,
        attendance=attendance, financial_status=financial_status,
        search=q.strip(), limit=2**31 - 1,
    )
    return charts(session, rows, date_from, date_to,
                  guest_ids={row["guest_id"] for row in cohort["items"]}, event_id=event_id)
