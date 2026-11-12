"""The Disease alerts page (ml/alerts.py and the /alerts route).

A fake model stands in for the trained one, so these tests don't need the
pickle file and every chance is known in advance."""
from datetime import date, timedelta

import numpy as np
import pytest

import ml.alerts
from app.extensions import db
from app.models import Farmer, HealthRecord, HerdActivity
from ml.alerts import farm_alerts
from ml.disease_data import FEATURES
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal, farm_id_of, farmer_logged_in

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


# ------------------------------------------------------------------ El Nino

def test_the_farmer_turns_el_nino_on_and_off(app, client):
    cattle_farm(app, client)
    assert b"Turn on" in client.get("/alerts").data
    page = client.post("/alerts/el-nino", follow_redirects=True).data
    assert b"El Ni\xc3\xb1o forecast turned on." in page and b"Turn off" in page
    assert b"Before the rains" in page and b"a month before the October rains" in page
    with app.app_context():
        assert Farmer.query.get(farm_id_of()).el_nino_forecast is True
    client.post("/alerts/el-nino")
    with app.app_context():
        assert Farmer.query.get(farm_id_of()).el_nino_forecast is False


def test_the_switch_only_reaches_the_model_from_october_to_january(app, client):
    cattle_farm(app, client)
    bundle = fake_bundle()
    with app.app_context():
        farm_alerts(farm_id_of(), el_nino=True, today=date(2026, 11, 1), bundle=bundle)
        assert bundle["model"].rows["el_nino"].eq(1).all()
        farm_alerts(farm_id_of(), el_nino=True, today=date(2026, 7, 1), bundle=bundle)
        assert bundle["model"].rows["el_nino"].eq(0).all()


def test_el_nino_flags_rift_valley_fever_on_the_watch_list(app, client):
    cattle_farm(app, client)
    with app.app_context():
        flags = {w["disease"]: w["flags"] for w in farm_alerts(farm_id_of(), el_nino=True)["watch_list"]}
    assert "El Niño forecast" in flags["Rift Valley Fever"]
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