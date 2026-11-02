"""Load the health records: illnesses, treatments and check-ups."""
from openpyxl import load_workbook

from app import create_app
from app.extensions import db
from app.models import HealthRecord, Livestock, User

EMAIL = "katanukavilakwinga@gmail.com"
WORKBOOK = "seeds/data/Kwetu_Animals_and_Records.xlsx"

app = create_app()

with app.app_context():
    farm_id = User.query.filter_by(email=EMAIL).first().farmer.farmer_id
    animals = {a.tag_number: a for a in Livestock.query.filter_by(farmer_id=farm_id)}

    sheet = load_workbook(WORKBOOK, read_only=True)["Health records"]
    counts = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        when, tag, record_type, problem, temp, medicine, dose, notes = row[0], row[1], row[3], row[4], row[5], row[6], row[7], row[8]
        if tag is None:
            continue
        db.session.add(HealthRecord(
            animal_id=animals[tag].animal_id,
            date=when.date(),
            record_type=record_type,
            disease=problem or None,
            temperature=temp,
            treatment=medicine or None,
            dosage=dose or None,
            description=notes or None,
        ))
        counts[record_type] = counts.get(record_type, 0) + 1

    db.session.commit()
    print(counts)