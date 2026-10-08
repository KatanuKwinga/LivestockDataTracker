"""One row per purchase or sale of an animal."""
from app.extensions import db

TRANSACTION_TYPES = ("BUY", "SELL")


class CommercialInfo(db.Model):
    __tablename__ = "commercial_info"
    __table_args__ = (db.CheckConstraint("amount >= 0", name="ck_amount_not_negative"),)

    transaction_id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), nullable=False, index=True)
    transaction_type = db.Column(db.Enum(*TRANSACTION_TYPES, name="transaction_type_enum"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)      # in KES
    other_party = db.Column(db.String(100))           # buyer or seller
    location = db.Column(db.String(100))

    animal = db.relationship("Livestock", back_populates="commercial_records")