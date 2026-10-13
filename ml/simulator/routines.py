"""Farm routines: vaccinations, deworming and tick spraying.

vaccination - each animal gets each of the farm's vaccines when due (70% on time)
deworming - every 90 days each species is dewormed as a group
spraying - cattle sprayed twice a week, goats and sheep once; some weeks missed

"""
from datetime import timedelta

from ml.reference import (
    DEWORM_DELAY_DAYS, DEWORM_EVERY_DAYS, DEWORM_LATE_CHANCE, DEWORM_MIN_AGE_DAYS,
    DEWORMER, MISSED_SPRAY_WEEK_CHANCE, SPRAY_PRODUCT, SPRAYS_PER_WEEK,
    VACCINE_DELAY_DAYS, VACCINE_ON_TIME_CHANCE, VACCINES,
)

# Which weekdays each species is sprayed (Monday = 0). Twice a week ->
# Monday and Thursday; once a week -> Wednesday.
SPRAY_WEEKDAYS = {2: (0, 3), 1: (2,)}


#Vaccinations

def setup_vaccines(farm, animal):
    """Work out when each of this animal's vaccines is next due."""
    rng = farm.rng
    for name in farm.vaccines: #only the vaccines in the farm's plan
        vaccine = VACCINES[name]
        if animal.species not in vaccine["species"]:
            continue
        first_due = animal.date_of_birth + timedelta(days=vaccine["first_dose_days"])
        animal.vaccine_doses[name] = 0
        if first_due >= farm.start:                  # not old enough yet when we start
            due = first_due
        elif vaccine["doses"] is not None:           # a fixed course: assume it was completed
            animal.vaccine_doses[name] = vaccine["doses"]
            due = None
        else:                                        # repeating: last dose was some time ago
            animal.vaccine_doses[name] = 1           # that earlier dose (not written as a record)
            since_last = int(rng.integers(0, vaccine["repeat_days"]))
            due = farm.start - timedelta(days=since_last) + timedelta(days=vaccine["repeat_days"])
        animal.vaccine_due[name] = due
        animal.vaccine_next_try[name] = due
    animal.vaccines_ready = True


def vaccination_step(farm, day):
    """On the day the farmer plans to vaccinate, it happens 70% of the time.
    Otherwise it is put off for a few weeks, and the animal is overdue."""
    rng = farm.rng
    for animal in farm.on_farm():
        if not animal.vaccines_ready:
            setup_vaccines(farm, animal)
        for name, next_try in animal.vaccine_next_try.items():
            if next_try is None or day < next_try:
                continue
            if rng.random() < VACCINE_ON_TIME_CHANCE:
                give_vaccine(farm, animal, name, day)
            else:
                low, high = VACCINE_DELAY_DAYS
                animal.vaccine_next_try[name] = day + timedelta(days=int(rng.integers(low, high + 1)))


def give_vaccine(farm, animal, name, day):
    """Write the VACCINATION record and schedule the next dose (if any)."""
    vaccine = VACCINES[name]
    farm.health.append({
        "animal_id": animal.animal_id, "date": day, "record_type": "VACCINATION",
        "disease": None, "temperature": None, "description": "Routine vaccination",
        "treatment": name, "dosage": "1 dose",
    })
    animal.vaccine_doses[name] += 1
    finished = vaccine["doses"] is not None and animal.vaccine_doses[name] >= vaccine["doses"]
    if finished or vaccine["repeat_days"] is None:
        animal.vaccine_due[name] = None
    else:
        animal.vaccine_due[name] = day + timedelta(days=vaccine["repeat_days"])
    animal.vaccine_next_try[name] = animal.vaccine_due[name]


# Deworming

def deworming_step(farm, day):
    """Each species is dewormed together, every 90 days. Sometimes (20%)
    the session is put off by 2-6 weeks; until it happens, the herd is overdue."""
    rng = farm.rng
    for species, dewormer in DEWORMER.items():
        if species not in farm.next_deworm:
            # Invented history: the last session was 0-89 days before the start.
            farm.last_deworm[species] = farm.start - timedelta(days=int(rng.integers(0, DEWORM_EVERY_DAYS)))
            farm.next_deworm[species] = farm.last_deworm[species] + timedelta(days=DEWORM_EVERY_DAYS)
        if day < farm.next_deworm[species]:
            continue
        if rng.random() < DEWORM_LATE_CHANCE:
            low, high = DEWORM_DELAY_DAYS
            farm.next_deworm[species] = day + timedelta(days=int(rng.integers(low, high + 1)))
            continue
        for animal in farm.on_farm(species):
            if animal.age_days(day) >= DEWORM_MIN_AGE_DAYS:
                farm.health.append({
                    "animal_id": animal.animal_id, "date": day, "record_type": "TREATMENT",
                    "disease": None, "temperature": None, "description": "Routine deworming",
                    "treatment": dewormer, "dosage": "As per label",
                })
        farm.last_deworm[species] = day
        farm.next_deworm[species] = day + timedelta(days=DEWORM_EVERY_DAYS)


# Spraying

def spraying_step(farm, day):
    """Group tick spraying, written to herd_activities (one row per session,
    not one per animal). Each Monday decides whether this whole week's
    spraying is missed, e.g. because the acaricide ran out."""
    rng = farm.rng
    for species, per_week in SPRAYS_PER_WEEK.items():
        farm.last_spray.setdefault(species, farm.start - timedelta(days=1))
        if day.weekday() == 0:
            farm.spray_week_missed[species] = rng.random() < MISSED_SPRAY_WEEK_CHANCE
        if day.weekday() in SPRAY_WEEKDAYS[per_week] and not farm.spray_week_missed.get(species):
            farm.herd_activities.append({
                "date": day, "species": species, "activity": "TICK_SPRAY", "product": SPRAY_PRODUCT,
            })
            farm.last_spray[species] = day


# Helpers answer questions of whether the vaccine/deworming/spraying is overdue

def vaccine_status(animal, name, day):
    """'not_yet' (too young or course finished), 'up_to_date' or 'overdue'."""
    due = animal.vaccine_due.get(name)
    if due is not None and day > due:
        return "overdue"
    return "up_to_date" if animal.vaccine_doses.get(name) else "not_yet"


def deworming_days_overdue(farm, species, day):
    """0 if the group was dewormed in the last 90 days, else days late."""
    return max(0, (day - farm.last_deworm[species]).days - DEWORM_EVERY_DAYS)


def days_since_spray(farm, species, day):
    return (day - farm.last_spray[species]).days