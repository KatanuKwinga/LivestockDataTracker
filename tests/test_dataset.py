"""The labels the model learns from (ml/dataset.py)."""
from datetime import date

import pandas as pd

from ml.dataset import labels


def tiny_farm():
    """Three goats whose answers we know by hand."""
    return {
        "livestock": pd.DataFrame({"animal_id": [1, 2, 3], "species": ["GOAT"] * 3,
                                   "date_of_birth": [date(2024, 1, 1), date(2024, 1, 1), date(2026, 2, 10)]}),
        # Goat 1 falls ill on 20 January. Goat 2 is sold on 5 January.
        "health": pd.DataFrame({"animal_id": [1], "date": [date(2026, 1, 20)], "record_type": ["ILLNESS"]}),
        "mortality": pd.DataFrame({"animal_id": [], "date_of_death": []}),
        "commercial": pd.DataFrame({"animal_id": [2], "date": [date(2026, 1, 5)]}),
    }


def test_each_snapshot_asks_about_the_next_30_days():
    table = labels(tiny_farm(), start=date(2026, 1, 1), end=date(2026, 3, 31))
    first = table[table["snapshot"] == pd.Timestamp(2026, 1, 1)]
    # On 1 January goats 1 and 2 are on the farm (goat 3 isn't born yet).
    assert sorted(first["animal_id"]) == [1, 2]
    # Goat 1 falls ill on 20 January, within 30 days; goat 2 doesn't.
    assert dict(zip(first["animal_id"], first["ill_within_30_days"])) == {1: 1, 2: 0}


def test_sold_and_unborn_animals_are_left_out():
    table = labels(tiny_farm(), start=date(2026, 1, 1), end=date(2026, 3, 31))
    assert 2 not in set(table.loc[table["snapshot"] > pd.Timestamp(2026, 1, 5), "animal_id"])
    assert table.loc[table["animal_id"] == 3, "snapshot"].min() >= pd.Timestamp(2026, 2, 10)


def test_no_snapshot_without_30_days_of_records_after_it():
    table = labels(tiny_farm(), start=date(2026, 1, 1), end=date(2026, 3, 31))
    assert table["snapshot"].max() <= pd.Timestamp(2026, 3, 1)