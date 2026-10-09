"""Account pages: farmer registration, login (separate doors for farmers and
workers, as in the wireframes) and logout. Workers and password reset are
added in later batches."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message

from app.accounts import create_account
from app.extensions import bcrypt, db, mail
from app.forms import FarmerRegistrationForm, LoginForm, RequestResetForm, ResetPasswordForm
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
    if form.validate_on_submit():
        # The role row for a self-registering user is always a Farmer.
        # "lambda user: Farmer(...)" is a tiny unnamed function: given the
        # new user, it returns their Farmer row.
        user = create_account(form, lambda user: Farmer(user_id=user.id))
        if user is None:
            form.email.errors.append("An account with this email already exists.")
        else:
            flash("Your farmer account has been created. Please log in.", "success")
            # Post/Redirect/Get: Refresh won't resubmit the form.
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



def send_reset_email(user):
    """Email the user a link containing their reset token."""
    token = user.get_reset_token()
    # _external=True makes a full "http://..." address, which an email needs
    # (the reader isn't on our site when they click it).
    reset_url = url_for("auth.reset_password", token=token, _external=True)

    # No Gmail settings yet? While developing (debug mode), print the link in
    # the terminal so reset can still be tested. Never in production.
    if not current_app.config.get("MAIL_USERNAME"):
        if current_app.debug:
            current_app.logger.warning("MAIL_USERNAME not set; reset link for %s: %s", user.email, reset_url)
        return

    message = Message(
        subject="Livestock Tracker: reset your password",
        recipients=[user.email],
        body=(
            f"Hi {user.name},\n\n"
            "Someone (hopefully you) asked to reset the password for your Livestock Tracker account.\n"
            "Open this link to choose a new password:\n\n"
            f"{reset_url}\n\n"
            "The link works once and expires in 30 minutes.\n"
            "If you didn't ask for this, ignore this email: your password stays the same.\n"
        ),
    )
    mail.send(message)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_request():
    """Step 1: ask for the email address."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            try:
                send_reset_email(user)
            except Exception:
                # Gmail down, wrong app password, no internet...: log the
                # details for us (in the terminal), never show them to users.
                current_app.logger.exception("Could not send the password reset email")

        # The SAME message whether or not the account exists, so this page
        # can't be used to check which emails are registered.
        flash("If an account exists for that email, a reset link is on its way. Check your inbox (and spam folder).", "info")
        return redirect(url_for("main.index"))

    return render_template("auth/reset_request.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Step 2: the link from the email lands here."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    user = User.verify_reset_token(token)
    if user is None:
        # One message for tampered, expired and already-used links: the user
        # only needs to know to ask for a new one.
        flash("That reset link is invalid, has expired or has already been used. Please request a new one.", "warning")
        return redirect(url_for("auth.reset_request"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        db.session.commit()  # the hash changes, so this link (and any older one) now stops working
        # Send them to the right door for their account.
        role = "farmer" if user.farmer else "worker"
        flash("Your password has been changed. Please log in with your new password.", "success")
        return redirect(url_for("auth.login", role=role))

    return render_template("auth/reset_password.html", form=form)