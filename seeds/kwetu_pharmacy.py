"""Load the pharmacy."""
from datetime import date

from app import create_app
from app.extensions import db
from app.models import PharmacyItem, User
from app.stock import add_line

EMAIL = "katanukavilakwinga@gmail.com"
MARK = "[kwetu]"

# name, what it treats, kind, unit, last balance, date of that balance, reorder at
# Balances are from the Kwetu_Livestock_Medicine_Log. Reorder levels are our estimates.
MEDICINES = [
    ("Bupalex", "East Coast Fever", "MEDICINE", "ml", 0, date(2026, 8, 13), 60),
    ("Bupacin", "East Coast Fever", "MEDICINE", "ml", 635, date(2026, 8, 27), 60),
    ("Oxytetracycline 10% LA", "Infections, fever, pneumonia", "MEDICINE", "ml", 844, date(2026, 6, 4), 200),
    ("Ecocan 20% LA", "Infections (long-acting)", "MEDICINE", "ml", 19, date(2026, 6, 19), 30),
    ("Alamycin 30%", "Infections (long-acting)", "MEDICINE", "ml", 26, date(2026, 8, 13), 30),
    ("Penstrep", "Mastitis, wounds, pneumonia", "MEDICINE", "ml", 55, date(2026, 8, 30), 50),
    ("Dexamethasone (Dexa)", "Inflammation, fever", "MEDICINE", "ml", 119, date(2026, 8, 27), 50),
    ("Histacine", "Allergies, lung problems", "MEDICINE", "ml", 5, date(2026, 8, 1), 15),
    ("S-Dime tablets", "Diarrhoea, fever in calves", "MEDICINE", "tablets", 3, date(2026, 9, 2), 5),
    ("S-Dime liquid", "Diarrhoea (scouring)", "MEDICINE", "ml", 343, date(2026, 7, 2), 50),
    ("Methoxicash", "Infections", "MEDICINE", "ml", 0, date(2026, 5, 19), 20),
    ("Ivermectin injection", "Internal and external parasites", "DEWORMER", "ml", 0, date(2026, 8, 13), 100),
    ("Nilzan", "Gastrointestinal worms", "DEWORMER", "ml", 1700, date(2026, 8, 13), 300),
    ("Dip Dominex", "Ticks", "ACARICIDE", "ml", 168, date(2026, 8, 18), 600),
    ("Magadi salt", "Washing (Orf), salt", "SUPPLEMENT", "kg", 4, date(2026, 5, 18), 2),
    ("Mack lick salt", "Minerals", "SUPPLEMENT", "kg", 0, date(2026, 8, 13), 10),
    ("Nutri-Vit", "Vitamins", "SUPPLEMENT", "bottles", 0, date(2026, 8, 13), 1),
]

app = create_app()

with app.app_context():
    farmer = User.query.filter_by(email=EMAIL).first().farmer

    # Medicine names are unique on a farm, so skip any the farm already has.
    have = {item.name.lower() for item in PharmacyItem.query.filter_by(farmer_id=farmer.farmer_id)}

    added = skipped = 0
    for name, treats, kind, unit, balance, as_of, reorder in MEDICINES:
        if name.lower() in have:
            skipped += 1
            continue
        item = PharmacyItem(farmer_id=farmer.farmer_id, name=name, disease=treats, kind=kind, unit=unit,
                            quantity=0, reorder_level=reorder, added_by=farmer.user_id,
                            notes=f"{MARK} From the medicine cards.")
        db.session.add(item)
        # The balance goes in as the first line of the medicine's ledger, so
        # its history starts with where the farm's own card left off.
        add_line(item, "OPENING", balance, as_of, farmer.user_id,
                 remarks=f"Balance on the medicine card, {as_of:%d/%m/%Y}")
        added += 1

    db.session.commit()
    print("medicines added", added, "already there", skipped)