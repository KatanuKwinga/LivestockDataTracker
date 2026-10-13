"""Tests for farm routines (ml/simulator/routines.py)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from ml.reference import DEWORM_EVERY_DAYS, VACCINES
from ml.simulator.farm import Animal, Farm, run
from ml.simulator.herd import births_step, sales_step, starting_herd
from ml.simulator.routines import (
    deworming_step, spraying_step, vaccination_step, vaccine_status,
)

START, END = date(2024, 10, 1), date(2026, 9, 30)


def simulate(seed=1):
    farm = Farm(START, END, seed=seed)
    starting_herd(farm)
    return run(farm, [births_step, sales_step, vaccination_step, deworming_step, spraying_step])


@pytest.fixture(scope="module")
def farm():
    return simulate()


@pytest.fixture(scope="module")
def health(farm):
    animals = pd.DataFrame([vars(a) for a in farm.animals])[
        ["animal_id", "species", "date_of_birth", "exit_date"]]
    return farm.tables()["health"].merge(animals, on="animal_id")


def test_vaccines_match_the_species_and_minimum_age(health):
    vaccinations = health[health["record_type"] == "VACCINATION"]
    assert len(vaccinations) > 500
    for row in vaccinations.itertuples():
        vaccine = VACCINES[row.treatment]
        assert row.species in vaccine["species"]
        assert (row.date - row.date_of_birth).days >= vaccine["first_dose_days"]


def test_once_only_vaccines_are_never_repeated(health):
    fowl_pox = health[health["treatment"] == "Fowl pox vaccine"]
    assert fowl_pox["animal_id"].is_unique


def test_some_vaccinations_run_late(farm):
    # With 70% on time, some animals must be overdue at some point.
    overdue = [a for a in farm.on_farm("GOAT") if vaccine_status(a, "FMD vaccine", END) == "overdue"]
    assert 0 < len(overdue) < len(farm.on_farm("GOAT"))


def test_vaccine_status_rules():
    calf = Animal(1, "C001", "CATTLE", "FEMALE", "Boran", date(2026, 1, 1))
    calf.vaccine_due["FMD vaccine"] = date(2026, 1, 1)
    calf.vaccine_doses["FMD vaccine"] = 0
    assert vaccine_status(calf, "FMD vaccine", date(2026, 1, 1)) == "not_yet"
    assert vaccine_status(calf, "FMD vaccine", date(2026, 2, 1)) == "overdue"
    calf.vaccine_doses["FMD vaccine"] = 1
    calf.vaccine_due["FMD vaccine"] = date(2026, 7, 1)
    assert vaccine_status(calf, "FMD vaccine", date(2026, 3, 1)) == "up_to_date"


def test_deworming_is_done_by_group_at_least_90_days_apart(health):
    deworming = health[health["description"] == "Routine deworming"]
    goat_sessions = sorted(set(deworming[deworming["species"] == "GOAT"]["date"]))
    gaps = [(b - a).days for a, b in zip(goat_sessions, goat_sessions[1:])]
    assert len(goat_sessions) >= 6
    assert min(gaps) >= DEWORM_EVERY_DAYS
    assert all(r == "TREATMENT" for r in deworming["record_type"])


def test_spraying_follows_the_kwetu_schedule_with_some_missed_weeks(farm):
    sprays = farm.tables()["herd_activities"]
    weeks = (END - START).days / 7
    cattle = sprays[sprays["species"] == "CATTLE"]
    goats = sprays[sprays["species"] == "GOAT"]
    assert set(d.weekday() for d in cattle["date"]) == {0, 3}     # Monday and Thursday
    assert set(d.weekday() for d in goats["date"]) == {2}         # Wednesday
    assert 1.6 * weeks < len(cattle) < 2 * weeks                  # twice a week, minus missed weeks
    assert "CHICKEN" not in set(sprays["species"])


def test_no_records_before_birth_or_after_leaving(health):
    assert (health["date"] >= health["date_of_birth"]).all()
    left = health[health["exit_date"].notna()]
    assert (left["date"] <= left["exit_date"]).all()


def test_same_seed_gives_the_same_records():
    first, second = simulate(seed=3).tables(), simulate(seed=3).tables()
    pd.testing.assert_frame_equal(first["health"], second["health"])
    pd.testing.assert_frame_equal(first["herd_activities"], second["herd_activities"])
    