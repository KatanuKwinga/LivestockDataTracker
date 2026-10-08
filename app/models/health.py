"""One row per health event: an illness, a vaccination, a treatment or a
routine check-up."""
from app.extensions import db

# What kind of event this row records. Stored explicitly, rather than guessed
# from which other columns are filled in, so the ML code can find "illnesses"
# and "vaccinations" reliably.
HEALTH_RECORD_TYPES = ("ILLNESS", "VACCINATION", "TREATMENT", "CHECKUP")


class HealthRecord(db.Model):
    __tablename__ = "health_records"

    h_record_id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    record_type = db.Column(
        db.Enum(*HEALTH_RECORD_TYPES, name="health_record_type_enum"), nullable=False
    )
    disease = db.Column(db.String(100))      
    description = db.Column(db.Text)
    treatment = db.Column(db.String(100))    
    dosage = db.Column(db.String(50))

    animal = db.relationship("Livestock", back_populates="health_records")