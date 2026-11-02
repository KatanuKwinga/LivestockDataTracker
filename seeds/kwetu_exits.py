"""Load the deaths, sales and other exits"""
from openpyxl import load_workbook

from app import create_app
from app.extensions import db
from app.models import CommercialInfo, Livestock, MortalityRecord, User

EMAIL = "katanukavilakwinga@gmail.com"
WORKBOOK = "seeds/data/Kwetu_Animals_and_Records.xlsx"

app = create_app()

with app.app_context():
    farm_id = User.query.filter_by(email=EMAIL).first().farmer.farmer_id

    # Look up each animal by its tag, only on this farm.
    animals = {a.tag_number: a for a in Livestock.query.filter_by(farmer_id=farm_id)}

    workbook = load_workbook(WORKBOOK, read_only=True)

    deaths = 0
    for row in workbook["Deaths"].iter_rows(min_row=2, values_only=True):
        when, tag, age, cause, note = row[0], row[1], row[4], row[5], row[6]
        if tag is None:
            continue
        db.session.add(MortalityRecord(animal_id=animals[tag].animal_id, date_of_death=when.date(),
                                       age_at_death=age, cause_of_death=cause, description=note))
        deaths += 1

    sales = others = 0
    for row in workbook["Sales & exits"].iter_rows(min_row=2, values_only=True):
        when, tag, what, amount, buyer, note = row[0], row[1], row[4], row[5], row[6], row[9]
        if tag is None:
            continue
        animal_id = animals[tag].animal_id
        if what == "Sold":
            db.session.add(CommercialInfo(animal_id=animal_id, transaction_type="SELL", date=when.date(),
                                          amount=amount, other_party=buyer))
            sales += 1
        elif what == "Given away / eaten":
            db.session.add(CommercialInfo(animal_id=animal_id, transaction_type="SELL", date=when.date(),
                                          amount=0, other_party=f"Given away: {note}"[:100]))
            others += 1
        else:
            # "Lost" or "Missing (count correction)": the app has no box for these,
            # so they are recorded as a mortality with that reason.
            db.session.add(MortalityRecord(animal_id=animal_id, date_of_death=when.date(),
                                           cause_of_death=what, description=note))
            others += 1

    db.session.commit()
    print("deaths", deaths, "sales", sales, "other exits", others)