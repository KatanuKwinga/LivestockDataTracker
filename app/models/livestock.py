"""One row per animal on a farm."""
from datetime import date

from app.extensions import db

# The allowed values, kept in one place so the model, the forms (Week 3) and
# the ML code all use exactly the same spelling.
SPECIES = ("CATTLE", "CHICKEN", "GOAT", "SHEEP")
GENDERS = ("MALE", "FEMALE")


class Livestock(db.Model):
    __tablename__ = "livestock"

    animal_id = db.Column(db.Integer, primary_key=True)
    # index=True: almost every page asks "which animals belong to this farm?",
    # and an index lets the database answer without reading every row.
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False, index=True)
    # db.Enum only accepts the listed values; the database rejects anything
    # else (e.g. "HORSE"). PostgreSQL needs each Enum to have a name.
    species = db.Column(db.Enum(*SPECIES, name="species_enum"), nullable=False)
    gender = db.Column(db.Enum(*GENDERS, name="gender_enum"), nullable=False)
    breed = db.Column(db.String(50))
    date_of_birth = db.Column(db.Date)
    description = db.Column(db.Text)

    farmer = db.relationship("Farmer", back_populates="livestock")
    # cascade="all, delete-orphan": deleting an animal also deletes its
    # records, so no weigh-ins are left pointing at an animal that's gone.
    # order_by: animal.weight_records always comes back oldest first.
    weight_records = db.relationship(
        "WeightRecord", back_populates="animal",
        cascade="all, delete-orphan", order_by="WeightRecord.date",
    )
    health_records = db.relationship(
        "HealthRecord", back_populates="animal",
        cascade="all, delete-orphan", order_by="HealthRecord.date",
    )

    @property
    def age(self):
        """Age in whole years, worked out from date_of_birth every time it's
        read. Not stored as a column: a stored age would be wrong a year later."""
        if self.date_of_birth is None:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        # Not had this year's birthday yet? Then one year less.
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years