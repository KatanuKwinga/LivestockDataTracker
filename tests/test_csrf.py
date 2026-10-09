"""CSRF protection, tested with it switched ON (the other tests switch it off
for convenience)."""
import re

import pytest

from app import create_app
from app.extensions import db
from tests.conftest import TestConfig


class CsrfOnConfig(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def csrf_client():
    app = create_app(CsrfOnConfig)
    with app.app_context():
        db.create_all()
    yield app.test_client()
    with app.app_context():
        db.session.remove()
        db.drop_all()


def csrf_token_from(page):
    """Read the hidden token out of a page, as a real browser would send it."""
    return re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page.decode()).group(1)


FARMER = {"name": "Jane", "email": "jane@example.com", "phone": "",
          "password": "password123", "confirm_password": "password123"}


def test_form_without_csrf_token_is_rejected(csrf_client):
    response = csrf_client.post("/auth/register", data=FARMER)
    assert b"has been created" not in response.data


def test_form_with_forged_csrf_token_is_rejected(csrf_client):
    response = csrf_client.post("/auth/register", data={**FARMER, "csrf_token": "forged"})
    assert b"has been created" not in response.data


def test_form_with_real_csrf_token_is_accepted(csrf_client):
    token = csrf_token_from(csrf_client.get("/auth/register").data)
    response = csrf_client.post("/auth/register", data={**FARMER, "csrf_token": token})
    assert response.headers["Location"] == "/auth/login/farmer"


def test_logout_without_csrf_token_is_rejected(csrf_client):
    # Register and log in properly (with real tokens)...
    token = csrf_token_from(csrf_client.get("/auth/register").data)
    csrf_client.post("/auth/register", data={**FARMER, "csrf_token": token})
    token = csrf_token_from(csrf_client.get("/auth/login/farmer").data)
    csrf_client.post("/auth/login/farmer",
                     data={"email": "jane@example.com", "password": "password123", "csrf_token": token})

    # ...then a logout with NO token (what another website would try) is refused.
    assert csrf_client.post("/auth/logout").status_code == 400
    assert csrf_client.get("/dashboard").status_code == 200   # still logged in