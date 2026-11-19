"""The Disease alerts page (ml/alerts.py and the /alerts route).

A fake model stands in for the trained one, so these tests don't need the
pickle file and every chance is known in advance."""
from datetime import date, timedelta

import numpy as np
import pytest

import ml.alerts
import app.routes.main as app_routes_main
from app.extensions import db
from app.models import HealthRecord, HerdActivity
from ml.alerts import farm_alerts
from ml.disease_data import FEATURES
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal, farm_id_of, farmer_logged_in
from tests.test_weather import fake_weather, set_location

TODAY = date.today()
CHANCES = {"East Coast Fever": 0.62, "Gastrointestinal worms": 0.31}    # everything else 0.05


class FakeModel:
    """Gives each disease a fixed chance, and remembers the rows it was given."""
    def predict_proba(self, rows):
        self.rows = rows.copy()
        chance = rows["disease"].map(CHANCES).fillna(0.05).to_numpy()
        return np.column_stack([1 - chance, chance])


def fake_bundle():
    return {"model": FakeModel(), "columns": FEATURES, "trained_on": "2026-11-12",
            "metrics": {"high_from": 0.5, "watch_from": 0.2}}


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(ml.alerts, "load_model", fake_bundle)


def cattle_farm(app, client):
    farmer_logged_in(client)
    cow = add_animal(app, "C001", species="CATTLE", date_of_birth=TODAY - timedelta(days=4 * 365))
    add_animal(app, "C002", species="CATTLE", gender="MALE", date_of_birth=TODAY - timedelta(days=60))
    return cow


def add_record(app, record):
    with app.app_context():
        db.session.add(record)
        db.session.commit()


# ------------------------------------------------------------------ the page

def test_only_the_farmer_sees_the_alerts(client):
    farm_with_worker(client)
    as_worker(client)
    assert client.get("/alerts").headers["Location"].endswith("/dashboard")
    as_farmer(client)
    assert client.get("/alerts").status_code == 200


def test_a_message_before_the_model_is_trained(client, monkeypatch):
    def no_file():
        raise FileNotFoundError
    monkeypatch.setattr(ml.alerts, "load_model", no_file)
    farmer_logged_in(client)
    assert b"hasn't been trained yet" in client.get("/alerts").data


def test_each_group_gets_its_alerts_with_level_reasons_and_advice(app, client):
    cow = cattle_farm(app, client)
    add_record(app, HealthRecord(animal_id=cow, date=TODAY - timedelta(days=5), record_type="ILLNESS",
                                 disease="East Coast Fever", treatment="Butalex"))
    page = client.get("/alerts").data.decode()
    assert "Adult cattle" in page and "Calves" in page
    assert "East Coast Fever" in page and "62%" in page and ">High<" in page
    assert "Gastrointestinal worms" in page and ">Watch<" in page
    assert "1 case on the farm in the last 30 days" in page
    assert "Deworm at the start of the rains" in page            # the advice from ml/reference.py
    assert "Lumpy skin disease" not in page.split("Watch list")[0]   # 5%: Low, not listed


def test_only_this_farms_animals_count(app, client):
    cattle_farm(app, client)
    client.post("/auth/logout")
    farmer_logged_in_as_other(client)
    add_animal(app, "C001", species="CATTLE", email="other@example.com",
               date_of_birth=TODAY - timedelta(days=4 * 365))
    with app.app_context():
        alerts = farm_alerts(farm_id_of("other@example.com"))
    assert [(g["group"], g["size"]) for g in alerts["groups"]] == [("Adult cattle", 1)]


def farmer_logged_in_as_other(client):
    client.post("/auth/register", data={"name": "Otieno Farmer", "email": "other@example.com", "phone": "",
                                        "password": "password123", "confirm_password": "password123"})


# ------------------------------------------------------------------ the rain

def test_the_models_rain_clues_come_from_the_farms_weather(app, client):
    cattle_farm(app, client)
    bundle = fake_bundle()
    weather = fake_weather(past_mm=5.0, forecast_mm=10.0)          # 150 mm in 30 days, 160 forecast
    with app.app_context():
        alerts = farm_alerts(farm_id_of(), weather=weather, bundle=bundle)
    rows = bundle["model"].rows
    assert rows["rain_last_30_days"].eq(150).all() and rows["rain_next_16_days"].eq(160).all()
    assert alerts["rain"]["last_30_days"] == 150 and alerts["rain"]["live"] is True


def test_without_the_weather_the_rain_is_left_unknown(app, client):
    cattle_farm(app, client)
    bundle = fake_bundle()
    with app.app_context():
        alerts = farm_alerts(farm_id_of(), weather=None, bundle=bundle)
    assert bundle["model"].rows["rain_last_30_days"].isna().all()
    assert alerts["rain"] == {"live": False, "last_30_days": None, "next_16_days": None, "heavy": False}
    assert alerts["groups"]                                         # the alerts still come


def test_a_banner_asks_for_the_farms_location(app, client):
    cattle_farm(app, client)
    page = client.get("/alerts").data
    assert b"Set your farm's location to add its rainfall to the alerts" in page
    set_location(app)
    page = client.get("/alerts").data                               # set, but the service can't be reached
    assert b"Set your farm's location to add" not in page and b"can't be reached right now" in page


def test_heavy_rain_brings_the_advice_and_flags_rift_valley_fever(app, client):
    cattle_farm(app, client)
    with app.app_context():
        alerts = farm_alerts(farm_id_of(), weather=fake_weather(past_mm=10.0, forecast_mm=2.0))   # 300 mm
    assert alerts["rain"]["heavy"] and any("lumpy skin" in line for line in alerts["heavy_rain_advice"])
    flags = {w["disease"]: w["flags"] for w in alerts["watch_list"]}
    assert "Heavy rain" in flags["Rift Valley Fever"]
    with app.app_context():
        dry = farm_alerts(farm_id_of(), weather=fake_weather(past_mm=1.0, forecast_mm=1.0))
    assert not dry["rain"]["heavy"] and dry["heavy_rain_advice"] == []


def test_heavy_rain_is_given_as_a_reason(app, client, monkeypatch):
    cattle_farm(app, client)
    set_location(app)
    monkeypatch.setattr(app_routes_main, "get_weather", lambda lat, lon: fake_weather(past_mm=10.0, forecast_mm=6.0))
    page = client.get("/alerts").data.decode()
    assert "Very heavy rain: 300 mm in the last 30 days" in page
    assert "96 mm of rain forecast for the next 16 days" in page


def test_no_vaccination_in_the_last_year_is_flagged_on_the_watch_list(app, client):
    cattle_farm(app, client)
    with app.app_context():
        flags = {w["disease"]: w["flags"] for w in farm_alerts(farm_id_of())["watch_list"]}
    assert "No vaccination in the last year" in flags["Foot and Mouth Disease"]


def test_a_recent_vaccination_clears_the_watch_list_flag(app, client):
    cow = cattle_farm(app, client)
    add_record(app, HealthRecord(animal_id=cow, date=TODAY - timedelta(days=30), record_type="VACCINATION",
                                 treatment="FMD vaccine"))
    with app.app_context():
        flags = {w["disease"]: w["flags"] for w in farm_alerts(farm_id_of())["watch_list"]}
    assert flags["Foot and Mouth Disease"] == []


# ------------------------------------------------------------------ spraying

def spray(app, days_ago):
    add_record(app, HerdActivity(farmer_id=farm_id_of(), species="CATTLE", activity="TICK_SPRAY",
                                 date=TODAY - timedelta(days=days_ago)))


def test_a_gap_in_spraying_gives_a_warning(app, client):
    cattle_farm(app, client)
    with app.app_context():
        for days_ago in (20, 17, 5, 2):          # nothing between 17 and 5 days ago: 12 days
            spray(app, days_ago)
        warnings = farm_alerts(farm_id_of())["spraying"]
    assert len(warnings) == 1 and "went 12 days without tick spraying" in warnings[0]["text"]
    assert "East Coast Fever" in warnings[0]["text"]


def test_spraying_on_time_gives_no_warning(app, client):
    cattle_farm(app, client)
    with app.app_context():
        for days_ago in range(1, 30, 3):
            spray(app, days_ago)
        assert farm_alerts(farm_id_of())["spraying"] == []


def test_no_spraying_recorded_asks_the_farmer_to_record_it(app, client):
    cattle_farm(app, client)
    assert b"No tick spraying recorded for the cattle" in client.get("/alerts").data


def test_the_home_page_links_to_the_alerts(client):
    farmer_logged_in(client)
    assert b'href="/alerts"' in client.get("/dashboard").data