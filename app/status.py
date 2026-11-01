"""The six farm statuses on the farmer's dashboard, as the farm asked for:"""
from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.farm import still_on_farm
from app.models import BreedingRecord, HealthRecord, HerdActivity, Livestock, PharmacyItem
from ml.reference import DEWORM_EVERY_DAYS, FARM_VACCINES, VACCINES

CALF_MONTHS = 12          # cattle younger than this are calves
UNWELL_DAYS = 14          # an illness or treatment this recent means "unwell" (the ML model's window too)
OUTLOOK_ALERT_DAYS = 30   # a routine due within a month is an Alert
OUTLOOK_DAYS = 90         # the outlook looks three months ahead
DEWORMED_SPECIES = ("CATTLE", "GOAT", "SHEEP")


def months_old(animal, today):
    born = animal.date_of_birth
    if born is None:
        return None
    return (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)


def on_farm(farm_id):
    return Livestock.query.filter(Livestock.farmer_id == farm_id, still_on_farm())


# --------------------------------------------------------------- 1. animals

def animal_counts(farm_id, today=None):
    """The total, and cattle in the groups the farm uses."""
    today = today or date.today()
    animals = on_farm(farm_id).all()
    mothers = {dam_id for (dam_id,) in db.session.query(BreedingRecord.animal_id)
               .filter(BreedingRecord.status == "SUCCESSFUL BIRTH")}
    groups = {"Calves": 0, "Heifers": 0, "Cows": 0, "Steers": 0, "Bulls": 0}    
    for animal in (a for a in animals if a.species == "CATTLE"):
        age = months_old(animal, today)
        if age is not None and age < CALF_MONTHS:
            groups["Calves"] += 1
        elif animal.gender == "MALE":
            groups["Steers" if animal.castrated else "Bulls"] += 1
        elif animal.animal_id in mothers:
            groups["Cows"] += 1
        else:
            groups["Heifers"] += 1
    others = {}
    for animal in animals:
        if animal.species != "CATTLE":
            others[animal.species] = others.get(animal.species, 0) + 1
    return {"total": len(animals), "cattle": groups, "others": others}


# ---------------------------------------------------------------- 2. health

def unwell(farm_id, today=None):
    """Animals with an illness or treatment recorded in the last 14 days,
    newest first, each with its latest such record."""
    today = today or date.today()
    since = today - timedelta(days=UNWELL_DAYS)
    records = (HealthRecord.query.join(HealthRecord.animal)
               .filter(Livestock.farmer_id == farm_id, still_on_farm(),
                       HealthRecord.record_type.in_(("ILLNESS", "TREATMENT")), HealthRecord.date > since)
               .order_by(HealthRecord.date.desc(), HealthRecord.h_record_id.desc()).all())
    latest = {}
    for record in records:
        latest.setdefault(record.animal_id, record)          # the first one seen is the newest
    animals = list(latest.values())
    return {"state": "Alert" if animals else "OK", "tone": "bad" if animals else "good", "records": animals}


# ------------------------------------------------------------- 3. condition

def pregnant(farm_id, today=None):
    """Females expecting, soonest due first. Overdue ones are flagged."""
    today = today or date.today()
    events = (BreedingRecord.query.join(BreedingRecord.dam)
              .filter(Livestock.farmer_id == farm_id, still_on_farm(), BreedingRecord.status == "EXPECTANT")
              .all())
    events.sort(key=lambda e: e.expected_delivery_date or date.max)
    rows = [{"event": e, "overdue": bool(e.expected_delivery_date and e.expected_delivery_date < today),
             "days": (e.expected_delivery_date - today).days if e.expected_delivery_date else None}
            for e in events]
    return {"state": f"{len(rows)} pregnant" if rows else "None", "tone": "warn" if any(r["overdue"] for r in rows) else "good",
            "rows": rows, "next": rows[0] if rows else None}


# ---------------------------------------------------------------- 4. market

def market(farm_id):
    """Animals the farmer has marked to sell or to cull."""
    animals = (on_farm(farm_id).filter(Livestock.market_status.isnot(None))
               .order_by(Livestock.market_status.desc(), Livestock.tag_number).all())
    sell = sum(1 for a in animals if a.market_status == "SELL")
    return {"state": "Available" if animals else "None", "tone": "warn" if animals else "good",
            "animals": animals, "sell": sell, "cull": len(animals) - sell}


# -------------------------------------------------------------- 5. pharmacy

def pharmacy(farm_id):
    """Low if any medicine is at or below its reorder level (or out)."""
    items = PharmacyItem.query.filter_by(farmer_id=farm_id).order_by(PharmacyItem.name).all()
    low = [i for i in items if i.status != "OK"]
    out = [i for i in low if i.status == "OUT"]
    tone = "bad" if out else "warn" if low else "good"
    return {"state": "Low" if low else "OK", "tone": tone, "low": low, "out": out, "count": len(items)}


# --------------------------------------------------------------- 6. outlook

def outlook(farm_id, today=None):
    """When each herd's next deworming and vaccinations are due."""
    today = today or date.today()
    species_here = {s for (s,) in on_farm(farm_id).with_entities(Livestock.species).distinct()}
    due = []
    for species in sorted(species_here & set(DEWORMED_SPECIES)):
        last = (db.session.query(func.max(HerdActivity.date))
                .filter_by(farmer_id=farm_id, species=species, activity="DEWORMING").scalar())
        due.append(routine("Deworming", species, last, DEWORM_EVERY_DAYS, today))
    for vaccine in FARM_VACCINES:
        info = VACCINES[vaccine]
        for species in sorted(species_here & set(info["species"])):
            if not info["repeat_days"]:
                continue
            last = (db.session.query(func.max(HealthRecord.date)).join(HealthRecord.animal)
                    .filter(Livestock.farmer_id == farm_id, Livestock.species == species,
                            HealthRecord.record_type == "VACCINATION", HealthRecord.treatment == vaccine).scalar())
            due.append(routine(vaccine, species, last, info["repeat_days"], today))
    due.sort(key=lambda r: r["due"])
    soon = [r for r in due if r["days"] <= OUTLOOK_ALERT_DAYS]
    return {"state": "Alert" if soon else "OK", "tone": "bad" if soon else "good",
            "rows": [r for r in due if r["days"] <= OUTLOOK_DAYS], "soon": soon, "next": due[0] if due else None}


def routine(name, species, last, every_days, today):
    """One row of the outlook: what, for which herd, last done, next due."""
    next_due = last + timedelta(days=every_days) if last else today
    return {"name": name, "species": species, "last": last, "due": next_due, "days": (next_due - today).days}


def all_statuses(farm_id):
    return {"animals": animal_counts(farm_id), "health": unwell(farm_id), "condition": pregnant(farm_id),
            "market": market(farm_id), "pharmacy": pharmacy(farm_id), "outlook": outlook(farm_id)}