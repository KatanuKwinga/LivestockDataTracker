"""Checks that the disease reference table is consistent with itself.

A typo here (a vaccine name spelt two ways, an unknown trigger word)
would silently break the simulator, so these tests catch it early.
"""
import pytest

from ml.reference import (
    CONDITIONS, GROUPS, RANKS, SPECIES_INFO, SPRAYS_PER_WEEK, TRIGGERS, VACCINES,
    conditions_for, daily_chance,
)

ALL = [(species, c) for species, conditions in CONDITIONS.items() for c in conditions]


def test_every_species_has_conditions_the_model_can_predict():
    assert set(CONDITIONS) == set(SPECIES_INFO)
    for species in CONDITIONS:
        assert any(c.group == "B" for c in CONDITIONS[species])


@pytest.mark.parametrize("species, condition", ALL, ids=lambda x: getattr(x, "name", x))
def test_each_condition_uses_known_values(species, condition):
    assert condition.group in GROUPS
    assert condition.rank in RANKS
    assert set(condition.triggers) <= set(TRIGGERS)
    assert 0 <= condition.death_chance <= 1
    assert set(condition.resistant_breeds) <= set(SPECIES_INFO[species]["breeds"])


def test_condition_names_are_unique_within_a_species():
    for species, conditions in CONDITIONS.items():
        names = [c.name for c in conditions]
        assert len(names) == len(set(names)), species


def test_vaccine_preventable_diseases_name_a_vaccine_for_that_species():
    for species, condition in ALL:
        if condition.group == "A":
            assert condition.vaccine in VACCINES, condition.name
            assert species in VACCINES[condition.vaccine]["species"]
            assert "vaccine_overdue" in condition.triggers


def test_every_vaccine_prevents_something():
    used = {c.vaccine for _, c in ALL if c.vaccine}
    assert used == set(VACCINES)


def test_only_ruminants_are_sprayed_for_ticks():
    assert set(SPRAYS_PER_WEEK) == {"CATTLE", "GOAT", "SHEEP"}


def test_daily_chance_adds_up_to_the_yearly_chance():
    for rank, yearly in (("common", 0.20), ("rare", 0.01)):
        daily = daily_chance(rank)
        assert 1 - (1 - daily) ** 365 == pytest.approx(yearly)


def test_conditions_for_leaves_out_newborn_deaths_and_injuries():
    names = [c.name for c in conditions_for("GOAT")]
    assert "Pneumonia" in names
    assert "Injury" not in names
    assert "Weak at birth / starvation" not in names
