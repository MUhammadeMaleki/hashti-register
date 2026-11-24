"""Explicit bootstrap command: python -m app.seed [--demo]."""

import argparse
from getpass import getpass

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.models import (
    Event,
    EventSecretary,
    Guest,
    InterestTag,
    Location,
    Registration,
    User,
    Wallet,
)


def bootstrap_admin(session: Session, *, username: str, full_name: str, password: str) -> bool:
    if len(password) < 12:
        raise ValueError("Bootstrap password must contain at least 12 characters")
    with session.begin():
        if session.scalar(select(User.id).where(User.username == username)) is not None:
            return False
        session.add(
            User(
                username=username,
                full_name=full_name,
                role="super_admin",
                password_hash=PasswordHasher().hash(password),
            )
        )
    return True


def seed_demo(session: Session, *, admin_id: int) -> None:
    """Idempotent demo data; call only against a development database."""
    with session.begin():
        if session.scalar(select(Event.id).where(Event.event_number == 1)) is not None:
            return
        location = Location(title="مکان نمونه", address="آدرس نمونه")
        tag = InterestTag(name="رویداد نمونه")
        session.add_all([location, tag])
        session.flush()
        event = Event(
            event_number=1,
            title="گردهمایی نمونه",
            location_id=location.id,
            registration_status="closed",
            entry_fee=0,
        )
        session.add(event)
        session.flush()
        session.add(EventSecretary(event_id=event.id, user_id=admin_id))
        guest = Guest(first_name="مهمان", last_name="نمونه", phone="09000000000")
        session.add(guest)
        session.flush()
        session.add(Wallet(guest_id=guest.id, balance=0))
        session.add(
            Registration(
                event_id=event.id,
                guest_id=guest.id,
                status="active",
                attendance="pending",
                source="admin",
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Hashti super admin and optional demo")
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--admin-name", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.demo and settings.environment != "development":
        parser.error("Demo seed is limited to the development environment")
    username = args.admin_username.strip()
    full_name = args.admin_name.strip()
    if not username or not full_name:
        parser.error("Admin username and name are required")

    engine = build_engine(settings.database_url.get_secret_value())
    try:
        factory = build_session_factory(engine)
        with factory() as session:
            existing_id = session.scalar(select(User.id).where(User.username == username))
            session.rollback()
            if existing_id is None:
                password = getpass("Initial super admin password: ")
                if password != getpass("Repeat password: "):
                    parser.error("Passwords do not match")
                bootstrap_admin(session, username=username, full_name=full_name, password=password)
            admin_id = session.scalar(select(User.id).where(User.username == username))
            admin_role = session.scalar(select(User.role).where(User.id == admin_id))
            session.rollback()
            if admin_role != "super_admin":
                parser.error("The username belongs to a non-super-admin account")
            if args.demo:
                seed_demo(session, admin_id=admin_id)
            print("Bootstrap complete. No password was printed or stored in plain text.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
