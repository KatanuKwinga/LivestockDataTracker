"""Purchases, sales and deaths: the records that can take an animal off the farm."""
from datetime import date, timedelta

from app.extensions import db
from app.models import CommercialInfo, Livestock, MortalityRecord
from tests.conftest import register_farmer
from tests.test_herd import tags_on
from tests.test_records import add_worker_and_log_in_as_them
from tests.test_records_general import add_animal, farmer_logged_in


def sale(**changes):
    data = {"transaction_type": "SELL", "date": "2026-10-01", "amount": "12500",
            "other_party": "Kiserian market", "location": "Farm gate", "confirm": "y"}
    data.update(changes)
    return data


def death(**changes):
    data = {"date_of_death": "2026-10-01", "cause_of_death": "Pneumonia",
            "description": "Coughing for a week", "confirm": "y"}
    data.update(changes)
    return data


def without(data, key):
    """The form data with one box left out, as a browser sends an unticked checkbox."""
    return {k: v for k, v in data.items() if k != key}


def status_of(app, animal_id):
    with app.app_context():
        return db.session.get(Livestock, animal_id).status


# -------------------------------------------------------------------- sales

def test_commercial_and_mortality_tiles_lead_to_choosing_an_animal(client):
    farmer_logged_in(client)
    page = client.get("/records/add/goat").data
    assert b"/records/add/goat/commercial" in page and b"/records/add/goat/mortality" in page
    assert client.get("/records/add/goat/commercial").status_code == 200
    assert client.get("/records/add/goat/mortality").status_code == 200


def test_recording_a_sale_takes_the_animal_off_the_farm(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    add_animal(app, "G002")

    response = client.post(f"/records/add/goat/commercial/{goat}", data=sale())

    assert response.headers["Location"].endswith(f"/records/saved/{goat}/commercial")
    with app.app_context():
        record = CommercialInfo.query.one()
        assert (record.transaction_type, record.amount, record.other_party) == ("SELL", 12500, "Kiserian market")
    assert status_of(app, goat) == "SOLD"
    saved = client.get(response.headers["Location"]).data
    assert b"KES 12,500" in saved and b"Sold to" in saved
    assert tags_on(client.get("/herd/").data) == [b"G002"]
    assert tags_on(client.get("/herd/?status=sold").data) == [b"G001"]


def test_a_sale_must_be_confirmed(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    response = client.post(f"/records/add/goat/commercial/{goat}", data=without(sale(), "confirm"))
    assert b"Tick the box to confirm the sale" in response.data
    assert status_of(app, goat) == "ON_FARM"


def test_a_purchase_needs_no_confirmation_and_keeps_the_animal(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    response = client.post(f"/records/add/goat/commercial/{goat}",
                           data=without(sale(transaction_type="BUY", other_party="Kajiado market"), "confirm"))
    assert response.status_code == 302
    assert status_of(app, goat) == "ON_FARM"
    assert b"Bought from" in client.get(response.headers["Location"]).data


def test_prices_and_dates_are_checked(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", date_of_birth=date(2025, 3, 1))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    cases = [
        (sale(amount="-50"), b"price can&#39;t be negative"),
        (sale(amount=""), b"Enter the price in KES"),
        (sale(date=tomorrow), b"can&#39;t be in the future"),
        (sale(date="2025-01-01"), b"was born on 01 Mar 2025"),
    ]
    for data, message in cases:
        assert message in client.post(f"/records/add/goat/commercial/{goat}", data=data).data
    with app.app_context():
        assert CommercialInfo.query.count() == 0
    # A gift is a sale for nothing: 0 is allowed.
    assert client.post(f"/records/add/goat/commercial/{goat}", data=sale(amount="0")).status_code == 302


def test_a_sold_animal_cannot_be_sold_again(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/commercial/{goat}", data=sale())
    again = client.post(f"/records/add/goat/commercial/{goat}", data=sale())
    assert again.headers["Location"].endswith(f"/herd/{goat}")
    with app.app_context():
        assert CommercialInfo.query.count() == 1


# ------------------------------------------------------------------- deaths

def test_recording_a_death(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", date_of_birth=date(2023, 11, 15))

    response = client.post(f"/records/add/goat/mortality/{goat}", data=death())

    assert response.headers["Location"].endswith(f"/records/saved/{goat}/mortality")
    with app.app_context():
        record = MortalityRecord.query.one()
        assert (record.date_of_death, record.cause_of_death) == (date(2026, 10, 1), "Pneumonia")
        assert record.age_at_death == 2          # 15 Nov 2023 to 1 Oct 2026: not yet 3
    assert status_of(app, goat) == "DIED"
    saved = client.get(response.headers["Location"]).data
    assert b"Pneumonia" in saved and b"2 years" in saved and b"01 Oct 2026" in saved


def test_age_at_death_is_left_empty_when_the_birth_date_is_unknown(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/mortality/{goat}", data=death())
    with app.app_context():
        assert MortalityRecord.query.one().age_at_death is None


def test_a_death_needs_a_cause_and_a_confirmation(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    no_cause = client.post(f"/records/add/goat/mortality/{goat}", data=death(cause_of_death=""))
    unconfirmed = client.post(f"/records/add/goat/mortality/{goat}", data=without(death(), "confirm"))
    assert b"Write the cause" in no_cause.data
    assert b"Tick the box to confirm" in unconfirmed.data
    assert status_of(app, goat) == "ON_FARM"


def test_a_dead_animal_cannot_die_again_or_be_sold(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/mortality/{goat}", data=death())
    for url, data in ((f"/records/add/goat/mortality/{goat}", death()), (f"/records/add/goat/commercial/{goat}", sale())):
        response = client.post(url, data=data)
        assert response.headers["Location"].endswith(f"/herd/{goat}")
    with app.app_context():
        assert MortalityRecord.query.count() == 1 and CommercialInfo.query.count() == 0


def test_a_worker_can_record_a_death(app, client):
    add_worker_and_log_in_as_them(client)
    goat = add_animal(app, "G001")
    assert client.post(f"/records/add/goat/mortality/{goat}", data=death()).status_code == 302
    assert status_of(app, goat) == "DIED"


def test_another_farms_animal_is_not_found(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)
    assert client.post(f"/records/add/goat/commercial/{theirs}", data=sale()).status_code == 404
    assert client.post(f"/records/add/goat/mortality/{theirs}", data=death()).status_code == 404
    assert status_of(app, theirs) == "ON_FARM"