"""Farmer-only pages for managing the farm's workers."""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.accounts import create_account
from app.decorators import farmer_required
from app.extensions import bcrypt, db
from app.forms import ResetPasswordForm, WorkerCreationForm
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
            form.username.errors.append("That username is taken. Try adding a number, e.g. wanjiru2.")
        else:
            flash(f"{user.name} can now log in through the Worker login as \"{user.username}\".", "success")
            return redirect(url_for("workers.list_workers"))

    return render_template("workers/new.html", form=form)

@workers_bp.route("/<int:worker_id>/password", methods=["GET", "POST"])
@farmer_required
def reset_worker_password(worker_id):
    """Workers have no email, so a worker who forgets their password asks
    the farmer, who sets a new one here and tells them in person."""
    # DATA SCOPING: only a worker on THIS farmer's farm; anyone else is "Not Found".
    worker = Worker.query.filter_by(worker_id=worker_id, farmer_id=current_user.farmer_id).first()
    if worker is None:
        abort(404)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        worker.user.password_hash = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        db.session.commit()
        flash(f"{worker.name}'s password has been changed. Give them the new one in person.", "success")
        return redirect(url_for("workers.list_workers"))
    return render_template("workers/password.html", form=form, worker=worker)