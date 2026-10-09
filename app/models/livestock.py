"""One row per animal on a farm."""
from datetime import date

from app.extensions import db

# The allowed values, kept in one place so the model, the forms (Week 3) and
# the ML code all use exactly the same spelling.
SPECIES = ("CATTLE", "CHICKEN", "GOAT", "SHEEP")
GENDERS = ("MALE", "FEMALE")

# The start of each species' suggested tag number: C001, CH001, G001, S001.
TAG_PREFIXES = {"CATTLE": "C", "CHICKEN": "CH", "GOAT": "G", "SHEEP": "S"}


class Livestock(db.Model):
    __tablename__ = "livestock"

    # A tag number only has to be unique WITHIN a farm: two farms may both
    # have a "G001". A unique constraint on the PAIR (farmer_id, tag_number)
    # says exactly that.
    __table_args__ = (
        db.UniqueConstraint("farmer_id", "tag_number", name="uq_livestock_farm_tag"),
    )

    animal_id = db.Column(db.Integer, primary_key=True)
    # index=True: almost every page asks "which animals belong to this farm?",
    # and an index lets the database answer without reading every row.
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False, index=True)
    # db.Enum only accepts the listed values; the database rejects anything
    # else (e.g. "HORSE"). PostgreSQL needs each Enum to have a name.
    
    # The farm's own ID for the animal, e.g. an ear-tag number like "G004".
    # The form suggests the next free one (app/farm.py), and the farmer can change it.
    tag_number = db.Column(db.String(20), nullable=False)
    species = db.Column(db.Enum(*SPECIES, name="species_enum"), nullable=False)
    gender = db.Column(db.Enum(*GENDERS, name="gender_enum"), nullable=False)
    breed = db.Column(db.String(50))
    date_of_birth = db.Column(db.Date)
    description = db.Column(db.Text)
    # The birth this animal came from, if it was born on the farm (empty for
    # animals that were bought in). This is the circular link with
    # breeding_record: use_alter=True tells SQLAlchemy to add this foreign key
    # after both tables exist, because each table points at the other.
    b_record_id = db.Column(
        db.Integer,
        db.ForeignKey("breeding_record.b_record_id", use_alter=True, name="fk_livestock_birth_event"),
    )

    farmer = db.relationship("Farmer", back_populates="livestock")
    # cascade="all, delete-orphan": deleting an animal also deletes its
    # records, so nothing is left pointing at an animal that's gone.
    # order_by: the records always come back oldest first.
    weight_records = db.relationship(
        "WeightRecord", back_populates="animal",
        cascade="all, delete-orphan", order_by="WeightRecord.date",
    )
    health_records = db.relationship(
        "HealthRecord", back_populates="animal",
        cascade="all, delete-orphan", order_by="HealthRecord.date",
    )
    production_records = db.relationship(
        "ProductionData", back_populates="animal",
        cascade="all, delete-orphan", order_by="ProductionData.date",
    )
    commercial_records = db.relationship(
        "CommercialInfo", back_populates="animal",
        cascade="all, delete-orphan", order_by="CommercialInfo.date",
    )
    # uselist=False: an animal has at most one death record, so this gives a
    # single object (or None), not a list.
    mortality_record = db.relationship(
        "MortalityRecord", back_populates="animal",
        uselist=False, cascade="all, delete-orphan",
    )

    # Breeding links. Again, several columns point between the same two
    # tables, so each relationship names the column it follows.
    birth_event = db.relationship("BreedingRecord", foreign_keys=[b_record_id], back_populates="offspring")
    dam_events = db.relationship("BreedingRecord", foreign_keys="BreedingRecord.animal_id", back_populates="dam")
    sire_events = db.relationship("BreedingRecord", foreign_keys="BreedingRecord.sire_id", back_populates="sire")

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