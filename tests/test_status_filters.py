"""Filters and tag search on the Unwell, Pregnant and Market pages, and the
medicine search in the pharmacy."""
from app.extensions import db
from app.models import Livestock
from tests.test_pharmacy import as_farmer, farm_with_worker, medicine
from tests.test_records_general import add_animal, farmer_logged_in
from tests.test_status import add_health, add_pregnancy


def tags_on(page):
    """Which of our test tags appear on the page."""
    return {tag for tag in ("C001", "C002", "G001", "G002", "S001") if tag.encode() in page}


# ------------------------------------------------------------ unwell animals

def unwell_farm(app, client):
    farmer_logged_in(client)
    cow = add_animal(app, "C001", species="CATTLE")
    bull = add_animal(app, "C002", species="CATTLE", gender="MALE")
    goat = add_animal(app, "G001")
    add_health(app, cow, 2, disease="East Coast Fever")
    add_health(app, bull, 3, disease="Mastitis")
    add_health(app, goat, 1, disease="East Coast Fever")


def test_unwell_filters_by_species_disease_and_sex(app, client):
    unwell_farm(app, client)
    assert tags_on(client.get("/status/health").data) == {"C001", "C002", "G001"}
    assert tags_on(client.get("/status/health?species=goat").data) == {"G001"}
    assert tags_on(client.get("/status/health?disease=Mastitis").data) == {"C002"}
    assert tags_on(client.get("/status/health?sex=female&species=cattle").data) == {"C001"}


def test_unwell_tag_search_ignores_case(app, client):
    unwell_farm(app, client)
    assert tags_on(client.get("/status/health?q=c00").data) == {"C001", "C002"}


def test_the_disease_list_only_has_diseases_in_the_table(app, client):
    unwell_farm(app, client)
    page = client.get("/status/health").data
    assert b'<option value="Mastitis"' in page and b'<option value="Anthrax"' not in page


def test_made_up_filter_values_are_ignored(app, client):
    unwell_farm(app, client)
    page = client.get("/status/health?species=pig&disease=<b>bad</b>&sex=x").data
    assert tags_on(page) == {"C001", "C002", "G001"} and b"<b>bad</b>" not in page


def test_no_match_says_so_and_the_list_is_not_lost(app, client):
    unwell_farm(app, client)
    page = client.get("/status/health?q=zzz").data
    assert b"No animals match these filters" in page and b"Clear filters" in page
    assert tags_on(client.get("/status/health").data) == {"C001", "C002", "G001"}


# ---------------------------------------------------------- pregnant animals

def test_pregnant_filters_by_species_and_tag(app, client):
    farmer_logged_in(client)
    add_pregnancy(app, add_animal(app, "C001", species="CATTLE"), 20)
    add_pregnancy(app, add_animal(app, "G001"), 10)
    add_pregnancy(app, add_animal(app, "S001", species="SHEEP"), 30)
    assert tags_on(client.get("/status/condition?species=sheep").data) == {"S001"}
    assert tags_on(client.get("/status/condition?q=g0").data) == {"G001"}
    # Pregnant animals are all female: there's no sex filter on this page.
    assert b'name="sex"' not in client.get("/status/condition").data


# --------------------------------------------------------------- market list

def test_market_filters_by_species_sex_and_sell_or_cull(app, client):
    farmer_logged_in(client)
    marks = {"C001": ("CATTLE", "FEMALE", "SELL"), "C002": ("CATTLE", "MALE", "CULL"),
             "G001": ("GOAT", "MALE", "SELL"), "G002": ("GOAT", "FEMALE", "CULL")}
    for tag, (species, gender, mark) in marks.items():
        animal_id = add_animal(app, tag, species=species, gender=gender)
        with app.app_context():
            db.session.get(Livestock, animal_id).market_status = mark
            db.session.commit()
    assert tags_on(client.get("/status/market?mark=cull").data) == {"C002", "G002"}
    assert tags_on(client.get("/status/market?sex=male&mark=sell").data) == {"G001"}
    assert tags_on(client.get("/status/market?species=cattle&q=2").data) == {"C002"}


# ------------------------------------------------------------------ pharmacy

def test_pharmacy_search_by_medicine_or_disease(app, client):
    farm_with_worker(client)
    as_farmer(client)
    client.post("/pharmacy/new", data=medicine())
    client.post("/pharmacy/new", data=medicine(name="Albendazole", disease="Worms", quantity="0"))
    page = client.get("/pharmacy/?q=tylo").data
    assert b"Tylosin 20%" in page and b">Albendazole<" not in page
    assert b"Out: Albendazole" in page            # the shortage warning still shows
    assert b"Albendazole" in client.get("/pharmacy/?q=worm").data
    assert b"No medicine matches" in client.get("/pharmacy/?q=zzz").data