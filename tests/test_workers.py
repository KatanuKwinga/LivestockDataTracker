"""Tests for adding workers, data scoping between farms, and role checks.
Workers sign in with a username; only farmers have an email."""
from app.models import User, Worker
from tests.conftest import login, register_farmer


def add_worker(client, name="Wanjiru", username="wanjiru", password="workerpass1"):
    return client.post("/workers/new", data={
        "name": name, "username": username, "phone": "",
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
        assert worker.username == "wanjiru"
        assert worker.user.email is None                    # workers have no email
    page = client.get("/workers/").data
    assert b"Wanjiru" in page and b"wanjiru" in page


def test_new_worker_can_log_in_through_the_worker_door_with_their_username(client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client, username="Wanjiru ")                 # stored as "wanjiru"
    client.post("/auth/logout")

    response = login(client, "worker", username="WANJIRU", password="workerpass1")

    assert response.headers["Location"] == "/dashboard"
    # The apostrophe is plain template text, so it isn't HTML-escaped.
    assert b"Jane Farmer's farm" in client.get("/dashboard").data


def test_wrong_worker_password_gets_the_general_message(client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client)
    client.post("/auth/logout")
    response = login(client, "worker", username="wanjiru", password="wrong-password")
    assert b"Invalid username or password." in response.data


def test_a_worker_at_the_farmer_door_is_sent_to_the_worker_door(client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client)
    client.post("/auth/logout")
    response = client.post("/auth/login/farmer", follow_redirects=True,
                           data={"email": "wanjiru", "password": "workerpass1"})
    assert response.request.path == "/auth/login/worker"
    assert b"This is a worker account" in response.data


def test_farmers_only_see_their_own_workers(app):
    # Two separate "browsers", one per farmer, logged in at the same time.
    farm_a, farm_b = app.test_client(), app.test_client()
    register_farmer(farm_a, name="Farmer A", email="a@example.com")
    register_farmer(farm_b, name="Farmer B", email="b@example.com")
    login(farm_a, "farmer", email="a@example.com")
    login(farm_b, "farmer", email="b@example.com")

    add_worker(farm_a, name="Worker of A", username="worker.a")
    add_worker(farm_b, name="Worker of B", username="worker.b")

    # DATA SCOPING: each farm sees only its own workers.
    page_a = farm_a.get("/workers/").data
    page_b = farm_b.get("/workers/").data
    assert b"Worker of A" in page_a and b"Worker of B" not in page_a
    assert b"Worker of B" in page_b and b"Worker of A" not in page_b


def test_usernames_must_be_unique_across_all_farms_and_follow_the_rules(app):
    farm_a, farm_b = app.test_client(), app.test_client()
    register_farmer(farm_a, email="a@example.com")
    register_farmer(farm_b, email="b@example.com")
    login(farm_a, "farmer", email="a@example.com")
    login(farm_b, "farmer", email="b@example.com")
    add_worker(farm_a, username="wanjiru")

    taken = add_worker(farm_b, username="wanjiru")
    assert b"That username is taken" in taken.data
    for bad in ("wa", "has space", "w@x.com"):
        assert b"Use 3 to 30 letters" in add_worker(farm_b, username=bad).data
    with app.app_context():
        assert Worker.query.count() == 1


def test_farmer_can_set_a_new_password_for_their_own_worker_only(app):
    farm_a, farm_b = app.test_client(), app.test_client()
    register_farmer(farm_a, email="a@example.com")
    register_farmer(farm_b, email="b@example.com")
    login(farm_a, "farmer", email="a@example.com")
    login(farm_b, "farmer", email="b@example.com")
    add_worker(farm_a)
    with app.app_context():
        worker_id = Worker.query.one().worker_id
    new = {"password": "newpass123", "confirm_password": "newpass123"}

    # Another farm can't reach this worker: "Not Found".
    assert farm_b.post(f"/workers/{worker_id}/password", data=new).status_code == 404

    response = farm_a.post(f"/workers/{worker_id}/password", data=new)
    assert response.headers["Location"] == "/workers/"
    farm_a.post("/auth/logout")
    assert login(farm_a, "worker", username="wanjiru", password="newpass123").headers["Location"] == "/dashboard"


def test_workers_cannot_open_or_use_farmer_pages(app, client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client)
    client.post("/auth/logout")
    login(client, "worker", username="wanjiru", password="workerpass1")

    # Opening the pages: sent back to the dashboard.
    for url in ("/workers/", "/workers/new", "/workers/1/password"):
        response = client.get(url)
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

    # Sending the form directly, without the page: still refused.
    add_worker(client, name="Sneaky", username="sneaky")
    with app.app_context():
        assert User.query.filter_by(username="sneaky").first() is None


def test_worker_pages_need_a_login(client):
    response = client.get("/workers/")
    assert response.headers["Location"].startswith("/?next=")