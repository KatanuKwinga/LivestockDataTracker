"""Load the demo farm (Kilima Farm, a fictional farm modelled on Kwetu) from
its workbook into one farmer's account, or take it out again.

    python -m seeds.demo_farm --farmer-email you@example.com            load it
    python -m seeds.demo_farm --farmer-email you@example.com --remove   remove it

Every animal, medicine and group session it adds is marked [demo], so
--remove takes away exactly what was loaded and nothing else.
"""
import argparse
import sys

import pandas as pd
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (BreedingRecord, CommercialInfo, Departure, HealthRecord, HerdActivity, Livestock,
                        MortalityRecord, PharmacyItem, ProductionData, StockMovement, User, WeightRecord)
from app.models.departure import REASONS
from app.stock import add_line

WORKBOOK = "seeds/data/Demo_Farm_Records.xlsx"
MARK = "[demo]"

# The workbook's words -> the codes the app stores.
BREEDING_STATUS = {"Gave birth": "SUCCESSFUL BIRTH", "Lost the pregnancy": "NO BIRTH", "Pregnant": "EXPECTANT"}
TRANSACTION = {"Bought": "BUY", "Sold": "SELL"}
MARKET = {"To sell": "SELL", "To cull": "CULL"}
ACTIVITY = {"Tick spraying": "TICK_SPRAY", "Deworming": "DEWORMING", "Vaccination": "VACCINATION"}
REASON_CODE = {label: code for code, label in REASONS.items()}


# --- reading cells: an empty Excel cell arrives as NaN, which the database must get as NULL
def day(value):
    return None if pd.isna(value) else pd.Timestamp(value).date()


def text(value):
    return None if pd.isna(value) or str(value).strip() == "" else str(value).strip()


def number(value):
    return None if pd.isna(value) else float(value)


def rows(sheets, name):
    return sheets[name].itertuples(index=False)


def load(farm_id, user_id, sheets):
    """Add every sheet's records to the farm. Nothing is committed here."""
    # Animals first: everything else points at them. flush() asks the
    # database for their ids without committing yet.
    animals = {}
    for r in rows(sheets, "Animals"):
        market = MARKET.get(text(r.Market) or "")
        animal = Livestock(farmer_id=farm_id, tag_number=r.Tag, species=r.Species.upper(), gender=r.Sex.upper(),
                           breed=text(r.Breed), date_of_birth=day(r[4]), castrated=text(r.Castrated) == "Yes",
                           market_status=market, market_marked_on=day(r[8]) if market else None,
                           market_note=text(r[9]) if market else None, description=f"{MARK} Kilima Farm (demo)")
        db.session.add(animal)
        animals[r.Tag] = animal
    db.session.flush()
    ids = {tag: animal.animal_id for tag, animal in animals.items()}
    print(f"  animals: {len(animals)}")

    # Breeding: one record per pregnancy; each newborn points back at its birth.
    for r in rows(sheets, "Breeding"):
        record = BreedingRecord(animal_id=ids[r[0]], sire_id=ids.get(text(r[1])), status=BREEDING_STATUS[r.Status],
                                expected_delivery_date=day(r.Expected), actual_delivery_date=day(r[4]),
                                num_stillborn=int(r[5]))
        db.session.add(record)
        for young in (text(r[6]) or "").split(", "):
            if young:
                animals[young].birth_event = record
    print(f"  breeding records: {len(sheets['Breeding'])}")

    db.session.add_all(HealthRecord(animal_id=ids[r.Tag], date=day(r.Date), record_type=r[3], disease=text(r.Disease),
                                    temperature=number(r[5]), treatment=text(r.Treatment), dosage=text(r.Dose),
                                    description=text(r.Notes))
                       for r in rows(sheets, "Health records"))
    db.session.add_all(WeightRecord(animal_id=ids[r.Tag], date=day(r.Date), weight=float(r[2]))
                       for r in rows(sheets, "Weights"))
    db.session.add_all(ProductionData(animal_id=ids[r.Tag], date=day(r.Date), item=r.Product,
                                      yield_amount=float(r.Amount), metric=r.Unit)
                       for r in rows(sheets, "Milk and eggs"))
    db.session.add_all(CommercialInfo(animal_id=ids[r.Tag], date=day(r.Date), transaction_type=TRANSACTION[r.Type],
                                      amount=float(r[3]), other_party=text(r[4]), location=text(r.Where))
                       for r in rows(sheets, "Purchases and sales"))
    db.session.add_all(MortalityRecord(animal_id=ids[r.Tag], date_of_death=day(r.Date),
                                       age_at_death=None if pd.isna(r[2]) else int(r[2]),
                                       cause_of_death=text(r[3]), description=text(r.Notes))
                       for r in rows(sheets, "Deaths"))
    db.session.add_all(Departure(animal_id=ids[r.Tag], date=day(r.Date), reason=REASON_CODE[r.Reason],
                                 description=text(r.Notes))
                       for r in rows(sheets, "Left the farm"))
    db.session.add_all(HerdActivity(farmer_id=farm_id, species=r.Species.upper(), date=day(r.Date),
                                    activity=ACTIVITY[r.Activity], product=text(r.Product),
                                    notes=f"{MARK} {text(r.Notes) or ''}".strip())
                       for r in rows(sheets, "Group treatments"))
    db.session.flush()
    print("  health, weights, milk and eggs, purchases and sales, deaths, departures, group treatments: added")

    # Pharmacy: the medicines, then their ledger in date order. add_line()
    # keeps each balance in step with its lines, as everywhere in the app.
    medicines = {}
    for r in rows(sheets, "Pharmacy medicines"):
        medicines[r.Medicine] = PharmacyItem(farmer_id=farm_id, name=r.Medicine, disease=r.Treats, kind=r.Type,
                                             unit=r.Unit, quantity=0, reorder_level=float(r[4]), added_by=user_id,
                                             notes=f"{MARK} Kilima Farm (demo)")
        db.session.add(medicines[r.Medicine])
    for r in rows(sheets, "Pharmacy ledger"):
        delivery = {}
        if r.Line == "RECEIVED":
            delivery = {"cost": number(r[5]), "supplier": text(r.Supplier), "expiry_date": day(r[7])}
        add_line(medicines[r.Medicine], r.Line, float(r.Amount), day(r.Date), user_id, remarks=text(r.Remarks), **delivery)
    print(f"  medicines: {len(medicines)}, ledger lines: {len(sheets['Pharmacy ledger'])}")


def remove(farm_id):
    """Take out everything marked [demo] on this farm, children before parents."""
    animal_ids = select(Livestock.animal_id).where(Livestock.farmer_id == farm_id,
                                                    Livestock.description.startswith(MARK))
    births = select(BreedingRecord.b_record_id).where(BreedingRecord.animal_id.in_(animal_ids))
    health = select(HealthRecord.h_record_id).where(HealthRecord.animal_id.in_(animal_ids))
    # Links from things that stay (none, normally) are cleared, not deleted.
    Livestock.query.filter(Livestock.b_record_id.in_(births)).update({"b_record_id": None}, synchronize_session=False)
    StockMovement.query.filter(StockMovement.animal_id.in_(animal_ids)).update({"animal_id": None}, synchronize_session=False)
    StockMovement.query.filter(StockMovement.health_record_id.in_(health)).update({"health_record_id": None}, synchronize_session=False)
    BreedingRecord.query.filter(BreedingRecord.sire_id.in_(animal_ids)).update({"sire_id": None}, synchronize_session=False)
    for model in (HealthRecord, WeightRecord, ProductionData, CommercialInfo, MortalityRecord, Departure, BreedingRecord):
        removed = model.query.filter(model.animal_id.in_(animal_ids)).delete(synchronize_session=False)
        print(f"  {model.__tablename__}: {removed}")
    print(f"  livestock: {Livestock.query.filter(Livestock.animal_id.in_(animal_ids)).delete(synchronize_session=False)}")
    for item in PharmacyItem.query.filter(PharmacyItem.farmer_id == farm_id, PharmacyItem.notes.startswith(MARK)):
        db.session.delete(item)                      # its ledger lines go with it (cascade)
    sessions = HerdActivity.query.filter(HerdActivity.farmer_id == farm_id, HerdActivity.notes.startswith(MARK))
    print(f"  herd_activities: {sessions.delete(synchronize_session=False)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--farmer-email", required=True)
    parser.add_argument("--remove", action="store_true", help="take the demo farm out again")
    parser.add_argument("--workbook", default=WORKBOOK)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=args.farmer_email.strip().lower()).first()
        if user is None or user.farmer is None:
            sys.exit(f"No farmer account with the email {args.farmer_email}. Register it in the app first.")
        farm_id = user.farmer.farmer_id
        already = Livestock.query.filter(Livestock.farmer_id == farm_id, Livestock.description.startswith(MARK)).count()

        if args.remove:
            remove(farm_id)
            db.session.commit()
            print("Demo farm removed.")
            return
        if already:
            sys.exit(f"This farm already has {already} demo animals. Run with --remove first to load it again.")

        sheets = pd.read_excel(args.workbook, sheet_name=None)
        clash = set(sheets["Animals"]["Tag"]) & {t for (t,) in db.session.query(Livestock.tag_number).filter_by(farmer_id=farm_id)}
        if clash:
            sys.exit(f"{len(clash)} tags are already used on this farm, e.g. {sorted(clash)[:5]}. Use a new farmer account.")
        print(f"Loading {args.workbook} into {user.email}'s farm...")
        load(farm_id, user.id, sheets)
        db.session.commit()                          # all or nothing: one commit at the end
        print("Done.")


if __name__ == "__main__":
    main()