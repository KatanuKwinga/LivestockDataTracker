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