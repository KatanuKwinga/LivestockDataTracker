"""Treat a group: tick spraying, deworming and vaccination sessions."""
import re
from datetime import date, timedelta

from app.extensions import db
from app.models import HealthRecord, HerdActivity
from tests.conftest import register_farmer
from tests.test_herd import sell
from tests.test_records import add_worker_and_log_in_as_them
from tests.test_records_general import add_animal, farm_id_of, farmer_logged_in


def session_data(**changes):
    # Only what the browser really sends: the page for a spraying or
    # deworming session has no Vaccine box, so no "vaccine" key here.
    data = {"date": "2026-10-01", "notes": ""}
    data.update(changes)
    return data


def records(app):
    with app.app_context():
        return HealthRecord.query.order_by(HealthRecord.animal_id).all()


def farm_id(app, email="jane@example.com"):
    with app.app_context():
        return farm_id_of(email)


def sessions(app):
    with app.app_context():
        return HerdActivity.query.all()


# ---------------------------------------------------------------- the pages

def test_group_pages_need_a_login(client):
    for url in ("/group/", "/group/spray", "/group/spray/cattle", "/group/saved/1"):
        assert client.get(url).headers["Location"].startswith("/?next=")


def test_navigation_and_worker_home_link_here(client):
    add_worker_and_log_in_as_them(client)
    home = client.get("/dashboard").data
    assert home.count(b'href="/group/"') >= 2                 # navbar and the home tile
    page = client.get("/group/").data
    for title in (b"Tick spraying", b"Deworming", b"Vaccination"):
        assert title in page


def test_only_sensible_herds_are_offered(client):
    farmer_logged_in(client)
    assert b"/group/spray/chicken" not in client.get("/group/spray").data      # chickens aren't sprayed
    assert b"/group/deworm/chicken" in client.get("/group/deworm").data
    assert client.get("/group/spray/chicken").status_code == 404
    assert client.get("/group/bathe").status_code == 404
    assert client.get("/group/spray/horse").status_code == 404


# ----------------------------------------------------------------- spraying

def test_spraying_is_one_record_for_the_herd(app, client):
    farmer_logged_in(client)
    add_animal(app, "C001", species="CATTLE")
    add_animal(app, "C002", species="CATTLE")

    assert b'value="Dip Dominex"' in client.get("/group/spray/cattle").data
    response = client.post("/group/spray/cattle", data=session_data(product="Dip Dominex"))

    assert "/group/saved/" in response.headers["Location"]
    [spray] = sessions(app)
    assert (spray.activity, spray.species, spray.product, spray.date) == ("TICK_SPRAY", "CATTLE", "Dip Dominex", date(2026, 10, 1))
    assert spray.farmer_id == farm_id(app)
    assert records(app) == []                                 # no per-animal rows for spraying
    assert b"Whole herd" in client.get(response.headers["Location"]).data


def test_session_needs_a_product_and_a_real_date(app, client):
    farmer_logged_in(client)
    add_animal(app, "C001", species="CATTLE")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    no_product = client.post("/group/spray/cattle", data=session_data())
    future = client.post("/group/spray/cattle", data=session_data(product="Dip Dominex", date=tomorrow))

    assert b"Write the product that was used" in no_product.data
    assert b"can&#39;t be in the future" in future.data
    assert sessions(app) == []


# ---------------------------------------------------------------- deworming

def test_deworming_ticks_everyone_except_the_very_young(app, client):
    farmer_logged_in(client)
    adult = add_animal(app, "G001", date_of_birth=date(2024, 1, 1))
    kid = add_animal(app, "G002", date_of_birth=date.today() - timedelta(days=10))

    page = client.get("/group/deworm/goat").data

    assert b'value="Nilzan"' in page
    ticked = re.findall(rb'<input checked[^>]*value="(\d+)"', page)
    assert ticked == [str(adult).encode()]                     # the 10-day-old kid is left unticked
    assert f'value="{kid}"'.encode() in page and b"under 30 days" in page


def test_deworming_writes_one_health_record_per_ticked_animal(app, client):
    farmer_logged_in(client)
    first = add_animal(app, "G001")
    second = add_animal(app, "G002")
    missed = add_animal(app, "G003")
    add_animal(app, "C001", species="CATTLE")

    response = client.post("/group/deworm/goat", data={**session_data(product="Nilzan"), "animals": [first, second]})

    [deworm] = sessions(app)
    assert (deworm.activity, deworm.product) == ("DEWORMING", "Nilzan")
    saved = records(app)
    assert [r.animal_id for r in saved] == [first, second]
    for record in saved:
        # Exactly what the prediction model looks for.
        assert (record.record_type, record.description, record.treatment) == ("TREATMENT", "Routine deworming", "Nilzan")
    assert missed not in [r.animal_id for r in saved]
    assert b"<dd>2</dd>" in client.get(response.headers["Location"]).data


def test_deworming_needs_at_least_one_animal(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    response = client.post("/group/deworm/goat", data=session_data(product="Nilzan"))
    assert b"Tick at least one animal" in response.data
    assert sessions(app) == [] and records(app) == []


def test_animals_from_another_farm_or_species_cannot_be_ticked(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)
    mine = add_animal(app, "G001")
    cow = add_animal(app, "C001", species="CATTLE")

    for intruder in (theirs, cow):
        response = client.post("/group/deworm/goat", data={**session_data(product="Nilzan"), "animals": [mine, intruder]})
        assert b"not a valid choice for this field" in response.data
    assert sessions(app) == [] and records(app) == []


def test_sold_animals_are_not_listed(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    sell(app, add_animal(app, "G002"))
    page = client.get("/group/deworm/goat").data
    assert b"G001" in page and b"G002" not in page


def test_an_animal_born_after_the_date_is_refused(app, client):
    farmer_logged_in(client)
    kid = add_animal(app, "G009", date_of_birth=date(2026, 10, 5))
    response = client.post("/group/deworm/goat", data={**session_data(product="Nilzan"), "animals": [kid]})
    assert b"Not born yet on that date: G009" in response.data
    assert records(app) == []


# -------------------------------------------------------------- vaccination

def test_group_vaccination_is_saved_the_way_the_model_reads_it(app, client):
    farmer_logged_in(client)
    first = add_animal(app, "G001")
    second = add_animal(app, "G002")

    client.post("/group/vaccinate/goat", data={**session_data(vaccine="CCPP vaccine"), "animals": [first, second]})

    [vaccination] = sessions(app)
    assert (vaccination.activity, vaccination.product) == ("VACCINATION", "CCPP vaccine")
    assert [(r.record_type, r.treatment, r.disease) for r in records(app)] == [("VACCINATION", "CCPP vaccine", None)] * 2


def test_vaccination_needs_a_vaccine_for_the_species(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    missing = client.post("/group/vaccinate/goat", data={**session_data(), "animals": [goat]})
    wrong = client.post("/group/vaccinate/goat", data={**session_data(vaccine="Lumpy skin vaccine"), "animals": [goat]})
    assert b"Choose the vaccine that was given" in missing.data
    assert b"Not a valid choice" in wrong.data
    assert sessions(app) == []


# ------------------------------------------------------- who sees what

def test_a_worker_records_sessions_for_their_farmers_farm(app, client):
    add_worker_and_log_in_as_them(client)
    add_animal(app, "C001", species="CATTLE")
    client.post("/group/spray/cattle", data=session_data(product="Dip Dominex"))
    assert sessions(app)[0].farmer_id == farm_id(app)


def test_recent_sessions_and_saved_pages_belong_to_one_farm(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    with app.app_context():
        theirs = HerdActivity(farmer_id=farm_id_of("other@example.com"), species="CATTLE", date=date(2026, 9, 9),
                              activity="TICK_SPRAY", product="Their own spray")
        db.session.add(theirs)
        db.session.commit()
        theirs_id = theirs.activity_id
    farmer_logged_in(client)
    first = add_animal(app, "G001")
    client.post("/group/deworm/goat", data={**session_data(product="Nilzan"), "animals": [first]})

    page = client.get("/group/").data
    assert b"Nilzan" in page and b"Their own spray" not in page
    assert client.get(f"/group/saved/{theirs_id}").status_code == 404