"""The General record: choosing an animal, registering one, and editing one."""
from datetime import date, timedelta

from app.extensions import db
from app.models import CommercialInfo, Farmer, Livestock, MortalityRecord
from tests.conftest import login, register_farmer
from tests.test_records import add_worker_and_log_in_as_them


def farm_id_of(email="jane@example.com"):
    return next(f.farmer_id for f in Farmer.query.all() if f.email == email)


def add_animal(app, tag, species="GOAT", email="jane@example.com", **details):
    """Put an animal straight into the database and return its id."""
    with app.app_context():
        animal = Livestock(farmer_id=farm_id_of(email), tag_number=tag, species=species,
                           gender=details.pop("gender", "FEMALE"), **details)
        db.session.add(animal)
        db.session.commit()
        return animal.animal_id


def new_goat(**changes):
    data = {"tag_number": "G001", "gender": "FEMALE", "breed": "Galla",
            "date_of_birth": "2024-03-01", "description": "White with a brown face"}
    data.update(changes)
    return data


def farmer_logged_in(client):
    register_farmer(client)
    login(client, "farmer")


#Choosing an animal

def test_general_tile_now_leads_to_choosing_an_animal(client):
    farmer_logged_in(client)
    assert b"/records/add/goat/general" in client.get("/records/add/goat").data


def test_choose_animal_lists_only_this_farms_animals_of_this_species(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    farmer_logged_in(client)
    add_animal(app, "G001")
    add_animal(app, "C001", species="CATTLE")
    add_animal(app, "G900", email="other@example.com")

    page = client.get("/records/add/goat/general").data

    assert b"G001" in page
    assert b"C001" not in page          # other species
    assert b"G900" not in page          # other farm
    assert b"G002" in page              # the suggested next tag


def test_dead_and_sold_animals_are_not_offered(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    dead = add_animal(app, "G002")
    sold = add_animal(app, "G003")
    with app.app_context():
        db.session.add(MortalityRecord(animal_id=dead, date_of_death=date.today(), cause_of_death="Pneumonia"))
        db.session.add(CommercialInfo(animal_id=sold, transaction_type="SELL", date=date.today(), amount=8000))
        db.session.commit()

    page = client.get("/records/add/goat/general").data

    assert b"G001" in page
    assert b"G002" not in page
    assert b"G003" not in page


def test_search_by_tag_or_breed(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001", breed="Galla")
    add_animal(app, "G002", breed="Toggenburg")

    by_breed = client.get("/records/add/goat/general?q=togg").data
    assert b"G002" in by_breed and b"G001</span>" not in by_breed

    by_tag = client.get("/records/add/goat/general?q=g001").data
    assert b"G001</span>" in by_tag and b"G002</span>" not in by_tag

    nothing = client.get("/records/add/goat/general?q=zebra").data
    assert b"No goats match" in nothing


def test_categories_without_a_form_are_not_found_yet(client):
    farmer_logged_in(client)
    assert client.get("/records/add/goat/breeding").status_code == 404    
    assert client.get("/records/add/goat/nonsense").status_code == 404


# Registering

def test_new_animal_form_suggests_the_next_tag(app, client):
    farmer_logged_in(client)
    add_animal(app, "G007")
    assert b'value="G008"' in client.get("/records/add/goat/general/new").data


def test_registering_an_animal(app, client):
    farmer_logged_in(client)

    response = client.post("/records/add/goat/general/new", data=new_goat())

    assert response.status_code == 302
    assert "/records/saved/" in response.headers["Location"]
    with app.app_context():
        goat = Livestock.query.one()
        assert (goat.tag_number, goat.species, goat.gender, goat.breed) == ("G001", "GOAT", "FEMALE", "Galla")
        assert goat.date_of_birth == date(2024, 3, 1)
        assert goat.farmer_id == farm_id_of()

    saved = client.get(response.headers["Location"]).data
    assert b"G001" in saved and b"Registered" in saved


def test_species_comes_from_the_page_not_the_form(app, client):
    farmer_logged_in(client)
    client.post("/records/add/sheep/general/new", data=new_goat(tag_number="S001", species="CATTLE"))
    with app.app_context():
        assert Livestock.query.one().species == "SHEEP"


def test_a_worker_registers_animals_on_their_farmers_farm(app, client):
    add_worker_and_log_in_as_them(client)
    client.post("/records/add/goat/general/new", data=new_goat())
    with app.app_context():
        assert Livestock.query.one().farmer_id == farm_id_of()


def test_tag_is_tidied_before_saving(app, client):
    farmer_logged_in(client)
    client.post("/records/add/goat/general/new", data=new_goat(tag_number=" g 014 "))
    with app.app_context():
        assert Livestock.query.one().tag_number == "G014"


def test_optional_fields_can_be_left_blank(app, client):
    farmer_logged_in(client)
    response = client.post("/records/add/goat/general/new",
                           data=new_goat(breed="", date_of_birth="", description=""))
    assert response.status_code == 302
    with app.app_context():
        goat = Livestock.query.one()
        assert goat.breed is None and goat.date_of_birth is None and goat.description is None


def test_duplicate_tag_is_refused(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")

    response = client.post("/records/add/goat/general/new", data=new_goat())

    assert response.status_code == 200
    assert b"already has this tag" in response.data
    with app.app_context():
        assert Livestock.query.count() == 1


def test_another_farm_can_use_the_same_tag(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)
    assert client.post("/records/add/goat/general/new", data=new_goat()).status_code == 302


def test_bad_input_is_refused_with_messages(app, client):
    farmer_logged_in(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    cases = [
        (new_goat(tag_number=""), b"Every animal needs a tag number"),
        (new_goat(tag_number="G/01"), b"Use only letters, numbers and hyphens"),
        (new_goat(gender=""), b"Choose female or male"),
        (new_goat(date_of_birth=tomorrow), b"can&#39;t be in the future"),
    ]
    for data, message in cases:
        response = client.post("/records/add/goat/general/new", data=data)
        assert response.status_code == 200
        assert message in response.data
    with app.app_context():
        assert Livestock.query.count() == 0


# Editing

def test_edit_form_shows_the_current_details(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", breed="Galla")
    page = client.get(f"/records/add/goat/general/{goat}").data
    assert b"Edit" in page and b'value="G001"' in page and b'value="Galla"' in page


def test_editing_an_animal(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", breed="Galla")

    # Keeping its own tag must not count as "already in use".
    response = client.post(f"/records/add/goat/general/{goat}", data=new_goat(breed="Saanen", gender="MALE"))

    assert response.status_code == 302 and "action=updated" in response.headers["Location"]
    with app.app_context():
        updated = db.session.get(Livestock, goat)
        assert (updated.breed, updated.gender) == ("Saanen", "MALE")
        assert Livestock.query.count() == 1


def test_duplicate_tag_is_reported_together_with_other_mistakes(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    response = client.post("/records/add/goat/general/new", data=new_goat(gender=""))
    assert b"already has this tag" in response.data and b"Choose female or male" in response.data


def test_cannot_edit_to_a_tag_another_animal_has(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    second = add_animal(app, "G002")
    response = client.post(f"/records/add/goat/general/{second}", data=new_goat(tag_number="G001"))
    assert b"already has this tag" in response.data


def test_another_farms_animal_cannot_be_opened(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)

    assert client.get(f"/records/add/goat/general/{theirs}").status_code == 404
    assert client.post(f"/records/add/goat/general/{theirs}", data=new_goat(breed="Hacked")).status_code == 404
    assert client.get(f"/records/saved/{theirs}").status_code == 404


def test_species_in_the_url_must_match_the_animal(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    assert client.get(f"/records/add/cattle/general/{goat}").status_code == 404


def test_pages_need_a_login(client):
    for url in ("/records/add/goat/general", "/records/add/goat/general/new", "/records/saved/1"):
        assert client.get(url).headers["Location"].startswith("/?next=")


#Age label

def test_age_label(app_ctx):
    today = date.today()
    animal = Livestock(date_of_birth=None)
    assert animal.age_label is None
    animal.date_of_birth = today - timedelta(days=10)
    assert animal.age_label == "10 days"
    animal.date_of_birth = date(today.year - 1, today.month, 1)
    assert animal.age_label == "12 months"
    animal.date_of_birth = date(today.year - 5, 1, 1)
    assert animal.age_label == "5 years"
