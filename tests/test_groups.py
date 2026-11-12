"""Tests for the animal groups the disease alerts are given for (ml/groups.py)."""
from ml.groups import GROUPS, diseases_for, group_name, pairs
from ml.reference import CONDITIONS


def test_animals_are_put_in_the_right_group():
    assert group_name("CATTLE", 60, True, None) == "Calves"
    assert group_name("CATTLE", 400, False, None) == "Young stock"
    assert group_name("CATTLE", 1500, True, 20) == "Cows after calving"
    assert group_name("CATTLE", 1500, True, 200) == "Adult cattle"       # calved long ago
    assert group_name("CATTLE", 1500, False, None) == "Adult cattle"
    assert group_name("GOAT", 30, False, None) == "Kids"
    assert group_name("GOAT", 700, True, 10) == "Does after kidding"
    assert group_name("SHEEP", 900, False, None) == "Adult sheep"
    assert group_name("CHICKEN", 500, True, None) == "Flock"


def test_diseases_only_go_to_groups_that_can_get_them():
    def names(species, group):
        return {c.name for c in diseases_for(species, group)}
    assert "Calf scours" in names("CATTLE", "Calves")
    assert "Calf scours" not in names("CATTLE", "Adult cattle")
    assert "Blackquarter" in names("CATTLE", "Young stock")
    assert "Blackquarter" not in names("CATTLE", "Calves")
    assert "Laminitis" in names("CATTLE", "Cows after calving")
    assert "Laminitis" not in names("CATTLE", "Adult cattle")
    assert "Mastitis" not in names("CATTLE", "Young stock")              # heifers don't milk yet
    assert "Mastitis" not in names("GOAT", "Kids")


def test_every_predicted_disease_has_at_least_one_group():
    covered = {(species, disease) for species, _, disease in pairs()}
    for species in GROUPS:
        for c in CONDITIONS[species]:
            if c.group in ("A", "B") and c.rank != "rare" and not c.watch_only:
                assert (species, c.name) in covered, c.name