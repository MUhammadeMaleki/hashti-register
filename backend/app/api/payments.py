"""Guest receipt submission and private, ownership-checked image delivery."""

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    require_active_admin,
    require_active_guest,
    require_browser_origin,
    require_csrf,
    require_guest_ownership,
)
from app.core.storage import uploads_root
from app.models import (
    AuditLog,
    Event,
    EventSecretary,
    Guest,
    GuestAccount,
    PaymentSubmission,
    Registration,
)
from app.services.auth import Actor
from app.services.finance import EffectResult, FinanceError, run_idempotent
from app.services.payment_review import review_payment

router = APIRouter(tags=["payments"])
RECEIPT_DIR = uploads_root() / "receipts"
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
MAX_RECEIPT_PIXELS = 20_000_000
RECEIPT_MIMES = {
    "image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP",
    "image/heic": "HEIF", "image/heif": "HEIF",
}
register_heif_opener()


def _magic_format(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1",
    }:
        return "HEIF"
    return None


async def _prepare_image(upload: UploadFile | None) -> tuple[bytes | None, bytes | None]:
    if upload is None:
        return None, None
    if upload.content_type not in RECEIPT_MIMES:
        raise HTTPException(422, "invalid_receipt_type")
    data = await upload.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise HTTPException(422, "invalid_receipt_size")
    expected = RECEIPT_MIMES[upload.content_type]
    if _magic_format(data) != expected:
        raise HTTPException(422, "invalid_receipt_image")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format != expected or source.width * source.height > MAX_RECEIPT_PIXELS:
                raise ValueError("invalid format or pixel count")
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            preview = BytesIO()
            image.save(preview, format="JPEG", quality=88)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "invalid_receipt_image") from None
    return data, preview.getvalue()


def _serialize(row: PaymentSubmission) -> dict:
    return {
        "id": row.id, "amount": row.amount, "tracking_code": row.tracking_code,
        "event_id": row.event_id, "status": row.status,
        "reject_reason": row.reject_reason, "has_image": row.display_receipt_path is not None,
        "created_at": row.created_at.isoformat(),
    }


class RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    reason: str | None = Field(default=None, max_length=2000)


def _admin_payment(session: Session, payment_id: int, actor: Actor) -> PaymentSubmission:
    row = session.get(PaymentSubmission, payment_id)
    if row is None or (actor.role != "super_admin" and (
        row.event_id is None or session.scalar(select(EventSecretary.user_id).where(
            EventSecretary.event_id == row.event_id,
            EventSecretary.user_id == actor.id,
        )) is None
    )):
        raise HTTPException(404, "payment_not_found")
    return row


def _admin_detail(session: Session, row: PaymentSubmission) -> dict:
    guest = session.get(Guest, row.guest_id)
    event = session.get(Event, row.event_id) if row.event_id is not None else None
    return {**_serialize(row), "guest_id": row.guest_id,
            "guest_name": f"{guest.first_name} {guest.last_name}",
            "event_title": event.title if event else None,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}


async def _submit(
    request: Request, session: Session, actor: Actor, *, event_id: int | None,
    amount: int, tracking_code: str | None, receipt: UploadFile | None, key: str,
) -> dict:
    form = await request.form()
    if "event_id" in form or "guest_id" in form:
        raise HTTPException(422, "invalid_payment_fields")
    code = tracking_code.strip() if tracking_code else None
    code = code or None
    if amount <= 0 or (code is not None and len(code) > 200):
        raise HTTPException(422, "invalid_amount_or_tracking_code")
    original, display = await _prepare_image(receipt)
    if code is None and original is None:
        raise HTTPException(422, "payment_evidence_required")
    token = uuid4().hex
    original_name = f"{token}.original" if original is not None else None
    display_name = f"{token}.jpg" if display is not None else None
    unique_key = hashlib.sha256(f"{actor.id}:{key}".encode()).hexdigest()
    payload = {"event_id": event_id, "amount": amount, "tracking_code": code,
               "image_sha256": hashlib.sha256(original).hexdigest() if original else None}
    written: list[Path] = []

    def effect(db: Session) -> EffectResult:
        account = db.get(GuestAccount, actor.id)
        if account is None:
            raise FinanceError("forbidden", 403)
        if event_id is not None:
            event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
            if event is None:
                raise FinanceError("event_not_found", 404)
            if event.is_cancelled:
                raise FinanceError("event_cancelled")
            registration = db.scalar(select(Registration).where(
                Registration.event_id == event_id,
                Registration.guest_id == account.guest_id,
            ).with_for_update())
            if registration is None or registration.status != "active":
                raise FinanceError("active_registration_required", 403)
        if original is not None and display is not None:
            RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
            for name, content in ((original_name, original), (display_name, display)):
                path = RECEIPT_DIR / name
                written.append(path)
                path.write_bytes(content)
        row = PaymentSubmission(
            guest_id=account.guest_id, event_id=event_id, amount=amount,
            tracking_code=code, original_receipt_path=original_name,
            display_receipt_path=display_name, idempotency_key=unique_key,
        )
        db.add(row)
        db.flush()
        db.add(AuditLog(actor_type="guest", actor_id=actor.id,
                        action="payment.submit", entity_type="payment_submission",
                        entity_id=row.id, request_id=key,
                        after_json={"amount": amount, "event_id": event_id,
                                    "has_image": display is not None}))
        return EffectResult(201, _serialize(row), "payment_submission", row.id)

    session.rollback()
    try:
        result = run_idempotent(session, actor_type="guest", actor_id=actor.id,
                                operation="payment.submit", key=key, payload=payload,
                                effect=effect)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return result.body


@router.post("/api/me/payments", status_code=201,
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
async def submit_independent(
    request: Request, amount: int = Form(...), tracking_code: str | None = Form(None),
    receipt: UploadFile | None = File(None),
    key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> dict:
    try:
        return await _submit(request, session, actor, event_id=None, amount=amount,
                             tracking_code=tracking_code, receipt=receipt, key=key)
    except FinanceError as error:
        raise HTTPException(error.status, error.code) from None


@router.post("/api/me/events/{event_id}/payments", status_code=201,
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
async def submit_event(
    event_id: int, request: Request, amount: int = Form(...),
    tracking_code: str | None = Form(None), receipt: UploadFile | None = File(None),
    key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> dict:
    try:
        return await _submit(request, session, actor, event_id=event_id, amount=amount,
                             tracking_code=tracking_code, receipt=receipt, key=key)
    except FinanceError as error:
        raise HTTPException(error.status, error.code) from None


@router.get("/api/me/payments")
def list_mine(actor: Actor = Depends(require_active_guest),
              session: Session = Depends(get_db)) -> list[dict]:
    guest_id = session.get(GuestAccount, actor.id).guest_id
    rows = session.scalars(select(PaymentSubmission).where(
        PaymentSubmission.guest_id == guest_id,
    ).order_by(PaymentSubmission.id.desc())).all()
    return [_serialize(row) for row in rows]


def _image_response(row: PaymentSubmission) -> Response:
    name = row.display_receipt_path
    if not name or Path(name).name != name:
        raise HTTPException(404, "receipt_not_found")
    try:
        content = (RECEIPT_DIR / name).read_bytes()
    except OSError:
        raise HTTPException(404, "receipt_not_found") from None
    return Response(content, media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})


@router.get("/api/me/payments/{payment_id}/receipt")
def my_receipt(payment_id: int, actor: Actor = Depends(require_active_guest),
               session: Session = Depends(get_db)) -> Response:
    require_guest_ownership(session, actor=actor, resource_type="payment",
                            resource_id=payment_id)
    return _image_response(session.get(PaymentSubmission, payment_id))


@router.get("/api/admin/payments/{payment_id}/receipt")
def admin_receipt(payment_id: int, actor: Actor = Depends(require_active_admin),
                  session: Session = Depends(get_db)) -> Response:
    return _image_response(_admin_payment(session, payment_id, actor))


@router.get("/api/admin/payments")
def admin_payments(
    status: Literal["pending", "approved", "rejected"] | None = None,
    limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    filters = []
    if status is not None:
        filters.append(PaymentSubmission.status == status)
    if actor.role != "super_admin":
        assigned = select(EventSecretary.event_id).where(EventSecretary.user_id == actor.id)
        filters.append(PaymentSubmission.event_id.in_(assigned))
    total = session.scalar(select(func.count()).select_from(PaymentSubmission).where(*filters)) or 0
    rows = session.scalars(select(PaymentSubmission).where(*filters).order_by(
        PaymentSubmission.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [_admin_detail(session, row) for row in rows],
            "total": total, "limit": limit, "offset": offset}


@router.get("/api/admin/payments/{payment_id}")
def admin_payment_detail(
    payment_id: int, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> dict:
    return _admin_detail(session, _admin_payment(session, payment_id, actor))


def _review_result(session: Session, call) -> dict:
    session.rollback()
    try:
        return call().body
    except FinanceError as error:
        raise HTTPException(error.status, error.code) from None


@router.post("/api/admin/payments/{payment_id}/approve",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def approve_payment(
    payment_id: int, key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _admin_payment(session, payment_id, actor)
    return _review_result(session, lambda: review_payment(
        session, payment_id=payment_id, approve=True, reason=None, actor=actor, key=key))


@router.post("/api/admin/payments/{payment_id}/reject",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def reject_payment(
    payment_id: int, body: RejectBody | None = None,
    key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _admin_payment(session, payment_id, actor)
    return _review_result(session, lambda: review_payment(
        session, payment_id=payment_id, approve=False, reason=body.reason if body else None,
        actor=actor, key=key))
