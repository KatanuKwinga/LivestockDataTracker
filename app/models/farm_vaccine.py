from app.extensions import db


class FarmVaccine(db.Model):
    """One vaccine in a farm's vaccination plan (the Vaccination plan page).
    Vaccine names are the keys of ml.reference.VACCINES."""
    __tablename__ = "farm_vaccines"
    __table_args__ = (
        db.UniqueConstraint("farmer_id", "vaccine", name="uq_farm_vaccine"),
    )

    farm_vaccine_id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False, index=True)
    vaccine = db.Column(db.String(50), nullable=False)