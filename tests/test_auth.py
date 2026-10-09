"""Tests for registration, login, protected pages and logout."""
from app.models import Farmer, User
from tests.conftest import login, register_farmer


# ---- Registration -----------------------------------------------------

def test_farmer_can_register(client):
    response = register_farmer(client, email=" Jane@Example.com ")

    # 302 = a redirect; here, to the farmer login page.
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/login/farmer"
    user = User.query.one()
    assert user.email == "jane@example.com"          # spaces and capitals tidied
    assert user.farmer is not None                   # a Farmer row was created too
    assert user.password_hash.startswith("$2b$")     # bcrypt's signature
    assert "password123" not in user.password_hash   # the real password is not stored


def test_duplicate_email_is_rejected_whatever_the_capitals(client):
    register_farmer(client, email="jane@example.com")
    response = register_farmer(client, email="JANE@example.com")

    assert b"An account with this email already exists." in response.data
    assert User.query.count() == 1


def test_passwords_must_match(client):
    response = client.post("/auth/register", data={
        "name": "Jane", "email": "jane@example.com",
        "password": "password123", "confirm_password": "different123",
    })
    assert b"match" in response.data
    assert User.query.count() == 0


def test_password_must_be_at_least_8_characters(client):
    response = register_farmer(client, password="short")
    assert b"Use at least 8 characters." in response.data
    assert Farmer.query.count() == 0


# ---- Login ------------------------------------------------------------

def test_farmer_can_log_in_and_see_dashboard(client):
    register_farmer(client)
    response = login(client, "farmer")

    assert response.headers["Location"] == "/dashboard"
    page = client.get("/dashboard").data
    assert b"Jane Farmer" in page
    assert b"overview of your livestock" in page


def test_wrong_password_and_unknown_email_give_the_same_message(client):
    register_farmer(client)

    wrong_password = login(client, "farmer", password="wrong-password")
    unknown_email = login(client, "farmer", email="nobody@example.com")

    # Identical messages: the form can't be used to discover accounts.
    for response in (wrong_password, unknown_email):
        assert b"Invalid email or password." in response.data


def test_wrong_door_hint_only_after_correct_password(client):
    register_farmer(client)

    # Right password, wrong door: moved to the farmer login, with the hint.
    response = client.post("/auth/login/worker", follow_redirects=True,
                           data={"email": "jane@example.com", "password": "password123"})
    assert response.request.path == "/auth/login/farmer"
    assert b"This is a farmer account" in response.data

    # Wrong password at the wrong door: only the general message.
    response = login(client, "worker", password="wrong-password")
    assert b"Invalid email or password." in response.data
    assert b"This is a farmer account" not in response.data


def test_unknown_role_in_login_address_is_not_found(client):
    assert client.get("/auth/login/admin").status_code == 404


# ---- Pages that need a login ------------------------------------------

def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/?next=")


def test_after_login_user_returns_to_the_page_they_wanted(client):
    register_farmer(client)
    response = client.post("/auth/login/farmer?next=/dashboard",
                           data={"email": "jane@example.com", "password": "password123"})
    assert response.headers["Location"] == "/dashboard"


def test_next_link_to_another_website_is_ignored(client):
    register_farmer(client)
    for evil in ("https://evil.example/", "//evil.example/"):
        response = client.post(f"/auth/login/farmer?next={evil}",
                               data={"email": "jane@example.com", "password": "password123"})
        assert response.headers["Location"] == "/dashboard"
        client.post("/auth/logout")


# ---- Logout -----------------------------------------------------------

def test_logout_only_accepts_post(client):
    register_farmer(client)
    login(client, "farmer")

    # 405 = "method not allowed": a plain link can't log anyone out.
    assert client.get("/auth/logout").status_code == 405

    response = client.post("/auth/logout")
    assert response.headers["Location"] == "/"
    assert client.get("/dashboard").status_code == 302   # logged out now