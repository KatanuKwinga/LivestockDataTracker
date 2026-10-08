"""Account pages. This batch: farmer registration. Login, logout, workers and
password reset are added in the next batches."""
from flask import Blueprint, flash, redirect, render_template, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import bcrypt, db
from app.forms import FarmerRegistrationForm
from app.models import Farmer, User

# url_prefix: every route here starts with /auth, e.g. /auth/register.
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    form = FarmerRegistrationForm()

    # True only for a POST whose CSRF token and every validator passed.
    # On a normal visit (GET) it's False, so the empty form is shown.
    if form.validate_on_submit():
        user = User(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data or None,
            # bcrypt turns the password into a one-way hash. Only the hash is
            # stored, so even someone who saw the database couldn't read
            # the password. .decode() turns bcrypt's bytes into text.
            password_hash=bcrypt.generate_password_hash(form.password.data).decode("utf-8"),
        )
        db.session.add(user)
        try:
            # flush() sends the INSERT now and gives us user.id, without
            # committing yet: the Farmer row needs that id. User and Farmer
            # are then committed together, so we never end up with a user
            # who has no role.
            db.session.flush()
            db.session.add(Farmer(user_id=user.id))
            db.session.commit()
        except IntegrityError:
            # validate_email() already checked for duplicates, but two
            # sign-ups at the same instant (e.g. a double-click) can both
            # pass that check. The database's unique rule on email then
            # rejects the second one, and we show a friendly message
            # instead of crashing.
            db.session.rollback()
            form.email.errors.append("An account with this email already exists.")
            return render_template("auth/register.html", form=form)

        flash("Your farmer account has been created.", "success")
        # Post/Redirect/Get: redirect after a successful POST, so pressing
        # Refresh doesn't resubmit the form.
        return redirect(url_for("main.index"))

    return render_template("auth/register.html", form=form)