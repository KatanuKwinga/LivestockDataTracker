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



# ------------------------------------------------------------------ features
# Everything here looks only at records ON OR BEFORE the snapshot day: what
# the farmer could know that day. Looking later would be seeing the future.

FEATURES = ["age_days", "days_since_deworming", "days_since_vaccination",
            "illnesses_last_year", "rainy_season"]
CAP_DAYS = 365          # "never", or more than a year ago, both count as 365
RAINY_MONTHS = (3, 4, 5, 10, 11, 12)
DEWORMING_NOTE = "Routine deworming"   # what the group deworming form writes (app/routes/group.py)


def days_since(table, events, by):
    """For each row: days from its snapshot back to the latest event on or before it.
    `by` says whose events count: the same animal ("animal_id") or the same herd ("species")."""
    events = events[[by, "date"]].dropna().sort_values("date").rename(columns={"date": "last"})
    left = table[["snapshot", by]].copy()
    # merge_asof insists both date columns are stored the same way, so make them match.
    left["snapshot"] = left["snapshot"].astype("datetime64[ns]")
    events["last"] = events["last"].astype("datetime64[ns]")
    found = pd.merge_asof(left, events, left_on="snapshot", right_on="last", by=by)
    return (found["snapshot"] - found["last"]).dt.days.fillna(CAP_DAYS).clip(upper=CAP_DAYS)


def features(table, data):
    """Add the model's clues to each row of the labels table."""
    table = table.sort_values("snapshot").reset_index(drop=True)     # merge_asof needs date order
    born = data["livestock"][["animal_id", "date_of_birth"]].copy()
    born["date_of_birth"] = pd.to_datetime(born["date_of_birth"])
    table = table.merge(born, on="animal_id", how="left")
    table["age_days"] = (table["snapshot"] - table["date_of_birth"]).dt.days

    health = data["health"].copy()
    health["date"] = pd.to_datetime(health["date"])
    health = health.merge(data["livestock"][["animal_id", "species"]], on="animal_id")

    # Deworming: the animal's own record, or a deworming session for its whole herd.
    own = days_since(table, health[health["description"] == DEWORMING_NOTE], "animal_id")
    sessions = data["herd_activities"].copy()
    sessions["date"] = pd.to_datetime(sessions["date"])
    herd = days_since(table, sessions[sessions["activity"] == "DEWORMING"], "species")
    table["days_since_deworming"] = pd.concat([own, herd], axis=1).min(axis=1)

    table["days_since_vaccination"] = days_since(table, health[health["record_type"] == "VACCINATION"], "animal_id")

    # Illnesses in the year up to and including the snapshot.
    ill = health[health["record_type"] == "ILLNESS"]
    counts = []
    for day, rows in table.groupby("snapshot", sort=False):
        recent = ill[(ill["date"] > day - timedelta(days=365)) & (ill["date"] <= day)]        
        counts.append(rows["animal_id"].map(recent["animal_id"].value_counts()).fillna(0))
    table["illnesses_last_year"] = pd.concat(counts).astype(int)
    
    # Rainy season: is the middle of the next 30 days in a rainy month?
    table["rainy_season"] = (table["snapshot"] + timedelta(days=15)).dt.month.isin(RAINY_MONTHS).astype(int)
    return table.drop(columns="date_of_birth")