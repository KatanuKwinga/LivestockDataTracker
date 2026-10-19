"""Breeding (mating, birth, loss) and production (milk, eggs) records."""
from datetime import date, timedelta

from app.extensions import db
from app.models import BreedingRecord, Livestock, ProductionData
from tests.conftest import register_farmer
from tests.test_records_general import add_animal, farmer_logged_in


def breeding(**changes):
    # Every box is sent, as the browser sends the hidden ones too.
    data = {"event": "MATED", "sire": "", "mated_on": "", "expected_date": "", "birth_date": "",
            "females_born": "0", "males_born": "0", "stillborn": "0"}
    data.update(changes)
    return data


def breeding_records(app):
    with app.app_context():
        return BreedingRecord.query.order_by(BreedingRecord.b_record_id).all()


# ---------------------------------------------------------------- choosing

def test_only_females_are_offered_for_breeding_and_production(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001", gender="FEMALE")
    add_animal(app, "G002", gender="MALE")
    for category in ("breeding", "production"):
        page = client.get(f"/records/add/goat/{category}").data
        assert b"G001</span>" in page and b"G002</span>" not in page
        assert b"Only females are listed" in page


def test_a_male_cannot_be_reached_by_typing_the_url(app, client):
    farmer_logged_in(client)
    billy = add_animal(app, "G002", gender="MALE")
    assert client.get(f"/records/add/goat/breeding/{billy}").status_code == 404
    assert client.get(f"/records/add/goat/production/{billy}").status_code == 404


# ----------------------------------------------------------------- mating

def test_recording_a_mating_works_out_the_due_date(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001")
    buck = add_animal(app, "G010", gender="MALE")

    response = client.post(f"/records/add/goat/breeding/{doe}", data=breeding(sire=str(buck), mated_on="2026-09-01"))

    assert response.headers["Location"].endswith(f"/records/saved/{doe}/breeding")
    [record] = breeding_records(app)
    assert (record.status, record.sire_id) == ("EXPECTANT", buck)
    assert record.expected_delivery_date == date(2026, 9, 1) + timedelta(days=150)     # goat gestation
    saved = client.get(response.headers["Location"]).data
    assert b"Expectant" in saved and b"29 Jan 2027" in saved and b"G010" in saved


def test_the_vets_due_date_wins_over_the_worked_out_one(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001")
    client.post(f"/records/add/goat/breeding/{doe}", data=breeding(mated_on="2026-09-01", expected_date="2027-02-05"))
    assert breeding_records(app)[0].expected_delivery_date == date(2027, 2, 5)


def test_only_this_farms_males_of_the_species_can_be_the_father(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    their_buck = add_animal(app, "G099", gender="MALE", email="other@example.com")
    farmer_logged_in(client)
    doe = add_animal(app, "G001")
    bull = add_animal(app, "C001", species="CATTLE", gender="MALE")

    page = client.get(f"/records/add/goat/breeding/{doe}").data
    assert b"G099" not in page and b"C001" not in page
    for intruder in (their_buck, bull):
        assert b"Not a valid choice" in client.post(f"/records/add/goat/breeding/{doe}", data=breeding(sire=str(intruder))).data
    assert breeding_records(app) == []


def test_a_pregnant_female_cannot_be_mated_again(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001")
    client.post(f"/records/add/goat/breeding/{doe}", data=breeding(expected_date="2027-01-20"))
    again = client.post(f"/records/add/goat/breeding/{doe}", data=breeding())
    assert b"already recorded as pregnant, due 20 Jan 2027" in again.data
    assert len(breeding_records(app)) == 1


# ------------------------------------------------------------------ births

def test_a_birth_closes_the_pregnancy_and_registers_the_young(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001", breed="Galla")
    buck = add_animal(app, "G010", gender="MALE", breed="Toggenburg")
    client.post(f"/records/add/goat/breeding/{doe}", data=breeding(sire=str(buck), mated_on="2026-04-01"))

    # The form now expects the birth, with the father already chosen.
    page = client.get(f"/records/add/goat/breeding/{doe}").data
    assert b"is recorded as pregnant" in page and f'<option selected value="{buck}">'.encode() in page

    response = client.post(f"/records/add/goat/breeding/{doe}",
                           data=breeding(event="BIRTH", sire=str(buck), birth_date="2026-08-29",
                                         females_born="1", males_born="1", stillborn="1"))

    [record] = breeding_records(app)                 # the same record, now closed
    assert (record.status, record.actual_delivery_date, record.num_stillborn) == ("SUCCESSFUL BIRTH", date(2026, 8, 29), 1)
    with app.app_context():
        young = Livestock.query.filter_by(b_record_id=record.b_record_id).order_by(Livestock.tag_number).all()
        assert [(k.tag_number, k.gender, k.breed, k.date_of_birth) for k in young] == [
            ("G011", "FEMALE", "Cross", date(2026, 8, 29)), ("G012", "MALE", "Cross", date(2026, 8, 29))]
    saved = client.get(response.headers["Location"]).data
    assert b"G011" in saved and b"G012" in saved and b"Born alive" in saved
    kid_page = client.get(f"/herd/{young[0].animal_id}").data
    assert b"Mother" in kid_page and b"G001" in kid_page and b"G010" in kid_page


def test_a_birth_can_be_recorded_without_a_recorded_pregnancy(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001", breed="Galla")
    client.post(f"/records/add/goat/breeding/{doe}", data=breeding(event="BIRTH", birth_date="2026-10-01", females_born="2"))
    with app.app_context():
        record = BreedingRecord.query.one()
        assert record.status == "SUCCESSFUL BIRTH" and record.num_born_alive == 2


def test_a_birth_needs_a_date_and_live_young(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001", date_of_birth=date(2024, 1, 1))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    cases = [
        (breeding(event="BIRTH", females_born="1"), b"Enter the date"),
        (breeding(event="BIRTH", birth_date="2026-10-01"), b"No live young?"),
        (breeding(event="BIRTH", birth_date=tomorrow, females_born="1"), b"can&#39;t be in the future"),
        (breeding(event="BIRTH", birth_date="2023-06-01", females_born="1"), b"was born on 01 Jan 2024"),
        (breeding(event="BIRTH", birth_date="2026-10-01", females_born="-1"), b"Number must be between 0 and 30"),
    ]
    for data, message in cases:
        assert message in client.post(f"/records/add/goat/breeding/{doe}", data=data).data
    assert breeding_records(app) == []


def test_a_lost_pregnancy_registers_no_young(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001")
    client.post(f"/records/add/goat/breeding/{doe}", data=breeding())
    client.post(f"/records/add/goat/breeding/{doe}", data=breeding(event="NO_BIRTH", birth_date="2026-10-01", stillborn="1"))
    with app.app_context():
        record = BreedingRecord.query.one()
        assert (record.status, record.num_stillborn, record.num_born_alive) == ("NO BIRTH", 1, 0)
        assert Livestock.query.count() == 1


# ------------------------------------------------------------- production

def test_recording_milk(app, client):
    farmer_logged_in(client)
    cow = add_animal(app, "C001", species="CATTLE")

    response = client.post(f"/records/add/cattle/production/{cow}", data={"date": "2026-10-01", "amount": "12.5"})

    assert response.headers["Location"].endswith(f"/records/saved/{cow}/production")
    with app.app_context():
        record = ProductionData.query.one()
        assert (record.item, record.yield_amount, record.metric) == ("Milk", 12.5, "L")
    assert b"12.5 L" in client.get(response.headers["Location"]).data
    assert b"Last recorded on 01 Oct 2026" in client.get(f"/records/add/cattle/production/{cow}").data


def test_hens_lay_whole_eggs(app, client):
    farmer_logged_in(client)
    hen = add_animal(app, "CH001", species="CHICKEN")
    assert b"Eggs laid" in client.get(f"/records/add/chicken/production/{hen}").data
    assert b"Count whole eggs" in client.post(f"/records/add/chicken/production/{hen}", data={"date": "2026-10-01", "amount": "1.5"}).data
    client.post(f"/records/add/chicken/production/{hen}", data={"date": "2026-10-01", "amount": "1"})
    with app.app_context():
        assert (ProductionData.query.one().item, ProductionData.query.one().metric) == ("Eggs", "eggs")


def test_one_production_record_per_day_and_believable_amounts(app, client):
    farmer_logged_in(client)
    doe = add_animal(app, "G001")
    client.post(f"/records/add/goat/production/{doe}", data={"date": "2026-10-01", "amount": "2"})
    twice = client.post(f"/records/add/goat/production/{doe}", data={"date": "2026-10-01", "amount": "1"})
    too_much = client.post(f"/records/add/goat/production/{doe}", data={"date": "2026-10-02", "amount": "40"})
    negative = client.post(f"/records/add/goat/production/{doe}", data={"date": "2026-10-02", "amount": "-1"})
    assert b"already has a milk record for 01 Oct 2026 (2 L)" in twice.data
    assert b"More than 10 L in a day" in too_much.data
    assert b"can&#39;t be negative" in negative.data
    with app.app_context():
        assert ProductionData.query.count() == 1


def test_another_farms_female_is_not_found(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)
    assert client.post(f"/records/add/goat/breeding/{theirs}", data=breeding()).status_code == 404
    assert client.post(f"/records/add/goat/production/{theirs}", data={"date": "2026-10-01", "amount": "2"}).status_code == 404