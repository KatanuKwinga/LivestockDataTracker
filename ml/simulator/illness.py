"""The illness engine: who falls sick, with what, and how it ends.

Each condition in ml/reference.py has a base chance (from its rank). That
chance is multiplied up or down by its triggers: the rains, a missed tick
spraying, overdue deworming, the animal's vaccine status, and recent cases
in the herd. This is where the reference table turns into records.
"""
from datetime import timedelta

from ml.reference import (
    CONDITIONS, DEWORM_OVERDUE_MULTIPLIER, FEVER_RISE, ILLNESS_RECOVERY_DAYS,
    LONG_RAINS, OUTBREAK_BOOST_PER_CASE, OUTBREAK_DAYS, OUTBREAK_MAX_MULTIPLIER,
    RAINS_MULTIPLIER, REPEAT_TREATMENT_CHANCES, RESISTANT_BREED_MULTIPLIER,
    SHORT_RAINS, SPECIES_INFO, SPRAY_LAPSE_MULTIPLIER, SPRAY_LAPSE_WINDOW_DAYS,
    VACCINE_UP_TO_DATE_MULTIPLIER, YEARLY_CHANCE,
)
from ml.simulator.routines import deworming_days_overdue, vaccine_status

AFTER_BIRTH_DAYS = 3


#Chances
def chance_per_day(condition):
    """The base daily chance for an unprotected animal."""
    if condition.after_birth:
        window = AFTER_BIRTH_DAYS
    elif condition.max_age_days:
        window = min(condition.max_age_days, 365)
    else:
        window = 365
    return 1 - (1 - YEARLY_CHANCE[condition.rank]) ** (1 / window)


def can_get(animal, condition, day):
    """The 'who gets it' rules: sex, age limit, days after giving birth."""
    if condition.sex and animal.gender != condition.sex:
        return False
    if condition.max_age_days and animal.age_days(day) >= condition.max_age_days:
        return False
    if condition.after_birth:
        return animal.last_birth is not None and 0 <= (day - animal.last_birth).days < AFTER_BIRTH_DAYS
    return True


def herd_multiplier(farm, species, condition, day):
    """The part of the risk shared by the whole herd today: rains, missed
    spraying, overdue deworming, and how many recent cases there are."""
    m = 1.0
    if "rains" in condition.triggers:
        if day.month in LONG_RAINS:
            m *= RAINS_MULTIPLIER["long"]
        elif day.month in SHORT_RAINS:
            m *= RAINS_MULTIPLIER["short"]
    if "spray_lapse" in condition.triggers:
        earliest, latest = SPRAY_LAPSE_WINDOW_DAYS
        if any(earliest <= (day - missed).days <= latest
               for missed in farm.missed_spray_weeks.get(species, [])):
            m *= SPRAY_LAPSE_MULTIPLIER
    if "deworm_overdue" in condition.triggers and deworming_days_overdue(farm, species, day) > 0:
        m *= DEWORM_OVERDUE_MULTIPLIER
    if "contagious" in condition.triggers:
        recent = [d for d in farm.recent_cases.get((species, condition.name), [])
                  if (day - d).days <= OUTBREAK_DAYS]
        m *= min(1 + OUTBREAK_BOOST_PER_CASE * len(recent), OUTBREAK_MAX_MULTIPLIER)
    return m


def daily_risk(animal, condition, day, herd_m):
    """One animal's chance of one condition today. herd_m is the herd
    multiplier, worked out once per species per day to save time."""
    if not can_get(animal, condition, day):
        return 0.0
    risk = chance_per_day(condition) * herd_m * animal.frailty
    if condition.vaccine and vaccine_status(animal, condition.vaccine, day) == "up_to_date":
        risk *= VACCINE_UP_TO_DATE_MULTIPLIER
    if animal.breed in condition.resistant_breeds:
        risk *= RESISTANT_BREED_MULTIPLIER
    return risk


#The step
def illness_step(farm, day):
    """Give every animal on the farm a chance of each condition today."""
    rng = farm.rng
    for species, conditions in CONDITIONS.items():
        animals = farm.on_farm(species)
        if not animals:
            continue
        # Newborn deaths (group M) are handled in herd.py, not here.
        active = [c for c in conditions if c.group != "M"]
        herd_m = {c.name: herd_multiplier(farm, species, c, day) for c in active}
        for animal in animals:
            if animal.last_illness and (day - animal.last_illness).days < ILLNESS_RECOVERY_DAYS:
                continue                                  # still recovering
            for condition in active:
                if rng.random() < daily_risk(animal, condition, day, herd_m[condition.name]):
                    fall_ill(farm, animal, condition, day)
                    break                                 # one new condition per day at most


def fall_ill(farm, animal, condition, day):
    """Write the illness and its follow-up treatments, as Kwetu's log does,
    and decide whether the animal dies."""
    rng = farm.rng
    normal = SPECIES_INFO[animal.species]["normal_temp"]
    # Temperature is only taken when an animal is sick, so every illness
    # record has one; it is a fever only if the condition causes fever.
    temp = normal + (rng.uniform(*FEVER_RISE) if condition.fever else rng.uniform(-0.3, 0.3))
    animal.last_illness = day
    farm.recent_cases.setdefault((animal.species, condition.name), []).append(day)

    # Injuries (group X) are treatments, not illnesses: the model must not
    # count them as a "new illness".
    record_type = "TREATMENT" if condition.group == "X" else "ILLNESS"
    records = [(day, record_type, round(temp, 1), "Reported sick by worker")]

    follow_ups = int(rng.choice(len(REPEAT_TREATMENT_CHANCES), p=REPEAT_TREATMENT_CHANCES))
    treat_day = day
    for _ in range(follow_ups):
        treat_day += timedelta(days=int(rng.integers(1, 4)))      # 1-3 days later
        temp = max(normal, temp - rng.uniform(0.3, 1.0))          # fever coming down
        records.append((treat_day, "TREATMENT", round(temp, 1), "Repeat treatment"))

    # Some treated cases still die, a few days after falling ill.
    died_on = None
    if rng.random() < condition.death_chance:
        died_on = day + timedelta(days=int(rng.integers(1, 15)))

    for when, kind, temperature, description in records:
        if when > farm.end or (died_on and when > died_on):
            break
        farm.health.append({
            "animal_id": animal.animal_id, "date": when, "record_type": kind,
            "disease": condition.name, "temperature": temperature,
            "description": description, "treatment": condition.treatment,
            "dosage": "As per vet instructions",
        })
    if died_on and died_on <= farm.end:
        farm.record_death(animal, died_on, condition.name, "Died despite treatment")