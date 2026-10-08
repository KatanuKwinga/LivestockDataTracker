"""One row per mating/pregnancy: who the mother and father are, how it went,
and (through livestock.b_record_id) which animals were born from it."""
from app.extensions import db

BREEDING_STATUSES = ("EXPECTANT", "SUCCESSFUL BIRTH", "NO BIRTH")


class BreedingRecord(db.Model):
    __tablename__ = "breeding_record"
    __table_args__ = (db.CheckConstraint("num_stillborn >= 0", name="ck_stillborn_not_negative"),)

    b_record_id = db.Column(db.Integer, primary_key=True)
    # The mother ("dam"). Required: every pregnancy has a mother on this farm.
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), nullable=False, index=True)
    # The father ("sire"). Optional: he may be unknown, or not on this farm.
    sire_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), index=True)
    status = db.Column(db.Enum(*BREEDING_STATUSES, name="breeding_status_enum"), nullable=False)
    expected_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.Date)
    num_stillborn = db.Column(db.Integer, nullable=False, default=0)

    # Two columns here point at the same table (livestock), so each
    # relationship must say WHICH column it follows: foreign_keys=[...].
    dam = db.relationship("Livestock", foreign_keys=[animal_id], back_populates="dam_events")
    sire = db.relationship("Livestock", foreign_keys=[sire_id], back_populates="sire_events")
    # The animals born from this event: those whose b_record_id points here.
    offspring = db.relationship("Livestock", foreign_keys="Livestock.b_record_id", back_populates="birth_event")

    @property
    def num_born_alive(self):
        """Counted from the registered offspring rather than typed in, so it
        can never disagree with the animals actually on record."""
        return len(self.offspring) 