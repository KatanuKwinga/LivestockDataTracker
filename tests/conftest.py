"""Shared test setup. pytest reads this file automatically before any test.

It builds the app with TestConfig instead of the real settings, so tests:
- use a throwaway in-memory SQLite database, never Supabase;
- never send real emails;
- can post forms without a CSRF token (CSRF gets its own test in Batch 8b).
"""
import pytest

from app import create_app
from app.config import Config
from app.extensions import db


class TestConfig(Config):
    """The real Config, with the parts that touch the outside world replaced."""
    TESTING = True
    SECRET_KEY = "test-secret-key"
    # ":memory:" = a database that lives only in memory and vanishes after
    # each test, so tests are fast and can never damage real data.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Your real config adds pg8000's SSL settings when .env holds a
    # Supabase address. SQLite doesn't understand them, so start clean.
    SQLALCHEMY_ENGINE_OPTIONS = {}
    # Lets tests post forms directly; CSRF protection is tested separately.
    WTF_CSRF_ENABLED = False
    # Flask-Mail builds the email but doesn't actually send it.
    MAIL_SUPPRESS_SEND = True
    # Fixed values so tests behave the same whether or not your .env has
    # Gmail settings.
    MAIL_USERNAME = "test-sender@example.com"
    MAIL_DEFAULT_SENDER = "test-sender@example.com"


@pytest.fixture
def app():
    """A fresh app with empty tables, for each test.

    A *fixture* is setup that pytest runs for any test that asks for it by
    name, e.g. def test_x(app):. Everything before `yield` runs before the
    test; everything after runs afterwards to clean up.
    """
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()       # build all 10 tables from the models
        yield app
        db.session.remove()
        db.drop_all()         # throw everything away


@pytest.fixture
def client(app):
    """Flask's pretend browser, for making requests to the app."""
    return app.test_client()


# Small helpers so tests don't repeat the same form data.

def register_farmer(client, name="Jane Farmer", email="jane@example.com", password="password123"):
    return client.post("/auth/register", data={
        "name": name, "email": email, "phone": "",
        "password": password, "confirm_password": password,
    })


def login(client, role, email="jane@example.com", password="password123"):
    return client.post(f"/auth/login/{role}", data={"email": email, "password": password})