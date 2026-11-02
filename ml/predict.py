"""
Setting up a way for the farmer to know which animals to check on first.
Ranks their risk level as low, medium or high.
"""
import argparse
from datetime import date

import joblib
import pandas as pd

from app.models import CommercialInfo, HealthRecord, HerdActivity, Livestock, MortalityRecord
from ml.dataset import FEATURES, SPECIES, exits, features
from ml.train import MODEL_PATH

# On the test rows, animals below 6% fell ill 5% of the time, 6-10% about 8%,
# and 10% or more about 12% of the time (lesson S9).
LOW_BELOW = 0.06
HIGH_FROM = 0.10
UNKNOWN_AGE_DAYS = 3 * 365     # animals with no birth date are treated as grown (3 years)


def risk_level(chance):
    if chance >= HIGH_FROM:
        return "High"
    if chance >= LOW_BELOW:
        return "Medium"
    return "Low"


def farm_data(farm_id):
    """The farm's records from the database, in the same shape as the simulator's tables."""
    animals = Livestock.query.filter_by(farmer_id=farm_id).all()
    ids = [a.animal_id for a in animals]
    return {
        "livestock": pd.DataFrame([{"animal_id": a.animal_id, "species": a.species, "tag": a.tag_number,
                                    "date_of_birth": a.date_of_birth} for a in animals],
                                  columns=["animal_id", "species", "tag", "date_of_birth"]),
        "health": pd.DataFrame([{"animal_id": h.animal_id, "date": h.date, "record_type": h.record_type,
                                 "description": h.description}
                                for h in HealthRecord.query.filter(HealthRecord.animal_id.in_(ids))],
                               columns=["animal_id", "date", "record_type", "description"]),
        "mortality": pd.DataFrame([{"animal_id": m.animal_id, "date_of_death": m.date_of_death}
                                   for m in MortalityRecord.query.filter(MortalityRecord.animal_id.in_(ids))],
                                  columns=["animal_id", "date_of_death"]),
        "commercial": pd.DataFrame([{"animal_id": c.animal_id, "date": c.date}
                                    for c in CommercialInfo.query.filter(CommercialInfo.animal_id.in_(ids),
                                                                         CommercialInfo.transaction_type == "SELL")],
                                   columns=["animal_id", "date"]),
        "herd_activities": pd.DataFrame([{"date": s.date, "species": s.species, "activity": s.activity}
                                         for s in HerdActivity.query.filter_by(farmer_id=farm_id)],
                                        columns=["date", "species", "activity"]),
    }


def on_farm_today(data, today):
    """One row per cattle, goat or sheep on the farm today (born, not dead, not sold)."""
    livestock = data["livestock"]
    gone = set(exits(data).loc[lambda e: e["date"] <= pd.Timestamp(today), "animal_id"])
    born = pd.to_datetime(livestock["date_of_birth"]).fillna(pd.Timestamp(today)) <= pd.Timestamp(today)
    here = livestock[livestock["species"].isin(SPECIES) & born & ~livestock["animal_id"].isin(gone)]
    return pd.DataFrame({"animal_id": here["animal_id"], "species": here["species"], "snapshot": pd.Timestamp(today)})


def predict_farm(farm_id, today=None, model=None):
    """Every animal on the farm with its chance and risk level, riskiest first."""
    today = today or date.today()
    model = model or joblib.load(MODEL_PATH)
    data = farm_data(farm_id)
    table = on_farm_today(data, today)
    if table.empty:
        return table
    table = features(table, data)
    table["age_days"] = table["age_days"].fillna(UNKNOWN_AGE_DAYS)
    table["chance"] = model.predict_proba(table[["species"] + FEATURES])[:, 1]
    table["risk"] = table["chance"].map(risk_level)
    table = table.merge(data["livestock"][["animal_id", "tag"]], on="animal_id")
    return table.sort_values("chance", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    from app import create_app
    from app.models import User

    parser = argparse.ArgumentParser(description="Illness risk for every animal on one farm.")
    parser.add_argument("--farmer-email", required=True)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        farm_id = User.query.filter_by(email=args.farmer_email.strip().lower()).first().farmer.farmer_id
        result = predict_farm(farm_id)
        print(f"{len(result)} animals on the farm today ({date.today():%d/%m/%Y}):")
        print(result["risk"].value_counts().reindex(["High", "Medium", "Low"], fill_value=0).to_string())
        print("\nThe ten to check first:")
        columns = ["tag", "species", "chance", "risk", "illnesses_last_year", "days_since_deworming", "age_days"]
        print(result[columns].head(10).round({"chance": 3}).to_string(index=False))