"""Tests for adding workers, data scoping between farms, and role checks."""
from app.models import User, Worker
from tests.conftest import login, register_farmer


def add_worker(client, name="Wanjiru", email="wanjiru@example.com", password="workerpass1"):
    return client.post("/workers/new", data={
        "name": name, "email": email, "phone": "",
        "password": password, "confirm_password": password,
    })


def test_farmer_can_add_a_worker_tied_to_their_farm(app, client):
    register_farmer(client)
    login(client, "farmer")

    response = add_worker(client)

    assert response.headers["Location"] == "/workers/"
    with app.app_context():
        worker = Worker.query.one()
        assert worker.farmer.email == "jane@example.com"   # tied to the right farm
    assert b"Wanjiru" in client.get("/workers/").data


def test_new_worker_can_log_in_through_the_worker_door(client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client)
    client.post("/auth/logout")

    response = login(client, "worker", email="wanjiru@example.com", password="workerpass1")

    assert response.headers["Location"] == "/dashboard"
    # The apostrophe is plain template text, so it isn't HTML-escaped.
    assert b"Jane Farmer's farm" in client.get("/dashboard").data


def test_farmers_only_see_their_own_workers(app):
    # Two separate "browsers", one per farmer, logged in at the same time.
    farm_a, farm_b = app.test_client(), app.test_client()
    register_farmer(farm_a, name="Farmer A", email="a@example.com")
    register_farmer(farm_b, name="Farmer B", email="b@example.com")
    login(farm_a, "farmer", email="a@example.com")
    login(farm_b, "farmer", email="b@example.com")

    add_worker(farm_a, name="Worker of A", email="wa@example.com")
    add_worker(farm_b, name="Worker of B", email="wb@example.com")

    # DATA SCOPING: each farm sees only its own workers.
    page_a = farm_a.get("/workers/").data
    page_b = farm_b.get("/workers/").data
    assert b"Worker of A" in page_a and b"Worker of B" not in page_a
    assert b"Worker of B" in page_b and b"Worker of A" not in page_b


def test_worker_email_must_be_unique_across_all_farms(app, client):
    register_farmer(client)
    login(client, "farmer")

    response = add_worker(client, email="jane@example.com")   # the farmer's own email

    assert b"An account with this email already exists." in response.data
    with app.app_context():
        assert Worker.query.count() == 0


def test_workers_cannot_open_or_use_farmer_pages(app, client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client)
    client.post("/auth/logout")
    login(client, "worker", email="wanjiru@example.com", password="workerpass1")

    # Opening the pages: sent back to the dashboard.
    for url in ("/workers/", "/workers/new"):
        response = client.get(url)
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

    # Sending the form directly, without the page: still refused.
    add_worker(client, name="Sneaky", email="sneaky@example.com")
    with app.app_context():
        assert User.query.filter_by(email="sneaky@example.com").first() is None


def test_worker_pages_need_a_login(client):
    response = client.get("/workers/")
    assert response.headers["Location"].startswith("/?next=")