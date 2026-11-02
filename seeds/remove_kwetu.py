"""Remove everything the Kwetu seed scripts loaded, and nothing else.

    python -m seeds.remove_kwetu          only counts what would be removed
    python -m seeds.remove_kwetu --yes    removes it
"""
import sys

from openpyxl import load_workbook
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (BreedingRecord, CommercialInfo, HealthRecord, HerdActivity, Livestock, MortalityRecord,
                        PharmacyItem, ProductionData, StockMovement, User, WeightRecord)

EMAIL = "katanukavilakwinga@gmail.com"
WORKBOOK = "seeds/data/Kwetu_Animals_and_Records.xlsx"
MARK = "[kwetu]"

app = create_app()

with app.app_context():
    farm_id = User.query.filter_by(email=EMAIL).first().farmer.farmer_id
    really = "--yes" in sys.argv

    # What to remove: things marked [kwetu] on this farm...
    animal_ids = [a.animal_id for a in Livestock.query.filter(Livestock.farmer_id == farm_id,
                                                              Livestock.description.startswith(MARK))]
    medicines = PharmacyItem.query.filter(PharmacyItem.farmer_id == farm_id,
                                          PharmacyItem.notes.startswith(MARK)).all()
    # ...and the group sessions from the workbook (they weren't marked), found by date and product.
    from_workbook = {(row[0].date(), row[3]) for row in load_workbook(WORKBOOK, read_only=True)["Group treatments"]
                     .iter_rows(min_row=2, values_only=True) if row[1]}
    sessions = [s for s in HerdActivity.query.filter_by(farmer_id=farm_id) if (s.date, s.product) in from_workbook]

    print(f"Animals: {len(animal_ids)}  medicines: {len(medicines)}  group sessions: {len(sessions)}")
    if not really:
        print("Nothing removed. Run again with --yes to remove them.")
        sys.exit()

    births = select(BreedingRecord.b_record_id).where(BreedingRecord.animal_id.in_(animal_ids))
    health = select(HealthRecord.h_record_id).where(HealthRecord.animal_id.in_(animal_ids))

    # 1. Things that point AT these animals but aren't theirs keep existing, without the link:
    #    a calf registered later whose mother was a Kwetu cow, a medicine line used on one, a father.
    Livestock.query.filter(Livestock.b_record_id.in_(births)).update({"b_record_id": None}, synchronize_session=False)
    StockMovement.query.filter(StockMovement.animal_id.in_(animal_ids)).update({"animal_id": None}, synchronize_session=False)
    StockMovement.query.filter(StockMovement.health_record_id.in_(health)).update({"health_record_id": None}, synchronize_session=False)
    BreedingRecord.query.filter(BreedingRecord.sire_id.in_(animal_ids)).update({"sire_id": None}, synchronize_session=False)

    # 2. The animals' own records first, because each one points at its animal.
    for model in (HealthRecord, WeightRecord, ProductionData, CommercialInfo, MortalityRecord, BreedingRecord):
        removed = model.query.filter(model.animal_id.in_(animal_ids)).delete(synchronize_session=False)
        print(f"  {model.__tablename__}: {removed}")

    # 3. Then the animals, the medicines (their ledger lines go with them) and the sessions.
    print(f"  livestock: {Livestock.query.filter(Livestock.animal_id.in_(animal_ids)).delete(synchronize_session=False)}")
    for item in medicines:
        db.session.delete(item)
    for session in sessions:
        db.session.delete(session)

    db.session.commit()
    print("Removed.")