"""Tests for the examples the disease-alert model learns from (ml/disease_data.py).

A tiny hand-made farm, so every number can be checked by hand."""
from datetime import date

import pandas as pd
import pytest

from ml.disease_data import FEATURES, LABEL, build_table, season, snapshot, prepare

DAY = pd.Timestamp("2026-03-01")


def farm(**extra):
    data = {
        "livestock": pd.DataFrame([
            # Two calves, one cow that calved 10 days ago, one older cow.
            {"animal_id": 1, "species": "CATTLE", "gender": "MALE", "date_of_birth": "2026-01-01"},
            {"animal_id": 2, "species": "CATTLE", "gender": "FEMALE", "date_of_birth": "2026-01-15"},
            {"animal_id": 3, "species": "CATTLE", "gender": "FEMALE", "date_of_birth": "2020-01-01"},
            {"animal_id": 4, "species": "CATTLE", "gender": "FEMALE", "date_of_birth": "2019-01-01"},
            {"animal_id": 5, "species": "CATTLE", "gender": "MALE", "date_of_birth": "2018-01-01"},
        ]),
        "breeding": pd.DataFrame({"animal_id": [3], "actual_delivery_date": ["2026-02-19"]}),
        "health": pd.DataFrame([
            # Last year's worms (to count as history), a scours case next week, and the
            # older cow's mastitis after the 30 days (must not count).
            {"animal_id": 4, "date": "2025-03-10", "record_type": "ILLNESS", "disease": "Gastrointestinal worms",
             "treatment": "Nilzan", "description": ""},
            {"animal_id": 1, "date": "2026-03-08", "record_type": "ILLNESS", "disease": "Calf scours",
             "treatment": "ORS", "description": ""},
            {"animal_id": 4, "date": "2026-04-15", "record_type": "ILLNESS", "disease": "Mastitis",
             "treatment": "Penstrep", "description": ""},
            {"animal_id": 4, "date": "2026-01-10", "record_type": "VACCINATION", "disease": None,
             "treatment": "Lumpy skin vaccine", "description": ""},
        ]),
        "mortality": pd.DataFrame({"animal_id": [5], "date_of_death": ["2026-01-01"]}),
        "commercial": pd.DataFrame(columns=["animal_id", "date", "transaction_type"]),
        "herd_activities": pd.DataFrame({"date": ["2026-02-01"], "species": ["CATTLE"], "activity": ["DEWORMING"]}),
    }
    data.update(extra)
    return data


@pytest.fixture
def rows():
    return snapshot(prepare(farm()), DAY)


def row(rows, group, disease):
    found = rows[(rows["group"] == group) & (rows["disease"] == disease)]
    assert len(found) == 1, (group, disease)
    return found.iloc[0]


def test_groups_and_their_sizes(rows):
    sizes = rows.groupby("group")["group_size"].first().to_dict()
    # The dead bull (5) is gone; cow 3 calved 10 days ago.
    assert sizes == {"Calves": 2, "Cows after calving": 1, "Adult cattle": 1}


def test_the_answer_only_looks_30_days_ahead(rows):
    assert row(rows, "Calves", "Calf scours")[LABEL] == 1
    assert row(rows, "Adult cattle", "Mastitis")[LABEL] == 0          # 45 days later


def test_history_and_routines_are_counted(rows):
    worms = row(rows, "Adult cattle", "Gastrointestinal worms")
    assert worms["cases_last_year"] == 1
    assert worms["cases_this_time_last_year"] == 1                    # 10 March 2025
    assert worms["cases_last_30_days"] == 0
    assert worms["days_since_deworming"] == 28
    assert worms["days_since_spraying"] == 365                        # never recorded
    assert worms["longest_spray_gap"] == 365

def test_vaccine_coverage_is_the_share_of_the_group_in_date(rows):
    lsd = row(rows, "Adult cattle", "Lumpy skin disease")
    assert lsd["has_vaccine"] == 1 and lsd["vaccine_coverage"] == 1.0
    assert row(rows, "Calves", "Lumpy skin disease")["vaccine_coverage"] == 0.0
    assert row(rows, "Calves", "Calf scours")["has_vaccine"] == 0


def test_the_season_is_kept_for_the_calendar_but_the_rain_is_the_clue():
    assert season(pd.Timestamp("2026-04-01")) == "long rains"
    assert season(pd.Timestamp("2026-11-01")) == "short rains"
    assert season(pd.Timestamp("2026-07-01")) == "dry"
    assert "season" not in FEATURES and "month" not in FEATURES
    assert {"rain_last_30_days", "rain_30_to_60_days_ago", "rain_next_16_days"} <= set(FEATURES)


def daily_rain(start, end, mm):
    days = pd.date_range(start, end)
    return pd.DataFrame({"date": days, "rain_mm": mm})


def test_the_rain_clues_come_from_the_farms_daily_rain():
    # 2 mm a day in February, 10 mm a day from 1 March: a snapshot on 1 March.
    rain = pd.concat([daily_rain("2025-12-01", "2026-02-28", 2.0), daily_rain("2026-03-01", "2026-04-30", 10.0)])
    row = snapshot(prepare(farm(rain=rain)), DAY).iloc[0]
    assert row["rain_last_30_days"] == pytest.approx(60.0)        # 30 dry days at 2 mm
    assert row["rain_30_to_60_days_ago"] == pytest.approx(60.0)
    assert row["rain_next_16_days"] == pytest.approx(160.0)       # the forecast: 16 days at 10 mm


def test_no_rain_known_leaves_the_rain_clues_empty():
    row = snapshot(prepare(farm()), DAY).iloc[0]
    assert pd.isna(row["rain_last_30_days"]) and pd.isna(row["rain_next_16_days"])


def test_build_table_takes_a_snapshot_every_fortnight():
    table = build_table(farm(), date(2026, 2, 1), date(2026, 5, 1))
    assert table["snapshot"].nunique() == 5                           # 1 Feb ... 29 Mar
    assert set(FEATURES + [LABEL]) <= set(table.columns)


def sprayed(dates):
    return pd.DataFrame({"date": dates, "species": "CATTLE", "activity": "TICK_SPRAY"})


def test_a_missed_spray_week_is_remembered_after_spraying_restarts():
    # Twice a week (Mon, Thu), except the week of 9 Feb was missed.
    dates = ["2026-02-02", "2026-02-05", "2026-02-16", "2026-02-19", "2026-02-23", "2026-02-26"]
    lsd = row(snapshot(prepare(farm(herd_activities=sprayed(dates))), DAY), "Adult cattle", "Lumpy skin disease")
    assert lsd["days_since_spraying"] == 3                    # back to normal...
    assert lsd["longest_spray_gap"] == 11                     # ...but 5 Feb to 16 Feb is remembered


def test_no_missed_week_gives_a_short_gap():
    dates = ["2026-02-05", "2026-02-09", "2026-02-12", "2026-02-16", "2026-02-19", "2026-02-23", "2026-02-26"]
    lsd = row(snapshot(prepare(farm(herd_activities=sprayed(dates))), DAY), "Adult cattle", "Lumpy skin disease")
    assert lsd["longest_spray_gap"] == 4

def test_a_farm_where_no_animal_has_left_yet():
    tidy = prepare(farm(mortality=pd.DataFrame(columns=["animal_id", "date_of_death"])))
    assert tidy["animals"]["left"].isna().all()
    assert len(snapshot(tidy, DAY)) > 0