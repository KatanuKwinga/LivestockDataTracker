"""Load the births, so each young animal is linked to its mother."""
from openpyxl import load_workbook

from app import create_app
from app.extensions import db
from app.models import BreedingRecord, Livestock, User

EMAIL = "katanukavilakwinga@gmail.com"
WORKBOOK = "seeds/data/Kwetu_Animals_and_Records.xlsx"

app = create_app()

with app.app_context():
    farm_id = User.query.filter_by(email=EMAIL).first().farmer.farmer_id
    animals = {a.tag_number: a for a in Livestock.query.filter_by(farmer_id=farm_id)}

    sheet = load_workbook(WORKBOOK, read_only=True)["Births"]
    births = young_count = 0
    for row in sheet.iter_rows(min_row=2, values_only=True):
        when, mother_tag, young_tags = row[0], row[2], row[3]
        if when is None:
            continue
        birth = BreedingRecord(dam=animals[mother_tag], status="SUCCESSFUL BIRTH",
                               actual_delivery_date=when.date())
        db.session.add(birth)
        births += 1

        # "S412, S413" -> ["S412", "S413"]: one birth can be twins.
        for tag in young_tags.split(", "):
            animals[tag].birth_event = birth
            animals[tag].description = f"[kwetu] Born to {mother_tag}"
            young_count += 1

    db.session.commit()
    print("births", births, "young linked to their mother", young_count)