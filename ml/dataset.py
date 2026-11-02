"""Turn a farm's history into examples the model can learn from to answer the
question of its likelihood of falling ill within the next 30 days
"""
from datetime import timedelta

import pandas as pd

HORIZON_DAYS = 30                          # how far ahead the model looks
EVERY_DAYS = 14                            # how often we take a snapshot
SPECIES = ("CATTLE", "GOAT", "SHEEP")      # Kwetu keeps no records of chickens


def exits(data):
    """When each animal left the farm: the day it died or was sold."""
    died = pd.DataFrame({"animal_id": data["mortality"]["animal_id"],
                         "date": pd.to_datetime(data["mortality"]["date_of_death"])})
    sold = pd.DataFrame({"animal_id": data["commercial"]["animal_id"],
                         "date": pd.to_datetime(data["commercial"]["date"])})
    return pd.concat([died, sold])


def labels(data, start, end, every_days=EVERY_DAYS, horizon=HORIZON_DAYS):
    """One row per animal per snapshot day, with its label (1 = fell ill within `horizon` days)."""
    livestock = data["livestock"][data["livestock"]["species"].isin(SPECIES)].copy()
    livestock["date_of_birth"] = pd.to_datetime(livestock["date_of_birth"])
    left = exits(data)
    health = data["health"]
    illnesses = health[health["record_type"] == "ILLNESS"].copy()
    illnesses["date"] = pd.to_datetime(illnesses["date"])

    rows = []
    day = pd.Timestamp(start)
    # Stop while there are still `horizon` days of records after the snapshot,
    # otherwise we couldn't know the answer.
    while day + timedelta(days=horizon) <= pd.Timestamp(end):
        born = livestock["date_of_birth"] <= day
        gone = livestock["animal_id"].isin(left.loc[left["date"] <= day, "animal_id"])
        here = livestock[born & ~gone]

        window = illnesses[(illnesses["date"] > day) & (illnesses["date"] <= day + timedelta(days=horizon))]
        fell_ill = set(window["animal_id"])

        for animal_id, species in zip(here["animal_id"], here["species"]):
            rows.append({"animal_id": animal_id, "species": species, "snapshot": day,
                         "ill_within_30_days": int(animal_id in fell_ill)})
        day += timedelta(days=every_days)
    return pd.DataFrame(rows)