"""Animals that left the farm without a sale or a death: given away,
slaughtered at home, lost, stolen or missing at a head count."""
import io
from datetime import date, timedelta

from app.analytics import farm_analytics
from app.extensions import db
from app.models import Departure, Livestock
from ml.predict import farm_data, on_farm_today
from tests.conftest import register_farmer
from tests.test_herd import tags_on
from tests.test_records import add_worker_and_log_in_as_them
from tests.test_records_general import add_animal, farm_id_of, farmer_logged_in


def departure(**changes):
    data = {"reason": "GIVEN_AWAY", "date": "2026-10-01", "description": "To my brother in Machakos", "confirm": "y"}
    data.update(changes)
    return data


def status_of(app, animal_id):
    with app.app_context():
        return db.session.get(Livestock, animal_id).status


def give_away(app, animal_id, day=date(2026, 10, 1)):
    with app.app_context():
        db.session.add(Departure(animal_id=animal_id, date=day, reason="GIVEN_AWAY"))
        db.session.commit()


def test_a_worker_records_an_animal_given_away_and_it_leaves_the_herd(app, client):
    add_worker_and_log_in_as_them(client)
    goat = add_animal(app, "G001")
    add_animal(app, "G002")
    assert b"/records/add/goat/departure" in client.get("/records/add/goat").data

    response = client.post(f"/records/add/goat/departure/{goat}", data=departure())

    assert response.headers["Location"].endswith(f"/records/saved/{goat}/departure")
    assert status_of(app, goat) == "LEFT"
    saved = client.get(response.headers["Location"]).data
    assert b"Given away" in saved and b"To my brother in Machakos" in saved
    assert tags_on(client.get("/herd/").data) == [b"G002"]                     # off the herd list
    assert tags_on(client.get("/herd/?status=left").data) == [b"G001"]         # but findable
    detail = client.get(f"/herd/{goat}").data
    assert b"Left the farm" in detail and b"01 Oct 2026" in detail


def test_the_form_is_checked_before_anything_is_saved(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", date_of_birth=date(2025, 1, 1))
    url = f"/records/add/goat/departure/{goat}"
    no_tick = {k: v for k, v in departure().items() if k != "confirm"}     # an unticked box isn't sent
    assert b"Tick the box to confirm" in client.post(url, data=no_tick).data
    assert b"Write what happened" in client.post(url, data=departure(reason="OTHER", description="")).data
    assert b"born on 01 Jan 2025" in client.post(url, data=departure(date="2024-06-01")).data
    future = (date.today() + timedelta(days=2)).isoformat()
    assert b"can&#39;t be in the future" in client.post(url, data=departure(date=future)).data
    assert b"Not a valid choice" in client.post(url, data=departure(reason="EATEN_BY_LIONS")).data
    with app.app_context():
        assert Departure.query.count() == 0
    assert status_of(app, goat) == "ON_FARM"


def test_an_animal_that_left_cannot_get_new_records_or_leave_twice(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    give_away(app, goat)
    for category in ("health", "weight", "departure"):
        response = client.get(f"/records/add/goat/{category}/{goat}", follow_redirects=True)
        assert b"G001 has left the farm, so new records can&#39;t be added" in response.data
    with app.app_context():
        assert Departure.query.count() == 1


def test_another_farms_animal_cannot_be_recorded_as_left(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G009", email="other@example.com")
    farmer_logged_in(client)                                  # Jane, on her own farm
    assert client.post(f"/records/add/goat/departure/{theirs}", data=departure()).status_code == 404
    assert status_of(app, theirs) == "ON_FARM"


def test_analytics_csv_import_and_risk_model_all_count_it_as_gone(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", date_of_birth=date(2024, 1, 1))
    give_away(app, goat, day=date.today() - timedelta(days=40))
    with app.app_context():
        farm = farm_id_of()
        # Herd size (goats are species[1]): counted at the end of each month
        # before it left, not after. Fixed dates, so the months don't move.
        db.session.get(Departure, 1).date = date(2026, 9, 10)
        db.session.commit()
        goats = farm_analytics(farm, today=date(2026, 11, 2))["species"][1]["herd"]
        assert goats[-4:] == [1, 0, 0, 0]          # end of Aug, Sep, Oct, and today
        # The risk page only lists animals still on the farm.
        assert on_farm_today(farm_data(farm), date.today()).empty
    # A CSV of weights can't be dated after the animal left.
    text = f"tag_number,date,weight_kg\nG001,{date.today().isoformat()},30\n"
    page = client.post("/records/import/weights", data={"file": (io.BytesIO(text.encode()), "w.csv")},
                       content_type="multipart/form-data").data.decode()
    assert "G001 left the farm on" in page