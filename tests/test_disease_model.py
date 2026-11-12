"""Tests for the disease-alert model's training code (ml/disease_model.py).
Uses a small simulated table, so it runs in under a minute."""
from datetime import date

import pytest

from ml.disease_data import FEATURES, LABEL
from ml.disease_model import SeasonalCalendar, boosting, last_year_rule, load_bundle, save_bundle, simulated_table, split


@pytest.fixture(scope="module")
def table():
    rows, _ = simulated_table(farms=3, end=date(2026, 9, 30), years=2)
    return rows


def test_split_keeps_test_days_after_learning_days_and_unseen_farms_out(table):
    learn, later, new = split(table, test_farms=1)
    assert learn["snapshot"].max() < later["snapshot"].min()
    assert set(new["farm"]).isdisjoint(set(learn["farm"]))
    assert len(learn) + len(later) + len(new) < len(table)            # the unseen farm's early days are unused


def test_the_rules_score_every_row(table):
    calendar = SeasonalCalendar().fit(table)
    chance = calendar.predict(table)
    assert ((chance >= 0) & (chance <= 1)).all()
    assert (last_year_rule(table) >= 0).all()


def test_the_model_trains_saves_and_loads(table, tmp_path):
    model = boosting().fit(table[FEATURES], table[LABEL])
    path = tmp_path / "disease_model.pkl"
    save_bundle(model, {"roc_auc_same_farms": 0.8}, path)
    bundle = load_bundle(path)
    chance = bundle["model"].predict_proba(table[bundle["columns"]].head(5))[:, 1]
    assert ((chance >= 0) & (chance <= 1)).all()
    assert bundle["label"] == LABEL and bundle["horizon_days"] == 30


## `tests/test_farm_records.py`
"""Tests for reading the demo farm's and Kwetu's workbooks (ml/farm_records.py)."""
import pytest

from ml.farm_records import DEMO_WORKBOOK, KWETU_WORKBOOK, demo_farm, kwetu, kwetu_disease


def test_kwetus_own_words_are_matched_to_the_models_diseases():
    assert kwetu_disease("East Coast Fever (treated with Bupalex)") == "East Coast Fever"
    assert kwetu_disease("Lung problem (breathing heavily)") == "Pneumonia"
    assert kwetu_disease("Sick (not stated)") is None
    assert kwetu_disease(None) is None


@pytest.mark.skipif(not DEMO_WORKBOOK.exists(), reason="demo workbook not in this checkout")
def test_the_demo_farm_reads_into_the_simulator_tables():
    data = demo_farm()
    assert {"livestock", "breeding", "health", "mortality", "commercial", "departures", "herd_activities"} <= set(data)
    assert data["livestock"]["animal_id"].is_unique
    assert (data["health"]["record_type"] == "ILLNESS").sum() > 100


@pytest.mark.skipif(not KWETU_WORKBOOK.exists(), reason="Kwetu workbook not in this checkout")
def test_kwetu_reads_and_keeps_only_illnesses_the_model_knows():
    data = kwetu()
    ill = data["health"][data["health"]["record_type"] == "ILLNESS"]
    assert set(ill["disease"].dropna()) <= {"East Coast Fever", "Calf scours", "Orf", "Pneumonia", "Vulval infection"}