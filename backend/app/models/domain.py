"""Hashti v1 schema. Monetary amounts are integer tomans; timestamps are UTC aware."""

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username"),
        CheckConstraint("role IN ('super_admin', 'secretary')", name="role_valid"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    failed_login_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Guest(Timestamped, Base):
    __tablename__ = "guests"
    __table_args__ = (
        UniqueConstraint("phone"),
        CheckConstraint("phone ~ '^09[0-9]{9}$'", name="phone_normalized"),
        CheckConstraint(
            "debt_ceiling IS NULL OR debt_ceiling >= 0", name="debt_ceiling_nonnegative"
        ),
        CheckConstraint("age IS NULL OR age >= 0", name="age_nonnegative"),
        Index("ix_guests_last_first", "last_name", "first_name"),
        Index("ix_guests_first_last", "first_name", "last_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(11), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(30))
    education: Mapped[str | None] = mapped_column(String(200))
    internal_note: Mapped[str | None] = mapped_column(Text)
    debt_ceiling: Mapped[int | None] = mapped_column(BigInteger)
    wallet: Mapped["Wallet"] = relationship(back_populates="guest", uselist=False)


class GuestAccount(Timestamped, Base):
    __tablename__ = "guest_accounts"
    __table_args__ = (
        UniqueConstraint("guest_id"),
        UniqueConstraint("phone"),
        CheckConstraint("phone ~ '^09[0-9]{9}$'", name="phone_normalized"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guest_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False
    )
    phone: Mapped[str] = mapped_column(String(11), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    temp_password_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    failed_login_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("refresh_token_hash"),
        CheckConstraint("actor_type IN ('user', 'guest')", name="actor_type_valid"),
        Index("ix_auth_sessions_actor", "actor_type", "actor_id"),
        Index(
            "ix_auth_sessions_active_expiry",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth_sessions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(45))


class InterestTag(Base):
    __tablename__ = "interest_tags"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class GuestInterestTag(Base):
    __tablename__ = "guest_interest_tags"
    __table_args__ = (PrimaryKeyConstraint("guest_id", "tag_id"),)
    guest_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guests.id", ondelete="RESTRICT"))
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interest_tags.id", ondelete="RESTRICT")
    )


class GuestNote(Base):
    __tablename__ = "guest_notes"
    __table_args__ = (CheckConstraint("type IN ('general', 'financial')", name="type_valid"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guest_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Location(Timestamped, Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    map_link: Mapped[str | None] = mapped_column(Text)


class Event(Timestamped, Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("uq_events_active_event_number", "event_number", unique=True,
              postgresql_where=text("number_released = false")),
        CheckConstraint("event_number > 0", name="event_number_positive"),
        CheckConstraint("entry_fee >= 0", name="entry_fee_nonnegative"),
        CheckConstraint("capacity IS NULL OR capacity >= 0", name="capacity_nonnegative"),
        CheckConstraint(
            "location_mode IN ('exact', 'approximate', 'tba')", name="location_mode_valid"
        ),
        CheckConstraint(
            "time_mode IN ('exact', 'approximate', 'tba')", name="time_mode_valid"
        ),
        CheckConstraint(
            "registration_status IN ('open', 'closed')", name="registration_status_valid"
        ),
        Index("ix_events_event_date", "event_date"),
        Index("ix_events_registration_status", "registration_status"),
        Index("ix_events_cancelled_date", "is_cancelled", "event_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    number_released: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    poster_path: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time)
    time_text: Mapped[str | None] = mapped_column(String(200))
    time_mode: Mapped[str] = mapped_column(
        String(20), server_default=text("'tba'"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("locations.id", ondelete="RESTRICT")
    )
    location_mode: Mapped[str] = mapped_column(
        String(20), server_default=text("'tba'"), nullable=False
    )
    location_text: Mapped[str | None] = mapped_column(Text)
    hosts: Mapped[str | None] = mapped_column(Text)
    entry_fee: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    public_note: Mapped[str | None] = mapped_column(Text)
    registration_status: Mapped[str] = mapped_column(
        String(10), server_default=text("'closed'"), nullable=False
    )
    is_cancelled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    is_historical_import: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )


class EventSecretary(Base):
    __tablename__ = "event_secretaries"
    __table_args__ = (PrimaryKeyConstraint("event_id", "user_id"),)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="RESTRICT"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))


class Registration(Timestamped, Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("guest_id", "event_id"),
        CheckConstraint("status IN ('active', 'cancelled')", name="status_valid"),
        CheckConstraint(
            "attendance IN ('pending', 'present', 'absent_kept', 'absent_forfeited')",
            name="attendance_valid",
        ),
        CheckConstraint("source IN ('public', 'admin')", name="source_valid"),
        Index("ix_registrations_event_status", "event_id", "status"),
        Index("ix_registrations_guest_status", "guest_id", "status"),
        Index("ix_registrations_event_attendance", "event_id", "attendance"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    guest_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(10), server_default=text("'active'"), nullable=False)
    attendance: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)


class EventCharge(Timestamped, Base):
    __tablename__ = "event_charges"
    __table_args__ = (
        CheckConstraint("type IN ('entry', 'order')", name="type_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_event_charges_registration_cancelled", "registration_id", "is_cancelled"),
        Index(
            "ix_event_charges_registration_type_cancelled",
            "registration_id",
            "type",
            "is_cancelled",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class Wallet(Timestamped, Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("guest_id"),
        CheckConstraint("balance >= 0", name="balance_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guest_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False
    )
    balance: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    guest: Mapped[Guest] = relationship(back_populates="wallet")


class PaymentSubmission(Timestamped, Base):
    __tablename__ = "payment_submissions"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status_valid"),
        CheckConstraint(
            "NULLIF(BTRIM(tracking_code), '') IS NOT NULL OR original_receipt_path IS NOT NULL",
            name="evidence_required",
        ),
        CheckConstraint(
            "(original_receipt_path IS NULL) = (display_receipt_path IS NULL)",
            name="image_paths_together",
        ),
        CheckConstraint(
            "(status = 'pending' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR "
            "(status <> 'pending' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="review_fields_valid",
        ),
        Index("ix_payment_submissions_status_event", "status", "event_id"),
        Index("ix_payment_submissions_guest_created", "guest_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guest_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tracking_code: Mapped[str | None] = mapped_column(String(200))
    original_receipt_path: Mapped[str | None] = mapped_column(Text)
    display_receipt_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(10), server_default=text("'pending'"), nullable=False
    )
    reject_reason: Mapped[str | None] = mapped_column(Text)
    event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("payment_submission_id"),
        CheckConstraint(
            "(type = 'topup' AND amount > 0 AND payment_submission_id IS NOT NULL "
            "AND registration_id IS NULL AND original_transaction_id IS NULL) OR "
            "(type = 'settlement' AND amount < 0 AND payment_submission_id IS NULL "
            "AND registration_id IS NOT NULL AND original_transaction_id IS NULL) OR "
            "(type = 'refund' AND amount > 0 AND payment_submission_id IS NULL "
            "AND registration_id IS NOT NULL AND original_transaction_id IS NOT NULL) OR "
            "(type = 'manual_adjust' AND amount <> 0 AND payment_submission_id IS NULL "
            "AND registration_id IS NULL AND original_transaction_id IS NULL "
            "AND NULLIF(BTRIM(note), '') IS NOT NULL)",
            name="type_fields_valid",
        ),
        CheckConstraint(
            "original_transaction_id IS NULL OR original_transaction_id <> id",
            name="not_self_refund",
        ),
        CheckConstraint("actor_type IN ('user', 'guest', 'system')", name="actor_type_valid"),
        Index("ix_wallet_transactions_wallet_created", "wallet_id", "created_at", "id"),
        Index("ix_wallet_transactions_registration_type", "registration_id", "type"),
        Index("ix_wallet_transactions_original", "original_transaction_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    registration_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("registrations.id", ondelete="RESTRICT")
    )
    payment_submission_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("payment_submissions.id", ondelete="RESTRICT")
    )
    original_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("wallet_transactions.id", ondelete="RESTRICT")
    )
    note: Mapped[str] = mapped_column(Text, server_default=text("''"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IdempotencyRequest(Base):
    __tablename__ = "idempotency_requests"
    __table_args__ = (UniqueConstraint("actor_type", "actor_id", "operation", "key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_json: Mapped[dict | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'guest', 'system')", name="actor_type_valid"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_actor", "actor_type", "actor_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100))
    before_json: Mapped[dict | None] = mapped_column(JSONB)
    after_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint(
            "key <> 'default_debt_ceiling' OR (jsonb_typeof(value) = 'number' "
            "AND (value #>> '{}')::numeric >= 0)",
            name="default_debt_ceiling_nonnegative",
        ),
    )
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | str | int] = mapped_column(JSONB, nullable=False)
