"""Tests for the finished simulator (ml/synthetic.py, ml/simulator/weights.py)."""
from datetime import date

import pandas as pd
import pytest

from ml.reference import CONDITIONS, GROWTH, WEIGH_DAYS_PER_YEAR
from ml.simulator.weights import expected_weight
from ml.synthetic import FARM_PLANS, simulate_farm, simulate_farms

END = date(2026, 9, 30)
TABLES = {
    "livestock": ["animal_id", "tag_number", "species", "gender", "breed", "date_of_birth", "b_record_id"],
    "health": ["animal_id", "date", "record_type", "disease", "temperature",
               "description", "treatment", "dosage"],
    "weights": ["animal_id", "date", "weight"],
    "mortality": ["animal_id", "date_of_death", "age_at_death", "cause_of_death", "description"],
}


@pytest.fixture(scope="module")
def farms():
    """Three one-year farms, one per vaccination plan (shared by the tests)."""
    return simulate_farms(end=END, years=1, seed=5)


def test_one_farm_has_every_table_with_database_columns():
    tables = simulate_farm(end=END, years=1, seed=1)
    assert set(tables) == {"livestock", "breeding", "mortality", "commercial",
                           "health", "herd_activities", "weights"}
    for name, columns in TABLES.items():
        assert list(tables[name].columns) == columns


def test_growth_curve_rises_and_levels_off():
    for species, g in GROWTH.items():
        assert expected_weight(species, 0) == pytest.approx(g["birth"])
        assert expected_weight(species, g["grown_by"]) == pytest.approx(
            g["birth"] + 0.9 * (g["adult"] - g["birth"]))
        assert expected_weight(species, 3000) <= g["adult"]


def test_animals_are_weighed_only_a_few_times_a_year(farms):
    weights = farms["weights"]
    assert (weights["weight"] > 0).all()
    days_per_farm = weights.groupby("farm")["date"].nunique()
    # 4 species x 2 weigh days, spread over the calendar years the run touches.
    assert (days_per_farm <= 4 * WEIGH_DAYS_PER_YEAR * 2).all()


def test_farms_are_stacked_with_unique_ids(farms):
    livestock = farms["livestock"]
    assert set(livestock["farm"]) == set(FARM_PLANS)
    assert livestock["animal_id"].is_unique
    # Every health record points at an animal on the same farm.
    merged = farms["health"].merge(livestock[["animal_id", "farm"]], on="animal_id",
                                   suffixes=("", "_animal"))
    assert len(merged) == len(farms["health"])
    assert (merged["farm"] == merged["farm_animal"]).all()


def test_each_farm_gives_only_the_vaccines_in_its_plan(farms):
    vaccinations = farms["health"][farms["health"]["record_type"] == "VACCINATION"]
    for farm, given in vaccinations.groupby("farm")["treatment"]:
        assert set(given) <= set(FARM_PLANS[farm])


def test_vaccinating_more_means_fewer_vaccine_preventable_illnesses():
    group_a = {c.name for conditions in CONDITIONS.values() for c in conditions if c.group == "A"}
    data = simulate_farms(end=END, years=1, seed=11,
                          plans={"full": FARM_PLANS["full"], "minimal": FARM_PLANS["minimal"]})
    ill = data["health"][(data["health"]["record_type"] == "ILLNESS")
                         & data["health"]["disease"].isin(group_a)]
    counts = ill.groupby("farm").size()
    assert counts.get("full", 0) < counts["minimal"]


def test_same_seed_gives_the_same_farm():
    first = simulate_farm(end=END, years=1, seed=3)
    second = simulate_farm(end=END, years=1, seed=3)
    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])