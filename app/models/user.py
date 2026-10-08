"""Accounts: who can log in, and in which role.

Every person has one row in `users` (their identity: name, email, password).
On top of that they are EITHER a farmer OR a worker, stored in the `farmers`
or `workers` table and linked back to their `users` row. Keeping the shared
details in one table means login, email checks and password reset work the
same way for both roles.
"""
from flask_login import UserMixin

from app.extensions import db, login_manager


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # unique=True makes the DATABASE itself refuse a second account with the
    # same email, even if two sign-ups arrive at the same instant.
    email = db.Column(db.String(150), unique=True, nullable=False)
    # Only the bcrypt hash is stored, never the password itself.
    password_hash = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(20))

    # Shortcuts in Python (not columns): user.farmer / user.worker give the
    # linked role row, or None. uselist=False means "one object, not a list".
    farmer = db.relationship("Farmer", back_populates="user", uselist=False)
    worker = db.relationship("Worker", back_populates="user", uselist=False)


class Farmer(UserMixin, db.Model):
    __tablename__ = "farmers"

    farmer_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    user = db.relationship("User", back_populates="farmer")
    workers = db.relationship("Worker", back_populates="farmer")
    livestock = db.relationship("Livestock", back_populates="farmer")

    def get_id(self):
        # Flask-Login stores this text in the login cookie. The "farmer:"
        # prefix matters because farmer 3 and worker 3 are different people,
        # and load_user() below must know which table to look in.
        return f"farmer:{self.farmer_id}"

    # So the rest of the app can write current_user.name instead of
    # current_user.user.name.
    @property
    def name(self):
        return self.user.name

    @property
    def email(self):
        return self.user.email


class Worker(UserMixin, db.Model):
    __tablename__ = "workers"

    worker_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    # Every worker belongs to exactly one farm, from the moment it exists.
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.farmer_id"), nullable=False)

    user = db.relationship("User", back_populates="worker")
    farmer = db.relationship("Farmer", back_populates="workers")

    def get_id(self):
        return f"worker:{self.worker_id}"

    @property
    def name(self):
        return self.user.name

    @property
    def email(self):
        return self.user.email


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login calls this on every page load with the text get_id()
    returned at login (e.g. "farmer:3"), and expects the account back."""
    try:
        role, raw_id = user_id.split(":")
        raw_id = int(raw_id)
    except (ValueError, AttributeError):
        # A damaged or tampered cookie: treat the visitor as logged out.
        return None

    if role == "farmer":
        return db.session.get(Farmer, raw_id)
    if role == "worker":
        return db.session.get(Worker, raw_id)
    return None