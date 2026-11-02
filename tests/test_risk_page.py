"""The farmer's Illness risk page."""
from datetime import date, timedelta

import joblib
import pytest

import ml.predict
from app.extensions import db
from app.models import HealthRecord
from ml.predict import reasons
from ml.train import build_table, train
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal


@pytest.fixture(scope="module")
def model_file(tmp_path_factory):
    """A small trained model saved to a file, like python -m ml.train does."""
    path = tmp_path_factory.mktemp("model") / "illness_model.joblib"
    joblib.dump(train(build_table(end=date(2026, 9, 30), years=1, seed=1))[0], path)
    return path


def test_reasons_are_written_in_plain_words():
    assert reasons({"illnesses_last_year": 2, "days_since_deworming": 365}) == [
        "Ill 2 times in the last year", "No deworming recorded in the last year"]
    assert reasons({"illnesses_last_year": 1, "days_since_deworming": 120}) == [
        "Ill 1 time in the last year", "Last dewormed 120 days ago"]
    assert reasons({"illnesses_last_year": 0, "days_since_deworming": 20}) == ["No warning signs in the records"]


def test_the_farmer_sees_every_animal_with_its_level_and_why(app, client, model_file, monkeypatch):
    monkeypatch.setattr(ml.predict, "MODEL_PATH", model_file)
    farm_with_worker(client)
    as_farmer(client)
    sickly = add_animal(app, "G001", date_of_birth=date.today() - timedelta(days=900))
    add_animal(app, "G002", date_of_birth=date.today() - timedelta(days=900))
    with app.app_context():
        for days_ago in (40, 120, 200):
            db.session.add(HealthRecord(animal_id=sickly, date=date.today() - timedelta(days=days_ago),
                                        record_type="ILLNESS", disease="Pneumonia"))
        db.session.commit()
    assert b"Illness risk" in client.get("/dashboard").data
    page = client.get("/risk?level=All").data.decode()
    assert "G001" in page and "G002" in page and "Ill 3 times in the last year" in page
    assert page.index("G001") < page.index("G002")             # riskiest first
    assert "All &middot; 2" in page


def test_workers_cannot_open_it(client):
    farm_with_worker(client)
    as_worker(client)
    assert client.get("/risk").headers["Location"].endswith("/dashboard")


def test_a_helpful_message_before_the_model_is_trained(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ml.predict, "MODEL_PATH", tmp_path / "not_there.joblib")
    farm_with_worker(client)
    as_farmer(client)
    assert b"python -m ml.train" in client.get("/risk").data