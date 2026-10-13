"""Occasional weigh-ins, as on a farm like Kwetu that rarely weighs.

weighing_step   on a couple of herd weigh days a year, weigh each species
expected_weight the weight an animal of this age "should" be
"""
from datetime import date, timedelta

import numpy as np

from ml.reference import (
    GROWTH, ILLNESS_WEIGHT_DROP, MISSED_WEIGH_CHANCE, WEIGH_DAYS_PER_YEAR,
)


def expected_weight(species, age_days):
    """Growth curve: from birth weight up toward adult weight, reaching
    about 90% of the way by `grown_by` days (it levels off, like real
    growth, instead of rising forever)."""
    g = GROWTH[species]
    rate = np.log(10) / g["grown_by"]       # chosen so 90% is reached at grown_by
    return g["adult"] - (g["adult"] - g["birth"]) * np.exp(-rate * age_days)


def plan_weigh_days(farm, year):
    """Pick this year's weigh days for each species at random."""
    for species in GROWTH:
        days = farm.rng.choice(365, size=WEIGH_DAYS_PER_YEAR, replace=False)
        farm.weigh_days[(species, year)] = {date(year, 1, 1) + timedelta(days=int(d)) for d in days}


def weighing_step(farm, day):
    rng = farm.rng
    if (next(iter(GROWTH)), day.year) not in farm.weigh_days:
        plan_weigh_days(farm, day.year)
    for species in GROWTH:
        if day not in farm.weigh_days[(species, day.year)]:
            continue
        for animal in farm.on_farm(species):
            if rng.random() < MISSED_WEIGH_CHANCE:
                continue
            # Each animal has its own build: some are simply bigger.
            weight = expected_weight(species, animal.age_days(day)) * rng.normal(1.0, 0.08)
            # A recently sick animal has lost some weight.
            if animal.last_illness and 0 <= (day - animal.last_illness).days <= 30:
                weight *= 1 - rng.uniform(*ILLNESS_WEIGHT_DROP)
            farm.weights.append({
                "animal_id": animal.animal_id, "date": day,
                "weight": round(float(weight), 3 if species == "CHICKEN" else 1),
            })