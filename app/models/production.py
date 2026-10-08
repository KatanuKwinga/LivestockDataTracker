"""One row per production event: milk, eggs, wool and so on."""
from app.extensions import db


class ProductionData(db.Model):
    __tablename__ = "production_data"
    # "yield" is in double quotes because it is a reserved word in SQL.
    __table_args__ = (db.CheckConstraint('"yield" >= 0', name="ck_yield_not_negative"),)

    product_id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    item = db.Column(db.String(100), nullable=False)     # e.g. "Milk", "Eggs"
    # `yield` is a reserved word in Python, so it can't be an attribute name.
    # The first argument keeps the DATABASE column called "yield" (as in the
    # ERD); in Python we use yield_amount instead.
    yield_amount = db.Column("yield", db.Float, nullable=False)
    metric = db.Column(db.String(10), nullable=False)    # e.g. "L", "kg", "count"

    animal = db.relationship("Livestock", back_populates="production_records")
    