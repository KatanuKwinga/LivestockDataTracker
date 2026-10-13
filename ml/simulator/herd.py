"""The herd: who is on the farm at the start, who is born, who is sold."""
from datetime import timedelta

from ml.reference import (
    AGE_LIMIT_DAYS, DECEMBER_SALE_SHARE, FIRST_BIRTH_AGE_DAYS, GESTATION_DAYS,
    NEWBORN_DEATH_CHANCE, NEWBORNS_PER_FEMALE_PER_YEAR, SALE_AGE_DAYS, SALE_MONTH,
    SALE_PRICE_KES, SPECIES_INFO, START_HERD, TWIN_CHANCE, WEAK_NEWBORN_MULTIPLIER,
)


def starting_herd(farm):
    """Add the starting animals, with random ages that fit their group:
    young = under a year old, adult = from 1 year up to the age limit."""
    rng = farm.rng
    for species, groups in START_HERD.items():
        breeds = SPECIES_INFO[species]["breeds"]
        for group, count in groups.items():
            age_group, sex = group.split("_")               # "adult_female" -> "adult", "female"
            for _ in range(count):
                if age_group == "young":
                    age = int(rng.integers(14, 365))
                else:
                    age = int(rng.integers(365, AGE_LIMIT_DAYS[species]))
                farm.add_animal(species, sex.upper(), str(rng.choice(breeds)),
                                farm.start - timedelta(days=age))


def births_step(farm, day):
    """Give each female who could give birth today a small chance to do so."""
    rng = farm.rng
    for species, yearly_newborns in NEWBORNS_PER_FEMALE_PER_YEAR.items():
        litter = 1 + TWIN_CHANCE[species]                 # average newborns per birth
        daily = yearly_newborns / litter / 365
        males = [a for a in farm.on_farm(species)
                 if a.gender == "MALE" and a.age_days(day) >= FIRST_BIRTH_AGE_DAYS[species]]
        for dam in farm.on_farm(species):
            if dam.gender != "FEMALE" or dam.age_days(day) < FIRST_BIRTH_AGE_DAYS[species]:
                continue
            # She can't give birth again until a whole pregnancy has passed.
            if dam.last_birth and (day - dam.last_birth).days < GESTATION_DAYS[species]:
                continue
            if rng.random() < daily:
                give_birth(farm, dam, day, males)


def give_birth(farm, dam, day, males):
    """Write the breeding record, add the newborn(s), and decide whether
    each newborn dies weak in its first two weeks."""
    rng = farm.rng
    species = dam.species
    twins = rng.random() < TWIN_CHANCE[species]
    sire = rng.choice(males) if males else None
    b_record_id = len(farm.breeding) + 1
    farm.breeding.append({
        "b_record_id": b_record_id, "animal_id": dam.animal_id,
        "sire_id": sire.animal_id if sire else None, "status": "SUCCESSFUL BIRTH",
        "expected_delivery_date": day + timedelta(days=int(rng.integers(-5, 6))),
        "actual_delivery_date": day, "num_stillborn": 0,
    })
    first_time = dam.births == 0
    dam.births += 1
    dam.last_birth = day

    # Weak newborns: more likely for twins and for a first-time mother
    # (the Kenyan kid study found the mother's parity mattered most).
    death_chance = NEWBORN_DEATH_CHANCE[species]
    if twins:
        death_chance *= WEAK_NEWBORN_MULTIPLIER
    if first_time:
        death_chance *= WEAK_NEWBORN_MULTIPLIER

    for _ in range(2 if twins else 1):
        calf = farm.add_animal(species, str(rng.choice(["MALE", "FEMALE"])), dam.breed,
                               day, b_record_id=b_record_id)
        if rng.random() < death_chance:
            # Its death is written now, dated a few days ahead. That takes it
            # off the farm straight away, so no later step (vaccination,
            # illness) writes records for a newborn that never joined the herd.
            died_on = day + timedelta(days=int(rng.integers(0, 15)))
            if died_on <= farm.end:
                farm.record_death(calf, died_on, "Weak at birth / starvation",
                                  "Born weak, did not suckle")


def sales_step(farm, day):
    """On the 15th of December, sell a share of the males old enough for
    market, at a price within that species' range."""
    if day.month != SALE_MONTH or day.day != 15:
        return
    rng = farm.rng
    for species, share in DECEMBER_SALE_SHARE.items():
        for animal in farm.on_farm(species):
            if (animal.gender == "MALE" and animal.age_days(day) >= SALE_AGE_DAYS[species]
                    and rng.random() < share):
                low, high = SALE_PRICE_KES[species]
                farm.record_sale(animal, day, round(rng.uniform(low, high), -2))
