"""Tests for the welcome, sign-in and the two home pages."""
from datetime import date

from app.extensions import db
from app.models import CommercialInfo, Livestock, MortalityRecord, User
from tests.conftest import login, register_farmer


def add_worker(client):
    client.post("/workers/new", data={
        "name": "Wanjiru Kamau", "email": "wanjiru@example.com", "phone": "",
        "password": "workerpass1", "confirm_password": "workerpass1",
    })


def add_animals(app):
    """Farm of jane@example.com: 3 goats and 1 cow, but one goat has died and
    the cow was sold, so only 2 goats are still on the farm."""
    with app.app_context():
        farmer_id = User.query.filter_by(email="jane@example.com").first().farmer.farmer_id
        animals = [Livestock(farmer_id=farmer_id, tag_number=t, species=s, gender="FEMALE")
                   for t, s in (("G001", "GOAT"), ("G002", "GOAT"), ("G003", "GOAT"), ("C001", "CATTLE"))]
        db.session.add_all(animals)
        db.session.flush()
        db.session.add(MortalityRecord(animal_id=animals[2].animal_id, date_of_death=date(2026, 9, 1),
                                       cause_of_death="Pneumonia"))
        db.session.add(CommercialInfo(animal_id=animals[3].animal_id, transaction_type="SELL",
                                      date=date(2026, 9, 2), amount=150000))
        db.session.commit()


def test_welcome_page_offers_both_doors(client):
    page = client.get("/").data
    assert b"/auth/login/farmer" in page and b"/auth/login/worker" in page
    assert b'id="meadow"' in page            # the animated grassland
    assert b'symbol id="mark"' in page       # the four-animal logo


def test_login_switch_marks_the_current_door(client):
    page = client.get("/auth/login/worker").data
    assert b'role-toggle is-worker' in page
    assert b'Worker sign in' in page


def test_farmer_home_shows_herd_counts_for_animals_still_on_the_farm(app, client):
    register_farmer(client)
    add_animals(app)
    login(client, "farmer")
    page = client.get("/dashboard").data.decode()
    assert "overview of your livestock" in page
    assert "Goats <b class=\"mono\">2</b>" in page       # dead goat left out
    assert "Cattle <b class=\"mono\">0</b>" in page      # sold cow left out
    assert "Your workers" in page


def test_worker_home_asks_what_to_do_and_hides_farmer_pages(client):
    register_farmer(client)
    login(client, "farmer")
    add_worker(client)
    client.post("/auth/logout")
    login(client, "worker", email="wanjiru@example.com", password="workerpass1")

    page = client.get("/dashboard").data.decode()
    assert "What would you like to do today?" in page
    assert "Add a record" in page
    assert 'href="/workers/"' not in page              # no Workers link for workers
    assert "Your workers" not in page


def test_navbar_highlights_the_current_section(client):
    register_farmer(client)
    login(client, "farmer")
    page = client.get("/records/add").data.decode()
    assert '<a href="/records/add" aria-current="page">Add record</a>' in page


def test_no_emoji_on_the_species_page(client):
    register_farmer(client)
    login(client, "farmer")
    page = client.get("/records/add").data.decode()
    assert not any(ord(ch) > 0x2FFF for ch in page)
