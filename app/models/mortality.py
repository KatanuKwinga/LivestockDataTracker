"""One row per animal that has died."""
from app.extensions import db


class MortalityRecord(db.Model):
    __tablename__ = "mortality_records"

    m_record_id = db.Column(db.Integer, primary_key=True)
    # unique=True: an animal can only die once, so at most one row per animal.
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), unique=True, nullable=False)
    date_of_death = db.Column(db.Date, nullable=False)
    age_at_death = db.Column(db.Integer)
    cause_of_death = db.Column(db.String(100))
    description = db.Column(db.Text)

    animal = db.relationship("Livestock", back_populates="mortality_record")