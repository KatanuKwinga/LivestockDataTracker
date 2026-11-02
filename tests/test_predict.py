from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import CommercialInfo, HealthRecord
from ml.predict import predict_farm, risk_level
from ml.train import build_table, train
from tests.conftest import register_farmer
from tests.test_records_general import add_animal, farm_id_of

TODAY = date(2026, 11, 2)


@pytest.fixture(scope="module")
def model():
    """A small model trained on one simulated year (enough for these tests)."""
    return train(build_table(end=date(2026, 9, 30), years=1, seed=1))[0]


def test_chances_become_low_medium_or_high():
    assert [risk_level(c) for c in (0.03, 0.06, 0.09, 0.10, 0.40)] == ["Low", "Medium", "Medium", "High", "High"]


def test_only_this_farms_animals_still_on_the_farm_are_scored(app, client, model):
    register_farmer(client)
    register_farmer(client, name="Other Farmer", email="other@example.com")
    born = TODAY - timedelta(days=900)
    sickly = add_animal(app, "G001", date_of_birth=born)
    healthy = add_animal(app, "G002", date_of_birth=born)
    sold = add_animal(app, "G003", date_of_birth=born)
    add_animal(app, "G900", email="other@example.com", date_of_birth=born)
    with app.app_context():
        for days_ago in (40, 120, 200):            # ill three times in the last year
            db.session.add(HealthRecord(animal_id=sickly, date=TODAY - timedelta(days=days_ago),
                                        record_type="ILLNESS", disease="Pneumonia"))
        db.session.add(CommercialInfo(animal_id=sold, transaction_type="SELL", date=TODAY - timedelta(days=10), amount=9000))
        db.session.commit()

        result = predict_farm(farm_id_of(), today=TODAY, model=model)

    assert sorted(result["tag"]) == ["G001", "G002"]            # not the sold goat, not the other farm's
    chance = dict(zip(result["tag"], result["chance"]))
    assert chance["G001"] > chance["G002"]                      # the sickly goat is riskier
    assert set(result["risk"]) <= {"Low", "Medium", "High"}
    assert result.iloc[0]["tag"] == "G001"                      # riskiest first


def test_a_new_farm_with_no_records_still_gets_a_prediction(app, client, model):
    register_farmer(client)
    add_animal(app, "C001", species="CATTLE")                  # no birth date, no records at all
    with app.app_context():
        result = predict_farm(farm_id_of(), today=TODAY, model=model)
    assert list(result["tag"]) == ["C001"] and result.iloc[0]["risk"] in {"Low", "Medium", "High"}