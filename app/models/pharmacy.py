"""The farm pharmacy"""
from datetime import date, datetime, timedelta

from app.extensions import db

KINDS = {
    "MEDICINE": "Medicine", "VACCINE": "Vaccine", "DEWORMER": "Dewormer", "ACARICIDE": "Tick spray / dip",
    "SUPPLEMENT": "Salt / minerals", "FEED": "Feed", "OTHER": "Other",
}
UNITS = ("ml", "L", "tablets", "doses", "g", "kg", "bags", "bottles", "sachets")

# OPENING: what was on the shelf when the medicine was added. 
# CORRECTED: the farmer setting the balance to what is really on the shelf (expired, lost, lent out, miscounted).
# UNDONE: the farmer cancelling a worker's line that was wrong.
LINE_KINDS = ("OPENING", "USED", "RECEIVED", "CORRECTED", "UNDONE")


def in_list(column, values):
    """SQL for a check constraint: column IN ('A', 'B', ...)."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PharmacyItem(db.Model):
    """One medicine (or vaccine, spray, supplement, feed) the farm keeps.
    Quantity is the balance. It only changes through a StockMovement."""
    __tablename__ = "pharmacy_items"
    __table_args__ = (
        db.UniqueConstraint("farmer_id", "name", name="uq_pharmacy_item_name"),
        db.CheckConstraint("quantity >= 0", name="ck_pharmacy_quantity_not_negative"),
        db.CheckConstraint("reorder_level >= 0", name="ck_pharmacy_reorder_not_negative"),
        # Plain strings with checks, like herd_activities.species, so the
        # migration doesn't need new PostgreSQL enum types.
        db.CheckConstraint(in_list("kind", KINDS), name="ck_pharmacy_kind"),
        db.CheckConstraint(in_list("unit", UNITS), name="ck_pharmacy_unit"),
    )

    item_id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    disease = db.Column(db.String(100), nullable=False)          # what it treats, e.g. "East Coast Fever"
    kind = db.Column(db.String(20), nullable=False)
    unit = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0)
    reorder_level = db.Column(db.Float, nullable=False, default=0)
    notes = db.Column(db.Text)

    added_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    checked = db.Column(db.Boolean, nullable=False, default=True)    # False: a worker added it, the farmer hasn't looked

    # A worker's "please reorder": who asked and when. Cleared by the next delivery.
    reorder_asked_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    reorder_asked_at = db.Column(db.DateTime)

    movements = db.relationship("StockMovement", back_populates="item", cascade="all, delete-orphan",
                                order_by="StockMovement.movement_id")
    adder = db.relationship("User", foreign_keys=[added_by])
    reorder_asker = db.relationship("User", foreign_keys=[reorder_asked_by])

    @property
    def status(self):
        """"OUT", "LOW" or "OK". Low means at or below the reorder level."""
        if self.quantity <= 0:
            return "OUT"
        if self.quantity <= self.reorder_level:
            return "LOW"
        return "OK"

    @property
    def history(self):
        """Every line, newest first, in the order they were written (as in
        the book), so the Balance column always reads correctly even when a
        use is recorded a day late."""
        return list(reversed(self.movements))

    def used_in_last(self, days):
        """How much was used in the last `days` days (undone uses don't count)."""
        since = date.today() - timedelta(days=days)
        return sum(m.amount for m in self.movements if m.kind == "USED" and not m.undone and m.date > since)


class StockMovement(db.Model):
    """One line of the ledger.

    amount is what the person typed (always positive); change is what it
    did to the balance (+ or -); balance_after is the Balance column."""
    __tablename__ = "stock_movements"
    __table_args__ = (
        db.CheckConstraint(in_list("kind", LINE_KINDS), name="ck_stock_movement_kind"),
        db.CheckConstraint("amount >= 0", name="ck_stock_movement_amount_not_negative"),
    )

    movement_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("pharmacy_items.item_id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.String(200))                       # the reason, as in the book
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), index=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id"))                 # the "By" column
    checked = db.Column(db.Boolean, nullable=False, default=True)
    undone = db.Column(db.Boolean, nullable=False, default=False)  # the farmer cancelled this line

    # Deliveries only.
    cost = db.Column(db.Numeric(10, 2))                       # total paid, in KES
    supplier = db.Column(db.String(100))
    expiry_date = db.Column(db.Date)

    # Lines that a health record or a group treatment creates point back to
    # it (used in a later batch), so nobody records the same use twice.
    health_record_id = db.Column(db.Integer, db.ForeignKey("health_records.h_record_id"), index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("herd_activities.activity_id"), index=True)

    item = db.relationship("PharmacyItem", back_populates="movements")
    user = db.relationship("User", foreign_keys=[recorded_by])
    animal = db.relationship("Livestock")
    health_record = db.relationship("HealthRecord")
    activity = db.relationship("HerdActivity")