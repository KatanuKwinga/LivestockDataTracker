"""Farmer-only pages for managing the farm's workers."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user

from app.accounts import create_account
from app.decorators import farmer_required
from app.forms import WorkerCreationForm
from app.models import User, Worker

workers_bp = Blueprint("workers", __name__, url_prefix="/workers")


@workers_bp.route("/")
@farmer_required
def list_workers():
    # DATA SCOPING: only workers whose farmer_id is the logged-in farmer's.
    # A farmer can never see another farm's workers, whatever they type in
    # the address bar.
    workers = (
        Worker.query.filter_by(farmer_id=current_user.farmer_id)
        .join(User)               # join to users so we can sort by name
        .order_by(User.name)
        .all()
    )
    return render_template("workers/list.html", workers=workers)


@workers_bp.route("/new", methods=["GET", "POST"])
@farmer_required
def new_worker():
    form = WorkerCreationForm()
    if form.validate_on_submit():
        # The new worker is tied to THIS farmer's farm from the moment it
        # exists. Workers never choose their farm or sign themselves up.
        farmer_id = current_user.farmer_id
        user = create_account(form, lambda user: Worker(user_id=user.id, farmer_id=farmer_id))
        if user is None:
            form.email.errors.append("An account with this email already exists.")
        else:
            flash(f"{user.name} can now log in through the Worker login.", "success")
            return redirect(url_for("workers.list_workers"))

    return render_template("workers/new.html", form=form)