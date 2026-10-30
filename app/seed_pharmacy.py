"""Load the medicines from Kwetu's ledger book into one farmer's pharmacy,
for the demo. A new farmer adds their own medicines instead.

    python -m app.seed_pharmacy --farmer-email demo@x.com            # add them
    python -m app.seed_pharmacy --farmer-email demo@x.com --remove   # take them out again

The balances are chosen so the demo shows every status: most In stock, some
Low, one Out. Each demo medicine's notes start with "[demo]", the way
synthetic animals' descriptions start with "[synthetic]", so --remove
deletes only these and never real entries.
"""
import argparse
from datetime import date

from app import create_app
from app.extensions import db
from app.models import PharmacyItem, User
from app.stock import add_line

DEMO_MARK = "[demo]"

# name, what it treats, type, unit, on the shelf, reorder at
BOOK_MEDICINES = [
    ("Butalex", "East Coast Fever", "MEDICINE", "ml", 150, 60),
    ("Dexamethasone 0.2%", "Inflammation", "MEDICINE", "ml", 80, 30),
    ("Pen & Strep", "Mastitis, wounds, pneumonia", "MEDICINE", "ml", 45, 50),
    ("Tylosin 20%", "Pneumonia", "MEDICINE", "ml", 120, 30),
    ("S-Dime tablets", "Diarrhoea", "MEDICINE", "tablets", 40, 10),
    ("Hist-Vet", "Allergies and eye problems", "MEDICINE", "ml", 50, 15),
    ("Dominex", "External parasites", "ACARICIDE", "ml", 400, 600),
    ("Grenade", "External parasites", "ACARICIDE", "ml", 600, 300),
    ("Almatix", "External parasites", "ACARICIDE", "ml", 0, 200),
    ("Mineral salt", "Mineral deficiency", "SUPPLEMENT", "kg", 25, 10),
]


def add_book_medicines(farmer):
    """Add each book medicine the farm doesn't already have. Returns how many."""
    have = {name.lower() for (name,) in PharmacyItem.query.with_entities(PharmacyItem.name)
            .filter_by(farmer_id=farmer.farmer_id)}
    added = 0
    for name, disease, kind, unit, on_shelf, reorder in BOOK_MEDICINES:
        if name.lower() in have:
            continue
        item = PharmacyItem(farmer_id=farmer.farmer_id, name=name, disease=disease, kind=kind, unit=unit,
                            quantity=0, reorder_level=reorder, added_by=farmer.user_id,
                            notes=f"{DEMO_MARK} From the farm's ledger book.")
        db.session.add(item)
        add_line(item, "OPENING", on_shelf, date.today(), farmer.user_id, remarks="Opening balance")
        added += 1
    db.session.commit()
    return added


def remove_book_medicines(farmer):
    """Delete the demo medicines (and, through the cascade, their history)."""
    items = PharmacyItem.query.filter(PharmacyItem.farmer_id == farmer.farmer_id,
                                      PharmacyItem.notes.startswith(DEMO_MARK)).all()
    for item in items:
        db.session.delete(item)
    db.session.commit()
    return len(items)


def main():
    parser = argparse.ArgumentParser(description="Load the ledger book's medicines for the demo.")
    parser.add_argument("--farmer-email", required=True)
    parser.add_argument("--remove", action="store_true", help="delete the demo medicines instead")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=args.farmer_email.strip().lower()).first()
        if user is None or user.farmer is None:
            raise SystemExit(f"No farmer account with the email {args.farmer_email}.")
        if args.remove:
            print(f"Removed {remove_book_medicines(user.farmer)} demo medicines.")
        else:
            print(f"Added {add_book_medicines(user.farmer)} medicines from the ledger book.")


if __name__ == "__main__":
    main()