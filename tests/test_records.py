"""Tests for the Add Record flow: species and category pages."""
from app.routes.records import CATEGORIES
from tests.conftest import login, register_farmer


def add_worker_and_log_in_as_them(client):
    register_farmer(client)
    login(client, "farmer")
    client.post("/workers/new", data={
        "name": "Wanjiru", "email": "w@example.com", "phone": "",
        "password": "workerpass1", "confirm_password": "workerpass1",
    })
    client.post("/auth/logout")
    login(client, "worker", email="w@example.com", password="workerpass1")


def test_add_record_needs_a_login(client):
    for url in ("/records/add", "/records/add/goat"):
        assert client.get(url).headers["Location"].startswith("/?next=")


def test_farmer_can_choose_a_species(client):
    register_farmer(client)
    login(client, "farmer")

    page = client.get("/records/add").data

    for label in (b"Cattle", b"Chickens", b"Goats", b"Sheep"):
        assert label in page
    assert b"/records/add/goat" in page


def test_workers_can_add_records_too(client):
    add_worker_and_log_in_as_them(client)
    assert client.get("/records/add").status_code == 200
    assert client.get("/records/add/sheep").status_code == 200


def test_category_page_shows_all_six_categories(client):
    register_farmer(client)
    login(client, "farmer")

    page = client.get("/records/add/goat").data

    assert b"GOATS" in page.upper()
    # Checked against CATEGORIES itself, so the test can't drift from the code.
    for category in CATEGORIES:
        assert category["title"].encode() in page
        assert category["blurb"].encode() in page


def test_unknown_species_is_not_found(client):
    register_farmer(client)
    login(client, "farmer")
    assert client.get("/records/add/horse").status_code == 404


def test_add_record_link_is_in_the_navigation(client):
    register_farmer(client)
    login(client, "farmer")
    assert b'href="/records/add">Add Record</a>' in client.get("/dashboard").data