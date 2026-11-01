"""Recording that a male has been castrated (a steer, or a wether), and
counting steers apart from bulls on the dashboard."""
from datetime import date, timedelta

from app import status
from app.extensions import db
from app.models import Livestock
from tests.test_records_general import farm_id_of, farmer_logged_in


def steer(**changes):
    data = {"tag_number": "C001", "gender": "MALE", "castrated": "y", "breed": "Boran",
            "date_of_birth": (date.today() - timedelta(days=800)).isoformat(), "description": ""}
    data.update(changes)
    return {k: v for k, v in data.items() if v is not None}


def animal(app, tag="C001"):
    with app.app_context():
        return Livestock.query.filter_by(tag_number=tag).one()


def test_the_animal_form_offers_castrated(client):
    farmer_logged_in(client)
    page = client.get("/records/add/cattle/general/new").data
    assert b"Castrated" in page and b'data-show-for-sex="MALE"' in page


def test_a_castrated_male_is_saved_and_shown(app, client):
    farmer_logged_in(client)
    client.post("/records/add/cattle/general/new", data=steer())
    cow = animal(app)
    assert cow.castrated is True
    assert b"Male, castrated" in client.get(f"/herd/{cow.animal_id}").data


def test_a_female_cannot_be_castrated(app, client):
    farmer_logged_in(client)
    page = client.post("/records/add/cattle/general/new", data=steer(gender="FEMALE")).data
    assert b"Only a male can be castrated" in page
    with app.app_context():
        assert Livestock.query.count() == 0


def test_unticking_it_when_editing_saves_not_castrated(app, client):
    farmer_logged_in(client)
    client.post("/records/add/cattle/general/new", data=steer())
    animal_id = animal(app).animal_id
    client.post(f"/records/add/cattle/general/{animal_id}", data=steer(castrated=None))
    assert animal(app).castrated is False


def test_existing_animals_are_not_castrated(app, client):
    farmer_logged_in(client)
    client.post("/records/add/cattle/general/new", data=steer(castrated=None))
    assert animal(app).castrated is False


def test_the_dashboard_counts_steers_apart_from_bulls(app, client):
    farmer_logged_in(client)
    client.post("/records/add/cattle/general/new", data=steer())
    client.post("/records/add/cattle/general/new", data=steer(tag_number="C002", castrated=None))
    client.post("/records/add/cattle/general/new",                      # a castrated calf is still a calf
                data=steer(tag_number="C003", date_of_birth=(date.today() - timedelta(days=100)).isoformat()))
    with app.app_context():
        cattle = status.animal_counts(farm_id_of())["cattle"]
    assert (cattle["Steers"], cattle["Bulls"], cattle["Calves"]) == (1, 1, 1)
    assert b"1 calf \xc2\xb7 1 steer \xc2\xb7 1 bull" in client.get("/dashboard").data