"""One row per weigh-in. Regular weights are the main input to the ML model:
an animal that stops gaining, or starts losing, is often about to fall sick."""
from app.extensions import db


class WeightRecord(db.Model):
    __tablename__ = "weight_records"
    # A database-level rule: a weight of 0 or less is impossible, so the
    # database refuses it even if a bug lets it past the form.
    __table_args__ = (db.CheckConstraint("weight > 0", name="ck_weight_positive"),)

    w_record_id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    weight = db.Column(db.Float, nullable=False)  # kilograms

    animal = db.relationship("Livestock", back_populates="weight_records")