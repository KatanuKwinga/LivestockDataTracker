"""Turn a farm's history into examples for the disease-alert model.

One example (row) = one farm, one animal group, one disease, on one
snapshot day. Its answer (label) is 1 if that disease appeared in that
group within the next 30 days. Its clues (features) only use records on
or before the snapshot day: what the farmer could know that day.

The same code builds the rows for the simulated farms (training), the demo
farm and Kwetu's records (testing), and the farm in the app (alerts).
"""
from datetime import timedelta

import numpy as np
import pandas as pd

from ml.groups import GROUPS, group_name, pairs
from ml.reference import (
        CONDITIONS, EL_NINO_MONTHS, EL_NINO_PERIODS, LONG_RAINS, SHORT_RAINS, VACCINES,
)

HORIZON_DAYS = 30            # how far ahead the model looks
EVERY_DAYS = 14              # how often a snapshot is taken
CAP_DAYS = 365               # "never", or more than a year ago, both count as 365
SPRAY_GAP_DAYS = 21          # a missed spray shows up as ECF / heartwarter 1-3 weeks later
UNKNOWN_AGE_DAYS = 3 * 365   # animals with no birth date are treated as grown
DEWORMING_NOTE = "Routine deworming"   # what a group deworming writes on each animal

LABEL = "disease_within_30_days"
CATEGORIES = ["species", "group", "disease", "season"]
NUMBERS = ["month", "group_size", "cases_last_30_days", "cases_last_year",
           "cases_this_time_last_year", "days_since_deworming", "days_since_spraying", "longest_spray_gap",
           "vaccine_coverage", "has_vaccine", "el_nino", "rains_start_soon"]
FEATURES = CATEGORIES + NUMBERS

# Which vaccine prevents each (species, disease), if any.
VACCINE_FOR = {(species, c.name): c.vaccine for species, conditions in CONDITIONS.items()
               for c in conditions if c.vaccine}


# ------------------------------------------------------------ the calendar

def season(day):
    """'long rains', 'short rains' or 'dry' for a day's month."""
    if day.month in LONG_RAINS:
        return "long rains"
    if day.month in SHORT_RAINS:
        return "short rains"
    return "dry"

def el_nino_on(day, seasons):
    """Is this day inside one of these El Nino seasons (a table of start, end)?"""
    return bool(((seasons["start"] <= day) & (day <= seasons["end"])).any())


def el_nino_switch(day, switch):
    """The farmer's switch means "El Nino is forecast for the short rains".
    It only counts in El Nino months (Oct-Jan): ticked in July, it changes
    nothing until October, so the farmer can tick it as soon as the
    forecast comes out."""
    return int(bool(switch) and day.month in EL_NINO_MONTHS)


# ------------------------------------------------------------ the records

def prepare(data):
    """Put a farm's tables into one tidy shape, whichever source they came
    from (simulator, workbook or database):

    animals      farm, animal_id, species, female, date_of_birth, joined, left
    births       animal_id, date          (the mother, and the day she gave birth)
    illnesses    farm, species, animal_id, date, disease
    vaccinations animal_id, date, vaccine
    dewormings   farm, species, date
    sprayings    farm, species, date
    """
    livestock = data["livestock"].copy()
    if "farm" not in livestock:
        livestock["farm"] = "farm"
    livestock["date_of_birth"] = pd.to_datetime(livestock["date_of_birth"])
    joined = pd.to_datetime(livestock["joined"]) if "joined" in livestock else livestock["date_of_birth"]
    animals = pd.DataFrame({
        "farm": livestock["farm"], "animal_id": livestock["animal_id"],
        "species": livestock["species"].str.upper(),
        "female": livestock["gender"].str.upper().eq("FEMALE"),
        "date_of_birth": livestock["date_of_birth"],
        "joined": joined.fillna(livestock["date_of_birth"]),
    })

    # The day each animal left: died, sold, or left another way.
    left = [pd.DataFrame({"animal_id": data["mortality"]["animal_id"],
                          "date": pd.to_datetime(data["mortality"]["date_of_death"])})]
    sales = data["commercial"]
    if "transaction_type" in sales:
        sales = sales[sales["transaction_type"] == "SELL"]
    left.append(pd.DataFrame({"animal_id": sales["animal_id"], "date": pd.to_datetime(sales["date"])}))
    if "departures" in data:
        left.append(pd.DataFrame({"animal_id": data["departures"]["animal_id"],
                                  "date": pd.to_datetime(data["departures"]["date"])}))
    first_exit = pd.concat(left).dropna().groupby("animal_id")["date"].min()
    # A farm with no deaths, sales or departures yet: nobody has left.
    animals["left"] = animals["animal_id"].map(first_exit) if len(first_exit) else pd.NaT
    animals["left"] = pd.to_datetime(animals["left"])
    breeding = data["breeding"]
    births = pd.DataFrame({"animal_id": breeding["animal_id"],
                           "date": pd.to_datetime(breeding["actual_delivery_date"])}).dropna()

    health = data["health"].drop(columns=["farm", "species"], errors="ignore")
    health["date"] = pd.to_datetime(health["date"])
    health = health.merge(animals[["animal_id", "farm", "species"]], on="animal_id")
    ill = health[health["record_type"] == "ILLNESS"]
    illnesses = ill[["farm", "species", "animal_id", "date", "disease"]].dropna(subset=["disease"])
    vacc = health[health["record_type"] == "VACCINATION"]
    vaccinations = pd.DataFrame({"animal_id": vacc["animal_id"], "date": vacc["date"],
                                 "vaccine": vacc["treatment"]})

    groups = data["herd_activities"].copy()

    if "farm" not in groups:
        groups["farm"] = animals["farm"].iloc[0] if len(animals) else "farm"
    groups["date"] = pd.to_datetime(groups["date"])
    groups["species"] = groups["species"].str.upper()
    own_deworm = health[health["description"] == DEWORMING_NOTE][["farm", "species", "date"]]
    dewormings = pd.concat([groups[groups["activity"] == "DEWORMING"][["farm", "species", "date"]], own_deworm])
    sprayings = groups[groups["activity"] == "TICK_SPRAY"][["farm", "species", "date"]]

    # Each farm's El Nino seasons: the simulator says which years it gave
    # each farm; for real records (demo farm, Kwetu) it's the real history.
    if "el_nino" in data:
        el_nino = data["el_nino"].copy()
        if "farm" not in el_nino:
            el_nino["farm"] = animals["farm"].iloc[0] if len(animals) else "farm"
    else:
        el_nino = pd.DataFrame([(farm, start, end) for farm in animals["farm"].unique()
                                for start, end in EL_NINO_PERIODS], columns=["farm", "start", "end"])
    el_nino["start"], el_nino["end"] = pd.to_datetime(el_nino["start"]), pd.to_datetime(el_nino["end"])

    return {"animals": animals, "births": births, "illnesses": illnesses,
            "vaccinations": vaccinations, "dewormings": dewormings, "sprayings": sprayings,
            "el_nino": el_nino[["farm", "start", "end"]]}


def members_on(tidy, day):
    """Every animal on the farm that day, with its group."""
    a = tidy["animals"]
    here = a[(a["joined"] <= day) & ~(a["left"] <= day)
             & (a["date_of_birth"].isna() | (a["date_of_birth"] <= day))].copy()
    births = tidy["births"]
    last_birth = births[births["date"] <= day].groupby("animal_id")["date"].max().rename("last_birth")
    here = here.merge(last_birth.reset_index(), on="animal_id", how="left")
    since_birth = (day - pd.to_datetime(here["last_birth"])).dt.days
    age = (day - here["date_of_birth"]).dt.days.fillna(UNKNOWN_AGE_DAYS)
    here["group"] = [group_name(s, a_, f, None if np.isnan(b) else b)
                     for s, a_, f, b in zip(here["species"], age, here["female"], since_birth)]
    return here[["farm", "species", "animal_id", "group"]]


def days_since(events, keys, day):
    """Days from `day` back to the latest event on or before it, per key
    (e.g. per farm and species), capped at a year."""
    done = events[events["date"] <= day].groupby(keys)["date"].max()
    return ((day - done).dt.days).clip(upper=CAP_DAYS)

def longest_spray_gap(sprayings, day, window=SPRAY_GAP_DAYS):
    """Per farm and species: the longest stretch with no spraying in the
    last `window` days. days_since_spraying forgets a missed week as soon as
    spraying starts again, but the ticks it let through cause East Coast
    Fever and heartwater 1-3 weeks later. This remembers it.
    Normal: 3-4 days for cattle (sprayed twice a week), 7 for goats and
    sheep. A missed week makes it about 11 or 14."""
    start = day - timedelta(days=window)
    gaps = {}
    for key, dates in sprayings[sprayings["date"] <= day].groupby(["farm", "species"])["date"]:
        before = dates[dates <= start]
        points = sorted([before.max() if len(before) else start] + list(dates[dates > start]) + [day])
        gaps[key] = max((b - a).days for a, b in zip(points, points[1:]))
    index = pd.MultiIndex.from_tuples(gaps, names=["farm", "species"]) if gaps else \
        pd.MultiIndex.from_tuples([], names=["farm", "species"])
    return pd.Series(list(gaps.values()), index=index, dtype=float).clip(upper=CAP_DAYS)


def vaccine_coverage(tidy, members, day):
    """For each group and vaccine: the share of the group whose vaccine is
    still in date (given within its repeat interval, or ever, for a course)."""
    v = tidy["vaccinations"]
    v = v[v["date"] <= day]
    if v.empty:
        return pd.DataFrame(columns=["farm", "species", "group", "vaccine", "vaccine_coverage"])
    last = v.groupby(["animal_id", "vaccine"])["date"].max().reset_index()
    repeat = last["vaccine"].map(lambda name: (VACCINES.get(name) or {}).get("repeat_days"))
    age = (day - last["date"]).dt.days
    last = last[repeat.isna() | (age <= repeat.fillna(0))]
    covered = members.merge(last[["animal_id", "vaccine"]], on="animal_id")
    counts = covered.groupby(["farm", "species", "group", "vaccine"]).size().rename("covered").reset_index()
    sizes = members.groupby(["farm", "species", "group"]).size().rename("size").reset_index()
    counts = counts.merge(sizes, on=["farm", "species", "group"])
    counts["vaccine_coverage"] = counts["covered"] / counts["size"]
    return counts[["farm", "species", "group", "vaccine", "vaccine_coverage"]]


def case_counts(ill, since, until, name):
    """Cases of each disease per farm and species, with since < date <= until."""
    window = ill[(ill["date"] > since) & (ill["date"] <= until)]
    return window.groupby(["farm", "species", "disease"]).size().rename(name)


# ------------------------------------------------------------ one snapshot

PAIRS = pd.DataFrame(pairs(), columns=["species", "group", "disease"])


def snapshot(tidy, day, el_nino=None, with_labels=True):
    """The rows for one snapshot day: one per farm, group and disease the
    group can get. `el_nino` is True/False (the farmer's switch), or None to
    look it up in the simulated years' history."""
    members = members_on(tidy, day)
    sizes = members.groupby(["farm", "species", "group"]).size().rename("group_size").reset_index()
    rows = sizes.merge(PAIRS, on=["species", "group"])
    if rows.empty:
        return rows

    middle = day + timedelta(days=HORIZON_DAYS // 2)
    rows["season"] = season(middle)
    rows["month"] = middle.month
    if el_nino is None:          # training and testing: the farm's own El Nino history
        seasons = tidy["el_nino"]
        rows["el_nino"] = rows["farm"].map(
            lambda farm: int(el_nino_on(middle, seasons[seasons["farm"] == farm]))).astype(int)
    else:                        # the app: the farmer's switch
        rows["el_nino"] = el_nino_switch(middle, el_nino)
    rows["rains_start_soon"] = int(season(day) == "dry" and season(day + timedelta(days=HORIZON_DAYS)) != "dry")

    ill = tidy["illnesses"]
    year_ago = day - timedelta(days=365)
    key = ["farm", "species", "disease"]
    for counts in (case_counts(ill, day - timedelta(days=30), day, "cases_last_30_days"),
                   case_counts(ill, year_ago, day, "cases_last_year"),
                   case_counts(ill, year_ago, year_ago + timedelta(days=HORIZON_DAYS), "cases_this_time_last_year")):
        rows = rows.merge(counts.reset_index(), on=key, how="left")
    for column in ("cases_last_30_days", "cases_last_year", "cases_this_time_last_year"):
        rows[column] = rows[column].fillna(0).astype(int)

    for name, events in (("days_since_deworming", tidy["dewormings"]), ("days_since_spraying", tidy["sprayings"])):
        found = days_since(events, ["farm", "species"], day).rename(name).reset_index()
        rows = rows.merge(found, on=["farm", "species"], how="left")
        rows[name] = rows[name].fillna(CAP_DAYS)
    gap = longest_spray_gap(tidy["sprayings"], day).rename("longest_spray_gap").reset_index()
    rows = rows.merge(gap, on=["farm", "species"], how="left")
    rows["longest_spray_gap"] = rows["longest_spray_gap"].fillna(CAP_DAYS)
    rows["vaccine"] = [VACCINE_FOR.get((s, d)) for s, d in zip(rows["species"], rows["disease"])]
    rows["has_vaccine"] = rows["vaccine"].notna().astype(int)
    coverage = vaccine_coverage(tidy, members, day)
    rows = rows.merge(coverage, on=["farm", "species", "group", "vaccine"], how="left")
    rows["vaccine_coverage"] = rows["vaccine_coverage"].fillna(0.0)
    rows = rows.drop(columns="vaccine")
    rows.insert(1, "snapshot", day)

    if with_labels:
        ahead = ill[(ill["date"] > day) & (ill["date"] <= day + timedelta(days=HORIZON_DAYS))]
        hit = ahead.merge(members[["animal_id", "group"]], on="animal_id")[["farm", "species", "group", "disease"]]
        hit = hit.drop_duplicates().assign(**{LABEL: 1})
        rows = rows.merge(hit, on=["farm", "species", "group", "disease"], how="left")
        rows[LABEL] = rows[LABEL].fillna(0).astype(int)
    return rows


def build_table(data, start, end, every_days=EVERY_DAYS, el_nino=None):
    """Snapshots every `every_days` from `start`, stopping while there are
    still 30 days of records after the snapshot (so its answer is known)."""
    tidy = prepare(data)
    day, end = pd.Timestamp(start), pd.Timestamp(end)
    parts = []
    while day + timedelta(days=HORIZON_DAYS) <= end:
        parts.append(snapshot(tidy, day, el_nino))
        day += timedelta(days=every_days)
    return pd.concat(parts, ignore_index=True)