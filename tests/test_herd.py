"""The Records pages: the herd table (filters, search, pages) and one animal's history."""
import re
from datetime import date

from app.extensions import db
from app.models import (BreedingRecord, CommercialInfo, HealthRecord, Livestock,
                        MortalityRecord, ProductionData, WeightRecord)
from tests.conftest import register_farmer
from tests.test_records import add_worker_and_log_in_as_them
from tests.test_records_general import add_animal, farmer_logged_in


def sell(app, animal_id):
    with app.app_context():
        db.session.add(CommercialInfo(animal_id=animal_id, transaction_type="SELL", date=date(2026, 5, 1),
                                      amount=12500, other_party="Kiserian market"))
        db.session.commit()


def bury(app, animal_id):
    with app.app_context():
        db.session.add(MortalityRecord(animal_id=animal_id, date_of_death=date(2026, 6, 2), cause_of_death="Pneumonia"))
        db.session.commit()


def tags_on(page):
    """The tags shown in the table, in order."""
    return re.findall(rb'class="row-link mono"[^>]*>([^<]+)<', page)


# ------------------------------------------------------------------ the table

def test_records_need_a_login(client):
    for url in ("/herd/", "/herd/1"):
        assert client.get(url).headers["Location"].startswith("/?next=")


def test_records_link_is_in_the_navigation_and_highlighted(client):
    farmer_logged_in(client)
    assert b'href="/herd/"' in client.get("/dashboard").data
    assert b'href="/herd/" aria-current="page"' in client.get("/herd/").data


def test_table_shows_only_this_farms_animals(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    farmer_logged_in(client)
    add_animal(app, "G001")
    add_animal(app, "C001", species="CATTLE")
    add_animal(app, "G900", email="other@example.com")

    assert sorted(tags_on(client.get("/herd/").data)) == [b"C001", b"G001"]


def test_workers_see_their_farmers_animals(app, client):
    add_worker_and_log_in_as_them(client)
    add_animal(app, "G001")
    assert tags_on(client.get("/herd/").data) == [b"G001"]


def test_status_filter(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    sell(app, add_animal(app, "G002"))
    bury(app, add_animal(app, "G003"))

    assert tags_on(client.get("/herd/").data) == [b"G001"]                 # default: on the farm
    assert tags_on(client.get("/herd/?status=sold").data) == [b"G002"]
    assert tags_on(client.get("/herd/?status=died").data) == [b"G003"]
    assert tags_on(client.get("/herd/?status=all").data) == [b"G001", b"G002", b"G003"]


def test_species_filter_and_search(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001", breed="Galla")
    add_animal(app, "G002", breed="Toggenburg")
    add_animal(app, "C001", species="CATTLE", breed="Friesian")

    assert tags_on(client.get("/herd/?species=cattle").data) == [b"C001"]
    assert tags_on(client.get("/herd/?q=togg").data) == [b"G002"]
    assert tags_on(client.get("/herd/?species=goat&q=g00").data) == [b"G001", b"G002"]
    assert b"No animals match" in client.get("/herd/?q=zebra").data


def test_unknown_filter_values_fall_back_to_the_defaults(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    page = client.get("/herd/?species=horse&status=stolen&page=abc")
    assert page.status_code == 200
    assert tags_on(page.data) == [b"G001"]


def test_long_lists_are_split_into_pages_that_keep_the_filters(app, client):
    farmer_logged_in(client)
    for n in range(1, 31):
        add_animal(app, f"G{n:03d}")

    first = client.get("/herd/?species=goat").data
    second = client.get("/herd/?species=goat&page=2").data

    assert len(tags_on(first)) == 25 and len(tags_on(second)) == 5
    assert b"Showing 1&ndash;25 of 30" in first
    assert b"species=goat" in first and b"page=2" in first          # the Next link keeps the filter


# ------------------------------------------------------------ one animal's page

def test_animal_page_shows_its_history(app, client):
    farmer_logged_in(client)
    dam = add_animal(app, "G001", breed="Galla", date_of_birth=date(2022, 5, 3), description="Brown, white blaze")
    sire = add_animal(app, "G010", gender="MALE")
    with app.app_context():
        birth = BreedingRecord(animal_id=dam, sire_id=sire, status="SUCCESSFUL BIRTH",
                               actual_delivery_date=date(2026, 2, 1), num_stillborn=1)
        db.session.add(birth)
        db.session.flush()
        kid = Livestock(farmer_id=db.session.get(Livestock, dam).farmer_id, tag_number="G020",
                        species="GOAT", gender="FEMALE", b_record_id=birth.b_record_id)
        db.session.add_all([
            kid,
            HealthRecord(animal_id=dam, date=date(2026, 4, 2), record_type="ILLNESS",
                         disease="Pneumonia", temperature=40.6, treatment="Oxytetracycline", dosage="5 ml"),
            WeightRecord(animal_id=dam, date=date(2026, 1, 5), weight=38),
            WeightRecord(animal_id=dam, date=date(2026, 3, 5), weight=41.5),
            ProductionData(animal_id=dam, date=date(2026, 3, 6), item="Milk", yield_amount=1.5, metric="L"),
        ])
        db.session.commit()
        kid_id = kid.animal_id
    sell(app, sire)

    page = client.get(f"/herd/{dam}").data
    for text in (b"G001", b"Galla", b"Brown, white blaze", b"Pneumonia", b"40.6", b"Oxytetracycline",
                 b"41.5 kg", b"Milk", b"1.5 L", b"Successful Birth", b"G010", b"On farm"):
        assert text in page, text
    assert page.index(b"41.5 kg") < page.index(b"38 kg")            # newest weight first

    kid_page = client.get(f"/herd/{kid_id}").data
    assert b"Mother" in kid_page and b"G001" in kid_page and b"Father" in kid_page

    sold_page = client.get(f"/herd/{sire}").data
    assert b"Sold" in sold_page and b"KES 12,500" in sold_page and b"Kiserian market" in sold_page


def test_animal_page_for_a_new_animal_has_empty_sections(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    page = client.get(f"/herd/{goat}").data
    assert b"No health records yet" in page and b"Not weighed yet" in page


def test_dead_animal_shows_its_death_and_no_add_button(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    bury(app, goat)
    page = client.get(f"/herd/{goat}").data
    assert b"Died" in page and b"Pneumonia" in page
    assert b"/records/add/goat\"" not in page


def test_another_farms_animal_is_not_found(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)
    assert client.get(f"/herd/{theirs}").status_code == 404


def test_status_property(app_ctx):
    animal = Livestock()
    assert animal.status == "ON_FARM"
    animal.commercial_records = [CommercialInfo(transaction_type="BUY")]
    assert animal.status == "ON_FARM"
    animal.commercial_records.append(CommercialInfo(transaction_type="SELL"))
    assert animal.status == "SOLD"
    animal.mortality_record = MortalityRecord()
    assert animal.status == "DIED"