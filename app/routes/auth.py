"""Account pages: farmer registration, login (separate doors for farmers and
workers, as in the wireframes) and logout. Workers and password reset are
added in later batches."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from app.extensions import bcrypt, db
from app.forms import FarmerRegistrationForm, LoginForm
from app.models import Farmer, User

# url_prefix: every route here starts with /auth, e.g. /auth/register.
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLES = ("farmer", "worker")


def is_safe_redirect(target):
    """Only allow "next" links that stay on THIS site.

    After logging in we send people back to the page they were trying to
    open, using ?next=... in the address. Without this check, an attacker
    could send someone a real login link ending in ?next=https://fake-site
    and the victim would land on the fake site right after logging in.
    A safe target starts with a single "/" (a page on our own site).
    "//" is excluded because browsers read "//fake-site" as another website.
    """
    return bool(target) and target.startswith("/") and not target.startswith("//") and "\\" not in target


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # Someone already logged in has no reason to see the sign-up page.
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = FarmerRegistrationForm()
    # True only for a POST whose CSRF token and every validator passed.
    if form.validate_on_submit():
        user = User(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data or None,
            # bcrypt turns the password into a one-way hash. Only the hash is
            # stored, so even someone who saw the database couldn't read the
            # password. .decode() turns bcrypt's bytes into text.
            password_hash=bcrypt.generate_password_hash(form.password.data).decode("utf-8"),
        )
        db.session.add(user)
        try:
            # flush() sends the INSERT now and gives us user.id, without
            # committing yet: the Farmer row needs that id. Both are then
            # committed together, so there's never a user without a role.
            db.session.flush()
            db.session.add(Farmer(user_id=user.id))
            db.session.commit()
        except IntegrityError:
            # Two sign-ups at the same instant can both pass validate_email();
            # the database's unique rule on email rejects the second one.
            db.session.rollback()
            form.email.errors.append("An account with this email already exists.")
            return render_template("auth/register.html", form=form)

        flash("Your farmer account has been created. Please log in.", "success")
        # Post/Redirect/Get: redirect after a successful POST, so pressing
        # Refresh doesn't resubmit the form. Straight to the farmer login.
        return redirect(url_for("auth.login", role="farmer"))

    return render_template("auth/register.html", form=form)


# <role> is part of the address: /auth/login/farmer or /auth/login/worker.
# Flask passes it to the function as the `role` argument.
@auth_bp.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ROLES:
        abort(404)  # e.g. /auth/login/admin: "Not Found"
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        # check_password_hash hashes the typed password the same way and
        # compares the result with the stored hash. The password itself is
        # never stored or decrypted.
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            account = user.farmer if role == "farmer" else user.worker

            if account is None:
                # Right email and password, wrong door. This hint is only
                # reached AFTER the correct password, so it tells a stranger
                # nothing; it just helps a real user who clicked the wrong card.
                other = "worker" if role == "farmer" else "farmer"
                flash(f"This is a {other} account. Please use the {other.capitalize()} login.", "warning")
                return redirect(url_for("auth.login", role=other, next=request.args.get("next")))

            # Flask-Login stores account.get_id() ("farmer:3") in the signed
            # session cookie. From now on, every page knows who this is.
            login_user(account)
            flash(f"Welcome back, {account.name}.", "success")
            next_page = request.args.get("next")
            return redirect(next_page if is_safe_redirect(next_page) else url_for("main.dashboard"))

        # Deliberately the same message for "no such email" and "wrong
        # password", so the form can't be used to find out who has an account.
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form, role=role)


# POST only: a plain link (GET) could be triggered by another website
# (e.g. an <img src=".../logout">) and silently log people out. With POST,
# CSRFProtect also demands the secret token.
@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()  # removes the account from the session cookie
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))