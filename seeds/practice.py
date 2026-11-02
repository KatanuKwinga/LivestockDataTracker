"""Practice seed (bit 2): add five goats to one farm."""
from app import create_app
from app.extensions import db
from app.models import Livestock, User

EMAIL = "katanukavilakwinga@gmail.com"

app = create_app()

with app.app_context():
    user = User.query.filter_by(email=EMAIL).first()
    farm_id = user.farmer.farmer_id

    for number in range(1, 6):
        tag = f"G{number:03d}"
        goat = Livestock(farmer_id=farm_id, tag_number=tag, species="GOAT",
                         gender="FEMALE", description="[practice] bit 2")
        db.session.add(goat)
        print("ready to save", tag)

    db.session.commit()
    print("saved all five")