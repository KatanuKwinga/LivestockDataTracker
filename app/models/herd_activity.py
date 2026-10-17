from app.extensions import db


class HerdActivity(db.Model):
    """A routine done to a whole group at once, e.g. spraying all the cattle
    for ticks. One row per session instead of one per animal: at twice a
    week, per-animal rows would be ~100 a year for every cow."""
    __tablename__ = "herd_activities"
    __table_args__ = (
        # A plain string with a check, rather than reusing species_enum, so the
        # migration doesn't try to create that PostgreSQL type a second time.
        db.CheckConstraint("species IN ('CATTLE', 'CHICKEN', 'GOAT', 'SHEEP')",
                           name="ck_herd_activity_species"),
    )

    activity_id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False, index=True)
    species = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    activity = db.Column(db.String(30), nullable=False)    # e.g. "TICK_SPRAY"
    product = db.Column(db.String(100))                    # e.g. "Dip Dominex"
    notes = db.Column(db.Text)