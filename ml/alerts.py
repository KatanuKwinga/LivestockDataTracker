"""The Disease alerts page: the trained model applied to the farm in the app.

For each group of animals on the farm (calves, cows after calving, kids,
the flock...), the model gives the chance of at least one case of each
disease in the next 30 days. The page shows them as High, Watch or Low,
with the reasons in plain words and the advice from ml/reference.py.

The model's rain clues come from the farm's weather (app/weather.py): the
rain of the last 60 days and the forecast for the next 16, at the location
the farmer set. Without it (no location yet, or no answer from the weather
service) the rain is left unknown and the model works from the rest.

Two kinds of warning come from rules, not the model (the notebook, section
15, explains why the model can't give them):
- a gap in tick spraying in the last 3 weeks (East Coast Fever, heartwater);
- very heavy rain, now or forecast: prepare as for an El Nino season.
Rare outbreak diseases (FMD, RVF, PPR...) are never predicted; they are on
the watch list.

The rows are built by the same code that built the training rows
(ml/disease_data.py), so the model gets its clues in the same form.
"""
from datetime import date
from functools import lru_cache

import pandas as pd

from app.models import (BreedingRecord, CommercialInfo, Departure, HealthRecord,
                        HerdActivity, Livestock, MortalityRecord)
from ml.disease_data import CAP_DAYS, prepare, snapshot
from ml.disease_model import MODEL_PATH, load_bundle
from ml.groups import GROUPS
from ml.reference import CONDITIONS, DEWORM_EVERY_DAYS, HEAVY_RAIN_MM, SPRAYS_PER_WEEK

HIGH_FROM = 0.50      # used if the model file doesn't say (it does: bundle["metrics"])
WATCH_FROM = 0.20
LONG_AGO = pd.Timestamp("1900-01-01")   # "joined" for animals with no birth or purchase date
# A spraying gap at least this long means a session was missed: cattle are
# sprayed twice a week (normal gap 3-4 days), goats and sheep once (7 days).
MISSED_SPRAY_GAP = {"CATTLE": 8, "GOAT": 11, "SHEEP": 11}
HEAVY_FORECAST_MM = 125     # 125+ mm forecast in 16 days: heavy rain on its way
WET_FORECAST_MM = 50        # enough forecast rain to mention as a reason
WET_MONTH_MM = 150          # a wet 30 days, as in Kenya's main rainy months
HERD_NAME = {"CATTLE": "cattle", "GOAT": "goats", "SHEEP": "sheep", "CHICKEN": "chickens"}
CONDITION = {(species, c.name): c for species, conditions in CONDITIONS.items() for c in conditions}


# ------------------------------------------------------------ the model

@lru_cache(maxsize=2)
def _load(path, modified):
    return load_bundle(path)


def load_model(path=MODEL_PATH):
    """The trained model, read from disk once and then kept in memory. If the
    file changes (the notebook was run again), it is read again."""
    return _load(str(path), path.stat().st_mtime)


# ------------------------------------------------------------ the records

def frame(rows, columns):
    return pd.DataFrame(rows, columns=columns)


def farm_data(farm_id):
    """The farm's records from the database, in the shape prepare() expects
    (the same shape the simulator and the workbooks give)."""
    animals = Livestock.query.filter_by(farmer_id=farm_id).all()
    ids = [a.animal_id for a in animals]
    bought = {}
    for c in CommercialInfo.query.filter(CommercialInfo.animal_id.in_(ids), CommercialInfo.transaction_type == "BUY"):
        bought[c.animal_id] = min(c.date, bought.get(c.animal_id, c.date))
    return {
        # "joined": the day it came to the farm (bought), else its birth day.
        "livestock": frame([(a.animal_id, a.species, a.gender, a.date_of_birth,
                             bought.get(a.animal_id) or a.date_of_birth or LONG_AGO) for a in animals],
                           ["animal_id", "species", "gender", "date_of_birth", "joined"]),
        "breeding": frame([(b.animal_id, b.actual_delivery_date) for b in BreedingRecord.query.filter(
                               BreedingRecord.animal_id.in_(ids), BreedingRecord.actual_delivery_date.isnot(None))],
                          ["animal_id", "actual_delivery_date"]),
        "mortality": frame([(m.animal_id, m.date_of_death) for m in
                            MortalityRecord.query.filter(MortalityRecord.animal_id.in_(ids))],
                           ["animal_id", "date_of_death"]),
        "commercial": frame([(c.animal_id, c.date, c.transaction_type) for c in
                             CommercialInfo.query.filter(CommercialInfo.animal_id.in_(ids))],
                            ["animal_id", "date", "transaction_type"]),
        "departures": frame([(d.animal_id, d.date) for d in Departure.query.filter(Departure.animal_id.in_(ids))],
                            ["animal_id", "date"]),
        "health": frame([(h.animal_id, h.date, h.record_type, h.disease, h.treatment, h.description)
                         for h in HealthRecord.query.filter(HealthRecord.animal_id.in_(ids))],
                        ["animal_id", "date", "record_type", "disease", "treatment", "description"]),
        "herd_activities": frame([(s.date, s.species, s.activity) for s in HerdActivity.query.filter_by(farmer_id=farm_id)],
                                 ["date", "species", "activity"]),
    }


# ------------------------------------------------------------ reasons

def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def reasons(row, condition):
    """Why this group is at this level, in plain words (the strongest first).
    Rain is only mentioned when it is known (NaN >= a number is False)."""
    said = []
    wet_triggers = {"rains", "rains_onset", "heavy_rain"} & set(condition.triggers)
    if wet_triggers and row["rain_last_30_days"] >= HEAVY_RAIN_MM:
        said.append(f"very heavy rain: {row['rain_last_30_days']:.0f} mm in the last 30 days")
    elif wet_triggers and row["rain_last_30_days"] >= WET_MONTH_MM:
        said.append(f"a wet month: {row['rain_last_30_days']:.0f} mm of rain in the last 30 days")
    if wet_triggers and row["rain_next_16_days"] >= WET_FORECAST_MM:
        said.append(f"{row['rain_next_16_days']:.0f} mm of rain forecast for the next 16 days")
    if row["cases_last_30_days"]:
        said.append(f"{plural(int(row['cases_last_30_days']), 'case')} on the farm in the last 30 days")
    if row["cases_this_time_last_year"]:
        said.append(f"{plural(int(row['cases_this_time_last_year']), 'case')} at this time last year")
    elif row["cases_last_year"]:
        said.append(f"{plural(int(row['cases_last_year']), 'case')} in the last year")
    if "deworm_overdue" in condition.triggers:
        if row["days_since_deworming"] >= CAP_DAYS:
            said.append("no deworming recorded in the last year")
        elif row["days_since_deworming"] > DEWORM_EVERY_DAYS:
            said.append(f"last dewormed {int(row['days_since_deworming'])} days ago (due every {DEWORM_EVERY_DAYS})")
    if row["has_vaccine"] and row["vaccine_coverage"] == 0:
        said.append(f"no animal in the group has an in-date {condition.vaccine}")
    elif row["has_vaccine"] and row["vaccine_coverage"] < 0.5:
        said.append(f"only {row['vaccine_coverage']:.0%} of the group has an in-date {condition.vaccine}")
    return said[:3] or ["common in this group at this time of year"]


def level(chance, high_from, watch_from):
    return "High" if chance >= high_from else "Watch" if chance >= watch_from else "Low"


# ------------------------------------------------------------ the page

def farm_alerts(farm_id, weather=None, today=None, bundle=None):
    """Everything the alerts page shows, worked out for one farm today.
    `weather` is app.weather.get_weather()'s answer for the farm, or None."""
    from app.weather import rain_table      # here, so ml/ doesn't need Flask to import
    bundle = bundle or load_model()
    metrics = bundle.get("metrics", {})
    high_from, watch_from = metrics.get("high_from", HIGH_FROM), metrics.get("watch_from", WATCH_FROM)
    day = pd.Timestamp(today or (weather["today"] if weather else date.today()))

    data = farm_data(farm_id)
    if weather:
        data["rain"] = rain_table(weather)
    tidy = prepare(data)
    rows = snapshot(tidy, day, with_labels=False) if len(tidy["animals"]) else pd.DataFrame()
    species_here = sorted(set(tidy["animals"].loc[
        (tidy["animals"]["joined"] <= day) & ~(tidy["animals"]["left"] <= day), "species"]))

    groups = []
    if len(rows):
        rows["chance"] = bundle["model"].predict_proba(rows[bundle["columns"]])[:, 1]
        order = {(s, g): i for i, (s, g) in enumerate((s, g) for s in GROUPS for g in GROUPS[s])}
        for (species, group), part in sorted(rows.groupby(["species", "group"]), key=lambda kv: order[kv[0]]):
            alerts = []
            for _, row in part.sort_values("chance", ascending=False).iterrows():
                condition = CONDITION[(species, row["disease"])]
                lvl = level(row["chance"], high_from, watch_from)
                if lvl != "Low":
                    alerts.append({"disease": row["disease"], "level": lvl, "chance": float(row["chance"]),
                                   "reasons": reasons(row, condition), "advice": condition.advice})
            groups.append({"species": species, "group": group, "size": int(part["group_size"].iloc[0]),
                           "alerts": alerts, "worst": alerts[0]["level"] if alerts else "Low"})

    rain = rain_summary(rows, weather is not None)
    return {"groups": groups, "species": species_here, "rain": rain,
            "counts": {name: sum(1 for g in groups for a in g["alerts"] if a["level"] == name)
                       for name in ("High", "Watch")},
            "spraying": spraying_warnings(rows, species_here),
            "watch_list": watch_list(tidy, species_here, rain["heavy"], day),
            "heavy_rain_advice": heavy_rain_advice(species_here) if rain["heavy"] else [],
            "trained_on": bundle.get("trained_on"), "high_from": high_from, "watch_from": watch_from}


def rain_summary(rows, live):
    """The rain the alerts were worked out with, to show the farmer
    (None when it isn't known)."""
    if not live or not len(rows):
        return {"live": False, "last_30_days": None, "next_16_days": None, "heavy": False}
    last30, ahead = float(rows["rain_last_30_days"].iloc[0]), float(rows["rain_next_16_days"].iloc[0])
    return {"live": True, "last_30_days": round(last30), "next_16_days": round(ahead),
            "heavy": last30 >= HEAVY_RAIN_MM or ahead >= HEAVY_FORECAST_MM}


def spraying_warnings(rows, species_here):
    """Rule, not model: a long gap between tick sprayings in the last 3
    weeks lets ticks through, and East Coast Fever and heartwater follow
    1-3 weeks later. Also says when no spraying is recorded at all, because
    then the alerts can't tell whether the herd is protected."""
    said = []
    for species in species_here:
        if species not in SPRAYS_PER_WEEK or not len(rows):
            continue
        part = rows[rows["species"] == species]
        if not len(part):
            continue
        gap, since = part["longest_spray_gap"].iloc[0], part["days_since_spraying"].iloc[0]
        name = HERD_NAME[species]
        if since >= CAP_DAYS:
            said.append({"species": species, "tone": "info",
                         "text": f"No tick spraying recorded for the {name} in the last year. If they are "
                                 "sprayed, record it under Treat a group so the alerts can use it."})
        elif gap >= MISSED_SPRAY_GAP[species]:
            disease = "East Coast Fever" if species == "CATTLE" else "heartwater"
            said.append({"species": species, "tone": "warn",
                         "text": f"The {name} went {int(gap)} days without tick spraying in the last 3 weeks. "
                                 f"Ticks let through then can cause {disease} 1 to 3 weeks later: check for "
                                 "fever and swollen lymph nodes over the next 2 weeks, and keep spraying on time."})
    return said


def watch_list(tidy, species_here, heavy_rain, day):
    """Rare outbreak diseases the model doesn't predict, for the species on
    the farm, with their advice. Flagged if heavy rain raises them and it is
    falling or forecast, or if their vaccine hasn't been given on the farm in
    the last year."""
    v = tidy["vaccinations"]
    given = set(v.loc[(v["date"] <= day) & (v["date"] > day - pd.Timedelta(days=365)), "vaccine"])
    found = {}
    for species in species_here:
        for c in CONDITIONS[species]:
            if not c.watch_only:
                continue
            item = found.setdefault(c.name, {"disease": c.name, "species": [], "advice": c.advice, "flags": []})
            item["species"].append(HERD_NAME[species].capitalize())
            if heavy_rain and "heavy_rain" in c.triggers and "Heavy rain" not in item["flags"]:
                item["flags"].append("Heavy rain")
            if c.vaccine and c.vaccine not in given and "No vaccination in the last year" not in item["flags"]:
                item["flags"].append("No vaccination in the last year")
    return sorted(found.values(), key=lambda i: (not i["flags"], i["disease"]))


def heavy_rain_advice(species_here):
    """Rule, not model: what to do in very heavy rain, as in an El Nino
    season (vet advice)."""
    advice = ["If the herd isn't vaccinated against lumpy skin disease and Rift Valley fever this year, "
              "talk to your vet now: both spread fast in very wet weather."]
    for species in species_here:
        for c in CONDITIONS[species]:
            if "heavy_rain" in c.triggers and c.advice and c.advice not in advice and not c.watch_only:
                advice.append(c.advice)
    return advice