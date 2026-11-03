"""One row per animal that left the farm without being sold or dying on it:
given away, slaughtered for home use, lost, stolen or found missing at a
head count. Like a death or a sale, it takes the animal off the herd lists,
but its records are kept."""
from app.extensions import db

# The reasons the form offers, and how each is shown on the pages. Stored
# as a short code (not free text) so the herd can be counted by reason.
REASONS = {
    "GIVEN_AWAY": "Given away",
    "SLAUGHTERED": "Slaughtered for home use",
    "LOST": "Lost or strayed",
    "STOLEN": "Stolen",
    "MISSING": "Missing at a head count",
    "OTHER": "Other",
}


class Departure(db.Model):
    __tablename__ = "departures"

    departure_id = db.Column(db.Integer, primary_key=True)
    # unique=True: an animal can only leave the farm once.
    animal_id = db.Column(db.Integer, db.ForeignKey("livestock.animal_id"), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)

    animal = db.relationship("Livestock", back_populates="departure")

    @property
    def reason_label(self):
        """The reason in words, e.g. "Given away"."""
        return REASONS.get(self.reason, self.reason)