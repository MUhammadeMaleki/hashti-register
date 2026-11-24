"""Origin guard behavior for local development and production."""

import pytest
from fastapi import HTTPException, Request
from pydantic import SecretStr

from app.api.dependencies import require_browser_origin
from app.core.config import Settings


def check_origin(configured: str, environment: str, origin: str | None,
                 fetch_site: str = "same-origin") -> int:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:pass@localhost/hashti_test"),
        public_origin=configured,
        environment=environment,
    )
    headers = [(b"sec-fetch-site", fetch_site.encode())]
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    request = Request({"type": "http", "headers": headers})
    try:
        require_browser_origin(request, settings)
    except HTTPException as error:
        return error.status_code
    return 200


@pytest.mark.parametrize(
    ("configured", "origin", "expected"),
    [
        ("http://127.0.0.1:3000", "http://127.0.0.1:3000", 200),
        ("http://127.0.0.1:3000", "http://localhost:3000", 200),
        ("http://localhost:3000", "http://127.0.0.1:3000", 200),
        ("http://127.0.0.1:3000", "http://localhost:3001", 403),
        ("http://127.0.0.1:3000", "http://evil.example:3000", 403),
        ("http://127.0.0.1:3000", None, 403),
        ("http://example.test:3000", "http://localhost:3000", 403),
    ],
)
def test_development_origin(configured, origin, expected):
    assert check_origin(configured, "development", origin) == expected


def test_production_requires_exact_origin():
    assert check_origin("https://example.test", "production", "https://example.test") == 200
    assert check_origin("https://example.test", "production", "https://localhost") == 403


def test_fetch_site_still_rejects_cross_site():
    assert check_origin("http://127.0.0.1:3000", "development", "http://localhost:3000",
                        "cross-site") == 403
