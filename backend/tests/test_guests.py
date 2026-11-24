from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, EventCharge, Guest, GuestAccount, Registration, Wallet
from app.seed import bootstrap_admin


def test_guest_list_filters_interest_age_and_gender(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        guests = []
        for index, (name, age, gender) in enumerate([
            ("مریم", 23, "زن"), ("سارا", 37, "زن"), ("علی", 28, "مرد")
        ]):
            response = client.post("/api/admin/guests", headers=write_headers(client), json={
                "first_name": name, "last_name": "نمونه", "phone": f"0912000010{index}",
                "age": age, "gender": gender,
            })
            assert response.status_code == 201
            guests.append(response.json()["id"])
        tag = client.post("/api/admin/interest-tags", headers=write_headers(client),
                          json={"name": "کتاب"}).json()
        for guest_id in guests[:2]:
            assert client.put(f"/api/admin/guests/{guest_id}/tags",
                              headers=write_headers(client),
                              json={"tag_ids": [tag["id"]]}).status_code == 200
        options = client.get("/api/admin/guests/filter-options")
        assert options.status_code == 200
        assert options.json()["genders"] == ["زن", "مرد"]
        filtered = client.get(f"/api/admin/guests?interest_tag_id={tag['id']}"
                              "&age_min=18&age_max=29&gender=زن")
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["id"] == guests[0]
        assert client.get("/api/admin/guests?age_min=40&age_max=20").status_code == 422
        assert client.get("/api/admin/guests?gender=مرد&limit=1&offset=0").json()[
            "total"] == 1


def test_contact_bank_and_history(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        assert client.get("/api/admin/guests").status_code == 401
        login(client, "boss", "boss-password-123")
        secretary = client.post("/api/admin/users", headers=write_headers(client), json={
            "username": "sec", "full_name": "دبیر", "password": "secretary-password",
        }).json()
        created = client.post("/api/admin/guests", headers=write_headers(client), json={
            "first_name": "مریم", "last_name": "احمدی", "phone": "۰۹۱۲ ۳۴۵ ۶۷۸۹",
            "age": 32, "education": "کارشناسی",
        })
        assert created.status_code == 201, created.text
        guest_id = created.json()["id"]
        assert created.json()["phone"] == "09123456789"
        assert created.json()["wallet_balance"] == 0
        assert created.json()["registrations"] == []
        assert created.json()["has_account"] is False
        with factory() as session:
            assert session.scalar(select(Wallet).where(Wallet.guest_id == guest_id)) is not None
            assert session.scalar(select(Registration.id).where(
                Registration.guest_id == guest_id)) is None
        assert client.post("/api/admin/guests", headers=write_headers(client), json={
            "first_name": "تکراری", "last_name": "فرد", "phone": "+989123456789",
        }).status_code == 409
        assert client.get("/api/admin/guests?q=۳۴۵").json()["total"] == 1
        assert client.get("/api/admin/guests?q=مریم").json()["total"] == 1
        assert client.get("/api/admin/guests?q=مریم احمدی").json()["total"] == 1

        tag = client.post("/api/admin/interest-tags", headers=write_headers(client),
                          json={"name": "موسیقی"})
        assert tag.status_code == 201
        tag_id = tag.json()["id"]
        assert client.put(f"/api/admin/guests/{guest_id}/tags", headers=write_headers(client),
                          json={"tag_ids": [999999]}).status_code == 422
        tagged = client.put(f"/api/admin/guests/{guest_id}/tags", headers=write_headers(client),
                            json={"tag_ids": [tag_id]})
        assert tagged.status_code == 200 and tagged.json()["tags"][0]["name"] == "موسیقی"
        note = client.post(f"/api/admin/guests/{guest_id}/notes", headers=write_headers(client),
                           json={"type": "financial", "text": "تماس گرفته شد"})
        assert note.status_code == 201
        assert note.json()["created_by"] == "مدیر"
        assert client.get(f"/api/admin/guests/{guest_id}").json()["notes"][0]["text"] == \
            "تماس گرفته شد"

        edited = client.patch(f"/api/admin/guests/{guest_id}",
                              headers=write_headers(client), json={
                                  "phone": "٠٩١٢٣٤٥٦٧٨٨", "internal_note": "دوست مجموعه",
                              })
        assert edited.status_code == 200, edited.text
        assert edited.json()["phone"] == "09123456788"
        assert client.get("/api/admin/guests?q=09123456788").json()["total"] == 1
        account = client.post("/api/auth/guest/register", headers={"Origin": ORIGIN}, json={
            "first_name": "مریم", "last_name": "احمدی", "phone": "09123456788",
            "password": "guest-password-123",
        })
        assert account.status_code == 201, account.text
        assert account.json()["guest_id"] == guest_id
        edited_again = client.patch(f"/api/admin/guests/{guest_id}",
                                    headers=write_headers(client), json={
                                        "phone": "۰۹۱۲۳۴۵۶۷۷۷",
                                    })
        assert edited_again.status_code == 200, edited_again.text
        with factory() as session:
            assert session.scalar(select(GuestAccount.phone).where(
                GuestAccount.guest_id == guest_id)) == "09123456777"

        with factory() as session:
            with session.begin():
                event = Event(event_number=19, title="شب شعر", event_date=date(2026, 1, 1),
                              registration_status="closed")
                session.add(event)
                session.flush()
                registration = Registration(event_id=event.id, guest_id=guest_id,
                                            source="admin", attendance="present")
                session.add(registration)
                session.flush()
                session.add(EventCharge(registration_id=registration.id, type="entry",
                                        description="ورودی", amount=50000,
                                        created_by=secretary["id"]))
        history = client.get(f"/api/admin/guests/{guest_id}").json()["registrations"]
        assert len(history) == 1
        assert history[0]["event"]["title"] == "شب شعر"
        assert history[0]["attendance"] == "present"
        assert history[0]["active_charge_total"] == 50000
        assert history[0]["outstanding_total"] == 50000
        assert client.delete(f"/api/admin/guests/{guest_id}",
                             headers=write_headers(client)).status_code == 409

        another = client.post("/api/admin/guests", headers=write_headers(client), json={
            "first_name": "علی", "last_name": "نو", "phone": "09123456780",
        })
        assert another.status_code == 201
        assert client.delete(f"/api/admin/guests/{another.json()['id']}",
                             headers=write_headers(client)).status_code == 204
        with factory() as session:
            assert session.get(Guest, another.json()["id"]) is None
