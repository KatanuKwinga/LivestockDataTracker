"""Synthetic farm data for building and testing the ML model."""
from datetime import date, timedelta

import pandas as pd

from ml.reference import FARM_VACCINES, VACCINES
from ml.simulator.farm import Farm, run
from ml.simulator.herd import births_step, sales_step, starting_herd
from ml.simulator.illness import illness_step
from ml.simulator.routines import deworming_step, spraying_step, vaccination_step
from ml.simulator.weights import weighing_step

# The order steps run in each day: herd changes first, then routines,
# then illness (which looks at today's vaccine and spraying state), then weighing.
STEPS = [births_step, sales_step, vaccination_step, deworming_step,
         spraying_step, illness_step, weighing_step]

# Vaccination plans for the simulated farms (the app's Vaccination plan page).
FARM_PLANS = {
    "kwetu": FARM_VACCINES,                 # CCPP, FMD, lumpy skin
    "full": tuple(VACCINES),                # every KEVEVAPI vaccine
    "minimal": ("FMD vaccine",),            # vaccinates very little
}


def simulate_farm(end=None, years=2, seed=42, vaccines=FARM_VACCINES):
    """Simulate one farm for `years` years ending on `end` (default today).
    Returns a dict of DataFrames: livestock, breeding, mortality, commercial,
    health, herd_activities, weights."""
    end = end or date.today()
    farm = Farm(end - timedelta(days=365 * years), end, seed=seed, vaccines=vaccines)
    starting_herd(farm)
    run(farm, STEPS)
    return farm.tables()


def simulate_farms(end=None, years=2, seed=42, plans=FARM_PLANS):
    """Simulate one farm per vaccination plan and stack their tables.

    Each farm numbers its animals from 1, so before stacking, every id is
    shifted by farm_number * 100,000 to keep ids unique across farms. A
    `farm` column says which farm each row came from.
    """
    combined = {}
    for number, (name, vaccines) in enumerate(plans.items()):
        tables = simulate_farm(end, years, seed + number, vaccines)
        offset = number * 100_000
        for table_name, df in tables.items():
            df = df.copy()
            for column in ("animal_id", "sire_id", "b_record_id"):
                if column in df:
                    df[column] = df[column] + offset
            df.insert(0, "farm", name)
            combined.setdefault(table_name, []).append(df)
    return {name: pd.concat(parts, ignore_index=True) for name, parts in combined.items()}


if __name__ == "__main__":
    # A quick look at what the simulator produces (takes about 15 seconds).
    data = simulate_farms()
    print("Rows per table:")
    for name, df in data.items():
        print(f"  {name:16} {len(df):6}")
    health, livestock = data["health"], data["livestock"]
    ill = health[health["record_type"] == "ILLNESS"].merge(
        livestock[["animal_id", "species"]], on="animal_id")
    print("\nIllnesses per farm:")
    print(ill.groupby("farm").size().to_string())
    print("\nMost common illnesses:")
    print(ill.groupby(["species", "disease"]).size().sort_values(ascending=False).head(10).to_string())
    print("\nCauses of death:")
    print(data["mortality"]["cause_of_death"].value_counts().head(8).to_string())