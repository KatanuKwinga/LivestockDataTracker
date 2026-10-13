"""Tests for the illness engine (ml/simulator/illness.py)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from ml.reference import CONDITIONS, ILLNESS_RECOVERY_DAYS, SPECIES_INFO
from ml.simulator.farm import Animal, Farm, run
from ml.simulator.herd import births_step, sales_step, starting_herd
from ml.simulator.illness import (
    can_get, chance_per_day, daily_risk, herd_multiplier, illness_step,
)
from ml.simulator.routines import (
    deworming_step, spraying_step, vaccination_step,
)

START, END = date(2024, 10, 1), date(2026, 9, 30)
STEPS = [births_step, sales_step, vaccination_step, deworming_step, spraying_step, illness_step]


def condition(species, name):
    return next(c for c in CONDITIONS[species] if c.name == name)


ECF = condition("CATTLE", "East Coast Fever")
MASTITIS = condition("CATTLE", "Mastitis")
SCOURS = condition("CATTLE", "Calf scours")
FMD = condition("CATTLE", "Foot and Mouth Disease")


def cow(**changes):
    animal = Animal(1, "C001", "CATTLE", "FEMALE", "Friesian", date(2022, 1, 1))
    for key, value in changes.items():
        setattr(animal, key, value)
    return animal


@pytest.fixture(scope="module")
def farm():
    farm = Farm(START, END, seed=1)
    starting_herd(farm)
    return run(farm, STEPS)


@pytest.fixture(scope="module")
def health(farm):
    species = {a.animal_id: a.species for a in farm.animals}
    records = farm.tables()["health"]
    records["species"] = records["animal_id"].map(species)
    return records


# Rules
def test_chance_is_spread_over_the_window_the_animal_can_get_it():
    # "common" = 20%: over a year for ECF, over the first 42 days for calf scours.
    assert 1 - (1 - chance_per_day(ECF)) ** 365 == pytest.approx(0.20)
    assert 1 - (1 - chance_per_day(SCOURS)) ** 42 == pytest.approx(0.20)


def test_who_can_get_what():
    day = date(2026, 6, 1)
    assert can_get(cow(), MASTITIS, day)
    assert not can_get(cow(gender="MALE"), MASTITIS, day)
    assert not can_get(cow(), SCOURS, day)                       # too old
    assert can_get(cow(date_of_birth=day - timedelta(days=10)), SCOURS, day)


def test_vaccinated_and_resistant_animals_are_at_lower_risk():
    day = date(2026, 6, 1)
    unprotected = daily_risk(cow(), FMD, day, 1.0)
    vaccinated = cow(vaccine_due={"FMD vaccine": day + timedelta(days=90)},
                     vaccine_doses={"FMD vaccine": 1})
    assert daily_risk(vaccinated, FMD, day, 1.0) == pytest.approx(unprotected * 0.05)
    assert daily_risk(cow(breed="Boran"), ECF, day, 1.0) == pytest.approx(
        daily_risk(cow(), ECF, day, 1.0) * 0.5)


def test_ecf_risk_rises_one_to_three_weeks_after_a_missed_spray_week():
    farm = Farm(START, END)
    missed = date(2026, 7, 6)                                    # a Monday, dry season
    farm.missed_spray_weeks["CATTLE"] = [missed]
    assert herd_multiplier(farm, "CATTLE", ECF, missed + timedelta(days=3)) == 1.0
    assert herd_multiplier(farm, "CATTLE", ECF, missed + timedelta(days=14)) == 3.0
    assert herd_multiplier(farm, "CATTLE", ECF, missed + timedelta(days=30)) == 1.0


def test_rains_raise_the_risk():
    farm = Farm(START, END)
    assert herd_multiplier(farm, "CATTLE", ECF, date(2026, 4, 15)) == 1.5   # long rains
    assert herd_multiplier(farm, "CATTLE", ECF, date(2026, 11, 15)) == 1.3  # short rains


# Simulated Farm
def test_illnesses_belong_to_the_animals_species(health):
    ill = health[health["record_type"] == "ILLNESS"]
    assert len(ill) > 300
    for row in ill.itertuples():
        assert row.disease in {c.name for c in CONDITIONS[row.species]}


def test_every_illness_has_a_temperature_and_fevers_run_hot(health):
    ill = health[health["record_type"] == "ILLNESS"]
    assert ill["temperature"].notna().all()
    ecf = ill[ill["disease"] == "East Coast Fever"]
    assert (ecf["temperature"] >= SPECIES_INFO["CATTLE"]["normal_temp"] + 1.0).all()


def test_injuries_are_treatments_not_illnesses(health):
    assert "Injury" not in set(health.loc[health["record_type"] == "ILLNESS", "disease"])


def test_repeat_treatments_follow_an_illness_of_the_same_animal(health):
    repeats = health[health["description"] == "Repeat treatment"]
    first = health[health["description"] == "Reported sick by worker"]
    assert len(repeats) > 100
    for row in repeats.head(200).itertuples():
        earlier = first[(first["animal_id"] == row.animal_id) & (first["disease"] == row.disease)
                        & (first["date"] < row.date)
                        & (first["date"] >= row.date - timedelta(days=12))]
        assert not earlier.empty


def test_no_new_illness_while_still_recovering(health):
    ill = health[health["record_type"] == "ILLNESS"].sort_values("date")
    for _, dates in ill.groupby("animal_id")["date"]:
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        assert all(g >= ILLNESS_RECOVERY_DAYS for g in gaps)


def test_some_illnesses_end_in_death_and_nothing_is_recorded_after(farm, health):
    deaths = farm.tables()["mortality"]
    illness_deaths = deaths[deaths["cause_of_death"] != "Weak at birth / starvation"]
    assert len(illness_deaths) > 5
    died = dict(zip(deaths["animal_id"], deaths["date_of_death"]))
    after = health[health["animal_id"].map(died).notna()]
    assert (after["date"] <= after["animal_id"].map(died)).all()


def test_rain_triggered_illness_is_more_common_in_the_long_rains(health):
    ecf = health[(health["disease"] == "East Coast Fever") & (health["record_type"] == "ILLNESS")]
    months = pd.to_datetime(ecf["date"]).dt.month
    per_month_rains = months.isin([3, 4, 5]).sum() / 3
    per_month_dry = months.isin([1, 2, 6, 7, 8, 9]).sum() / 6
    assert per_month_rains > per_month_dry