"""The simulated farm: its animals, the records it writes, and the clock.

A simulation is a loop over days. On each day every "step" function gets
a turn (births, sales, later vaccinations and illnesses), and each step
can add animals or write records. Because everything happens in date
order, nothing can happen to an animal after it has died or been sold.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ml.rainfall import FORECAST_DAYS, shifted_history
from ml.reference import FARM_VACCINES, FRAILTY_SPREAD, SPECIES_INFO

@dataclass
class Animal:
    #One animal's state while the simulation runs. 
    animal_id: int
    tag_number: str
    species: str
    gender: str
    breed: str
    date_of_birth: date
    b_record_id: int | None = None   # the birth event it came from, if born on the farm
    births: int = 0                  # how many times she has given birth
    last_birth: date | None = None
    exit_date: date | None = None    # the day it died or was sold
    exit_reason: str | None = None   # "DIED" or "SOLD"

    # Vaccine bookkeeping, one entry per vaccine name (filled in by routines.py).
    # field(default_factory=dict) gives every animal its OWN empty dict
    vaccine_due: dict = field(default_factory=dict)       # official due date (None = course finished)
    vaccine_next_try: dict = field(default_factory=dict)  # when the farmer will actually do it
    vaccine_doses: dict = field(default_factory=dict)     # doses given so far
    vaccines_ready: bool = False                          # bookkeeping set up yet?
    last_illness: date | None = None                      # start of its latest illness
    frailty: float = 1.0

    def age_days(self, day):
        return (day - self.date_of_birth).days

    def on_farm(self):
        return self.exit_date is None


class Farm:
    #Holds everything the simulation creates.
    def __init__(self, start, end, seed=42, vaccines=FARM_VACCINES, environment=None, rain_years_back=0):
        # One random-number generator for the whole run: the same seed
        # always gives exactly the same farm, so results can be repeated.
        self.rng = np.random.default_rng(seed)
        self.start = start
        self.end = end
        self.vaccines = tuple(vaccines)
        # The farm's surroundings (ENVIRONMENTS in reference.py): 1.0 = average,
        # 2.0 = twice the usual risk of the diseases it drives. None = all average.
        self.environment = dict(environment or {})
        # The farm's weather: Thika's real daily rainfall, from `rain_years_back`
        # years earlier (0 = the real rain on these dates). From 60 days before
        # the start, so the first days have a rain history, to 16 days after the end.
        self.rain_years_back = rain_years_back
        self.rain = shifted_history(start - timedelta(days=60), end + timedelta(days=FORECAST_DAYS),
                                    rain_years_back)
        # Rain in the 30 days before each day, and in the 30 days before those:
        # looked up every day for every condition, so worked out once here.
        last30 = self.rain.rolling(30).sum().shift(1)
        self.rain_last30 = {d.date(): v for d, v in last30.items()}
        self.rain_prev30 = {d.date(): v for d, v in last30.shift(30).items()}
        self.animals = []                        # every animal ever, alive or not
        self.tag_counts = {s: 0 for s in SPECIES_INFO}
        self.breeding = []
        self.mortality = []
        self.commercial = []
        self.health = []              # health_records rows
        self.herd_activities = []     # one row per group tick-spray session
        # Herd-level routine state, per species (filled in by routines.py).
        self.weights = []             # weight_records rows
        self.weigh_days = {}          # species -> planned weigh days this year
        self.last_spray = {}
        self.spray_week_missed = {}
        self.last_deworm = {}
        self.next_deworm = {}
        self.missed_spray_weeks = {}  # species -> Mondays of weeks with no spraying
        self.recent_cases = {}        # (species, condition name) -> dates of new cases

    # Animals

    def add_animal(self, species, gender, breed, date_of_birth, b_record_id=None):
        """Register an animal with the next free id and tag (C001, C002...)."""
        self.tag_counts[species] += 1
        animal = Animal(
            animal_id=len(self.animals) + 1,
            tag_number=f"{SPECIES_INFO[species]['prefix']}{self.tag_counts[species]:03d}",
            species=species, gender=gender, breed=breed,
            date_of_birth=date_of_birth, b_record_id=b_record_id,         
            frailty=float(self.rng.lognormal(-FRAILTY_SPREAD ** 2 / 2, FRAILTY_SPREAD)),
        )
        self.animals.append(animal)
        return animal

    def on_farm(self, species=None):
        """Animals currently on the farm (not dead, not sold)."""
        return [a for a in self.animals
                if a.on_farm() and (species is None or a.species == species)]

    def record_death(self, animal, day, cause, description=""):
        animal.exit_date, animal.exit_reason = day, "DIED"
        self.mortality.append({
            "animal_id": animal.animal_id, "date_of_death": day,
            "age_at_death": animal.age_days(day) // 365,   # whole years, like Livestock.age
            "cause_of_death": cause, "description": description,
        })

    def record_sale(self, animal, day, amount, other_party="Local buyer"):
        animal.exit_date, animal.exit_reason = day, "SOLD"
        self.commercial.append({
            "animal_id": animal.animal_id, "transaction_type": "SELL", "date": day,
            "amount": float(amount), "other_party": other_party, "location": "Farm gate",
        })

    # Output

    def tables(self):
        """Every record list as a DataFrame, shaped like our tables."""
        livestock = pd.DataFrame([{
            "animal_id": a.animal_id, "tag_number": a.tag_number, "species": a.species,
            "gender": a.gender, "breed": a.breed, "date_of_birth": a.date_of_birth,
            "b_record_id": a.b_record_id,
        } for a in self.animals])
        return {
            "livestock": livestock,
            "breeding": pd.DataFrame(self.breeding, columns=[
                "b_record_id", "animal_id", "sire_id", "status",
                "expected_delivery_date", "actual_delivery_date", "num_stillborn"]),
            "mortality": pd.DataFrame(self.mortality, columns=[
                "animal_id", "date_of_death", "age_at_death", "cause_of_death", "description"]),
            "commercial": pd.DataFrame(self.commercial, columns=[
                "animal_id", "transaction_type", "date", "amount", "other_party", "location"]),
            "health": pd.DataFrame(self.health, columns=[
                "animal_id", "date", "record_type", "disease", "temperature",
                "description", "treatment", "dosage"]),
            "herd_activities": pd.DataFrame(self.herd_activities, columns=[
                "date", "species", "activity", "product"]),
                        "weights": pd.DataFrame(self.weights, columns=["animal_id", "date", "weight"]),
            # Not a table in the app: the farm's daily rainfall, which the app
            # gets from the weather service instead.
            "rain": pd.DataFrame({"date": self.rain.index.date, "rain_mm": self.rain.to_numpy()}),
        }

def run(farm, steps):
    """The clock: call every step once for each day from start to end."""
    day = farm.start
    while day <= farm.end:
        for step in steps:
            step(farm, day)
        day += timedelta(days=1)
    return farm
