"""The simulated farm: its animals, the records it writes, and the clock.

A simulation is a loop over days. On each day every "step" function gets
a turn (births, sales, later vaccinations and illnesses), and each step
can add animals or write records. Because everything happens in date
order, nothing can happen to an animal after it has died or been sold.
"""
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ml.reference import SPECIES_INFO


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

    def age_days(self, day):
        return (day - self.date_of_birth).days

    def on_farm(self):
        return self.exit_date is None


class Farm:
    #Holds everything the simulation creates.
    def __init__(self, start, end, seed=42):
        # One random-number generator for the whole run: the same seed
        # always gives exactly the same farm, so results can be repeated.
        self.rng = np.random.default_rng(seed)
        self.start = start
        self.end = end
        self.animals = []                        # every animal ever, alive or not
        self.tag_counts = {s: 0 for s in SPECIES_INFO}
        self.breeding = []
        self.mortality = []
        self.commercial = []

    # Animals

    def add_animal(self, species, gender, breed, date_of_birth, b_record_id=None):
        """Register an animal with the next free id and tag (C001, C002...)."""
        self.tag_counts[species] += 1
        animal = Animal(
            animal_id=len(self.animals) + 1,
            tag_number=f"{SPECIES_INFO[species]['prefix']}{self.tag_counts[species]:03d}",
            species=species, gender=gender, breed=breed,
            date_of_birth=date_of_birth, b_record_id=b_record_id,
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
        }


def run(farm, steps):
    """The clock: call every step once for each day from start to end."""
    day = farm.start
    while day <= farm.end:
        for step in steps:
            step(farm, day)
        day += timedelta(days=1)
    return farm
