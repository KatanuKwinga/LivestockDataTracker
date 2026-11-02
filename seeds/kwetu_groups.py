"""Load the group treatments (dips, sprays, dewormings) and the weights."""
from openpyxl import load_workbook

from app import create_app
from app.extensions import db
from app.models import HerdActivity, Livestock, User, WeightRecord

EMAIL = "katanukavilakwinga@gmail.com"
WORKBOOK = "seeds/data/Kwetu_Animals_and_Records.xlsx"

# The workbook's words -> the codes the app uses for each kind of session.
ACTIVITY = {
    "Tick spraying": "TICK_SPRAY",
    "Dipping": "TICK_SPRAY",
    "Deworming": "DEWORMING",
    "Deworming (injection)": "DEWORMING",
    "Group treatment": "TREATMENT",
    "Group treatment (vet)": "TREATMENT",
    "Supplement": "SUPPLEMENT",
}
# One row can cover several species, or none that the app knows.
SPECIES = {
    "Cattle": ["CATTLE"],
    "Goat": ["GOAT"],
    "Sheep": ["SHEEP"],
    "Sheep, goats, calves": ["SHEEP", "GOAT", "CATTLE"],
    "Not stated": [],
}

app = create_app()

with app.app_context():
    farm_id = User.query.filter_by(email=EMAIL).first().farmer.farmer_id
    workbook = load_workbook(WORKBOOK, read_only=True)

    sessions = 0
    for row in workbook["Group treatments"].iter_rows(min_row=2, values_only=True):
        when, species, activity, product, amount, animals, notes = row[:7]
        if species is None:
            continue
        details = "; ".join(x for x in (amount, animals, notes) if x)
        for code in SPECIES[species]:
            db.session.add(HerdActivity(farmer_id=farm_id, species=code, date=when.date(),
                                        activity=ACTIVITY[activity], product=product, notes=details))
            sessions += 1

    animals = {a.tag_number: a for a in Livestock.query.filter_by(farmer_id=farm_id)}
    weighed = 0
    for row in workbook["Weights"].iter_rows(min_row=2, values_only=True):
        when, tag, weight = row[0], row[1], row[3]
        if tag is None:
            continue
        db.session.add(WeightRecord(animal_id=animals[tag].animal_id, date=when.date(), weight=weight))
        weighed += 1

    db.session.commit()
    print("group sessions", sessions, "weights", weighed)