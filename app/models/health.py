"""One row per health event: an illness, a vaccination, a treatment or a
routine check-up, and the medicines given at it (several per event)."""
from app.extensions import db
from app.models.pharmacy import UNITS, in_list

# What kind of event this row records. Stored explicitly, rather than guessed
# from which other columns are filled in, so the ML code can find "illnesses"
# and "vaccinations" reliably.
HEALTH_RECORD_TYPES = ("ILLNESS", "VACCINATION", "TREATMENT", "CHECKUP")


class HealthRecord(db.Model):
    __tablename__ = "health_records"
    #Constraint on temperature readings
    __table_args__ = (
        db.CheckConstraint(
            "temperature IS NULL OR (temperature >= 30 AND temperature <= 46)",
            name="ck_temperature_range",
        ),
    )
    h_record_id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    record_type = db.Column(
        db.Enum(*HEALTH_RECORD_TYPES, name="health_record_type_enum"), nullable=False
    )
    disease = db.Column(db.String(100))
    temperature = db.Column(db.Float)
    description = db.Column(db.Text)
    treatment = db.Column(db.String(100))
    dosage = db.Column(db.String(50))
    animal = db.relationship("Livestock", back_populates="health_records")
    medicines = db.relationship("HealthMedicine", back_populates="health_record",
                                cascade="all, delete-orphan", order_by="HealthMedicine.medicine_id")

    @property
    def medicines_text(self):
        """The medicines in words, e.g. "Tylosin 20% 8 ml, Multivitamin 5 ml".
        A vaccination shows its vaccine (kept in treatment). Records saved
        before medicines had their own table, and CSV imports, only have the
        treatment and dosage boxes, so those are used then."""
        if self.medicines and self.record_type != "VACCINATION":
            return ", ".join(f"{m.name} {m.amount:g} {m.unit}" for m in self.medicines)
        if self.treatment and self.dosage:
            return f"{self.treatment} ({self.dosage})"
        return self.treatment or ""


class HealthMedicine(db.Model):
    """One medicine given at a health event: what, how much, and in what
    unit. A health record can have several (an antibiotic and a
    painkiller, say), so they are rows of their own table rather than more
    columns on health_records.

    item_id links to the pharmacy when the medicine came from the farm's
    stock (its use is then a ledger line too). It is empty for a medicine
    bought or brought in for this animal only."""
    __tablename__ = "health_medicines"
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_health_medicine_amount_positive"),
        db.CheckConstraint(in_list("unit", UNITS), name="ck_health_medicine_unit"),
    )

    medicine_id = db.Column(db.Integer, primary_key=True)
    h_record_id = db.Column(db.Integer, db.ForeignKey("health_records.h_record_id", ondelete="CASCADE"),
                            nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("pharmacy_items.item_id"), index=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(10), nullable=False)

    health_record = db.relationship("HealthRecord", back_populates="medicines")
    item = db.relationship("PharmacyItem")