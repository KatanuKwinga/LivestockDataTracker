"""Tests for the herd part of the simulator (ml/sim/farm.py, ml/sim/herd.py)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from ml.reference import FIRST_BIRTH_AGE_DAYS, GESTATION_DAYS, START_HERD
from ml.simulator.farm import Farm, run
from ml.simulator.herd import births_step, sales_step, starting_herd

START, END = date(2024, 10, 1), date(2026, 9, 30)   # two years


def simulate(seed=1):
    farm = Farm(START, END, seed=seed)
    starting_herd(farm)
    return run(farm, [births_step, sales_step])


@pytest.fixture(scope="module")
def farm():
    """One two-year run shared by the tests below (simulating is the slow part)."""
    return simulate()


def test_starting_herd_matches_kwetu_head_count():
    farm = Farm(START, END)
    starting_herd(farm)
    for species, groups in START_HERD.items():
        assert len(farm.on_farm(species)) == sum(groups.values())
    assert all(a.date_of_birth < START for a in farm.animals)


def test_tags_are_unique_and_use_the_species_prefix(farm):
    livestock = farm.tables()["livestock"]
    assert livestock["tag_number"].is_unique
    goats = livestock[livestock["species"] == "GOAT"]
    assert goats["tag_number"].str.match(r"^G\d{3}$").all()


def test_births_happen_and_link_newborns_to_their_mother(farm):
    tables = farm.tables()
    breeding, livestock = tables["breeding"], tables["livestock"]
    assert len(breeding) > 50
    newborns = livestock[livestock["b_record_id"].notna()]
    assert len(newborns) >= len(breeding)           # twins give two newborns per record
    births = newborns.merge(breeding, on="b_record_id")
    assert (births["date_of_birth"] == births["actual_delivery_date"]).all()


def test_only_grown_females_give_birth_and_not_too_often(farm):
    animals = {a.animal_id: a for a in farm.animals}
    breeding = farm.tables()["breeding"].sort_values("actual_delivery_date")
    for dam_id, events in breeding.groupby("animal_id"):
        dam = animals[dam_id]
        assert dam.gender == "FEMALE"
        first = events["actual_delivery_date"].iloc[0]
        assert dam.age_days(first) >= FIRST_BIRTH_AGE_DAYS[dam.species]
        gaps = pd.Series(events["actual_delivery_date"]).diff().dropna()
        assert (gaps >= timedelta(days=GESTATION_DAYS[dam.species])).all()


def test_weak_newborns_die_within_two_weeks_of_birth(farm):
    animals = {a.animal_id: a for a in farm.animals}
    mortality = farm.tables()["mortality"]
    assert len(mortality) > 0
    for row in mortality.itertuples():
        assert row.cause_of_death == "Weak at birth / starvation"
        assert 0 <= (row.date_of_death - animals[row.animal_id].date_of_birth).days <= 14


def test_sales_are_grown_males_sold_in_december(farm):
    animals = {a.animal_id: a for a in farm.animals}
    sales = farm.tables()["commercial"]
    assert len(sales) > 10
    assert (sales["transaction_type"] == "SELL").all()
    assert all(d.month == 12 for d in sales["date"])
    assert all(animals[i].gender == "MALE" for i in sales["animal_id"])


def test_nobody_gives_birth_after_leaving_the_farm(farm):
    animals = {a.animal_id: a for a in farm.animals}
    for row in farm.tables()["breeding"].itertuples():
        dam = animals[row.animal_id]
        assert dam.exit_date is None or row.actual_delivery_date <= dam.exit_date


def test_same_seed_gives_the_same_farm():
    first, second = simulate(seed=7).tables(), simulate(seed=7).tables()
    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])
