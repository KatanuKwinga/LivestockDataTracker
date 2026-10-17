from datetime import date
from app.extensions import db

SPECIES = ("CATTLE", "CHICKEN", "GOAT", "SHEEP")
GENDERS = ("MALE", "FEMALE")

TAG_PREFIXES = {"CATTLE": "C", "CHICKEN": "CH", "GOAT": "G", "SHEEP": "S"}

class Livestock(db.Model):
    __tablename__ = "livestock"
    __table_args__ = (
        db.UniqueConstraint("farmer_id", "tag_number", name="uq_livestock_farm_tag"),
    )
    animal_id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False, index=True)
    tag_number = db.Column(db.String(20), nullable=False)
    species = db.Column(db.Enum(*SPECIES, name="species_enum"), nullable=False)
    gender = db.Column(db.Enum(*GENDERS, name="gender_enum"), nullable=False)
    breed = db.Column(db.String(50))
    date_of_birth = db.Column(db.Date)
    description = db.Column(db.Text)
    b_record_id = db.Column(
        db.Integer,
        db.ForeignKey("breeding_record.b_record_id", use_alter=True, name="fk_livestock_birth_event"),
    )
    farmer = db.relationship("Farmer", back_populates="livestock")
    weight_records = db.relationship("WeightRecord", back_populates="animal", cascade="all, delete-orphan", order_by="WeightRecord.date")
    health_records = db.relationship("HealthRecord", back_populates="animal", cascade="all, delete-orphan", order_by="HealthRecord.date")
    production_records = db.relationship("ProductionData", back_populates="animal", cascade="all, delete-orphan", order_by="ProductionData.date")
    commercial_records = db.relationship("CommercialInfo", back_populates="animal", cascade="all, delete-orphan", order_by="CommercialInfo.date")
    mortality_record = db.relationship("MortalityRecord", back_populates="animal", uselist=False, cascade="all, delete-orphan")
    birth_event = db.relationship("BreedingRecord", foreign_keys=[b_record_id], back_populates="offspring")
    dam_events = db.relationship("BreedingRecord", foreign_keys="BreedingRecord.animal_id", back_populates="dam")
    sire_events = db.relationship("BreedingRecord", foreign_keys="BreedingRecord.sire_id", back_populates="sire")

    @property
    def age(self):
        if self.date_of_birth is None:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    @property
    def age_label(self):
        """Age in words for the pages: "12 days", "5 months" or "3 years". Young animals are counted in months"""
        if self.date_of_birth is None or self.date_of_birth > date.today():
            return None
        today, born = date.today(), self.date_of_birth
        months = (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)
        if months < 2:
            days = (today - born).days
            return f"{days} day{'' if days == 1 else 's'}"
        if months < 24:
            return f"{months} months"
        return f"{self.age} years"
