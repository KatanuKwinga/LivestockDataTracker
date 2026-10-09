"""Tests for the password-reset flow: emails, single-use, expiry, tampering."""
import re
import time
from unittest import mock

from itsdangerous import timed

from app.extensions import mail
from app.models import User
from tests.conftest import login, register_farmer


def request_reset(client, email="jane@example.com"):
    return client.post("/auth/reset-password", data={"email": email}, follow_redirects=True)


def make_token(app):
    """Create a reset token directly (needs an app context for SECRET_KEY)."""
    with app.app_context():
        return User.query.one().get_reset_token()


def reset_link_from(message):
    """Pull the /auth/reset-password/<token> path out of the email text."""
    return re.search(r"http://localhost(/auth/reset-password/\S+)", message.body).group(1)


def test_known_email_receives_one_reset_email(client):
    register_farmer(client)

    # record_messages(): Flask-Mail collects emails here instead of sending them.
    with mail.record_messages() as outbox:
        response = request_reset(client, email=" JANE@example.com ")

    assert len(outbox) == 1
    assert outbox[0].recipients == ["jane@example.com"]
    assert b"If an account exists" in response.data


def test_unknown_email_gets_same_message_but_no_email(client):
    with mail.record_messages() as outbox:
        response = request_reset(client, email="nobody@example.com")

    assert outbox == []                                   # nothing sent
    assert b"If an account exists" in response.data       # but the same message


def test_reset_link_changes_the_password(client):
    register_farmer(client)
    with mail.record_messages() as outbox:
        request_reset(client)
    link = reset_link_from(outbox[0])

    response = client.post(link, data={"password": "brandnew123", "confirm_password": "brandnew123"})

    assert response.headers["Location"] == "/auth/login/farmer"
    assert b"Invalid email or password." in login(client, "farmer", password="password123").data
    assert login(client, "farmer", password="brandnew123").headers["Location"] == "/dashboard"


def test_reset_link_works_only_once(client):
    register_farmer(client)
    with mail.record_messages() as outbox:
        request_reset(client)
    link = reset_link_from(outbox[0])
    client.post(link, data={"password": "brandnew123", "confirm_password": "brandnew123"})

    response = client.get(link)   # the same link, a second time

    assert response.headers["Location"] == "/auth/reset-password"


def test_reset_link_expires_after_30_minutes(app, client):
    register_farmer(client)
    token = make_token(app)

    # mock.patch temporarily replaces itsdangerous's clock with one that is
    # 31 minutes ahead, instead of actually waiting half an hour.
    real_time = time.time
    with mock.patch.object(timed.time, "time", lambda: real_time() + 31 * 60):
        response = client.get(f"/auth/reset-password/{token}")

    assert response.headers["Location"] == "/auth/reset-password"


def test_tampered_reset_link_is_rejected(app, client):
    register_farmer(client)
    token = make_token(app)
    # Change the FIRST character of the signature (the part after the last
    # "."). The last character isn't reliable to change: base64 packs unused
    # padding bits into it, so some edits there don't change the signature.
    payload, signature = token.rsplit(".", 1)
    tampered = f"{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"

    assert client.get(f"/auth/reset-password/{tampered}").headers["Location"] == "/auth/reset-password"
    assert client.get("/auth/reset-password/not-a-token").headers["Location"] == "/auth/reset-password"


def test_new_password_must_follow_the_rules(app, client):
    register_farmer(client)
    token = make_token(app)

    response = client.post(f"/auth/reset-password/{token}",
                           data={"password": "short", "confirm_password": "short"})

    assert b"Use at least 8 characters." in response.data


def test_email_failure_does_not_crash_the_page(client):
    register_farmer(client)

    # Pretend Gmail is unreachable.
    with mock.patch("app.routes.auth.mail.send", side_effect=OSError("Gmail unreachable")):
        response = request_reset(client)

    assert response.status_code == 200
    assert b"If an account exists" in response.data