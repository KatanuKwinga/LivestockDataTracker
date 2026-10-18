"""The forms for each kind of record about one animal"""
from datetime import date

from flask import abort, flash, redirect, render_template, url_for
from flask_login import login_required

from app.extensions import db
from app.farm import get_farm_animal_or_404
from app.forms import HealthForm, WeightForm
from app.models import HealthRecord, WeightRecord
from app.routes.records import CATEGORIES, SLUG_FOR, records_bp, species_or_404
from ml.reference import CONDITIONS

# What happened to the animal, in words, for messages and the saved page.
STATUS_WORDS = {"SOLD": "was sold", "DIED": "has died"}


def animal_for_record(species_slug, animal_id):
    """The animal a new record is about, after three checks:
    it is on this farm (else 404), it is the species in the URL (else 404),
    and it is still on the farm. Returns (species, animal, redirect): the
    view must return the redirect if there is one."""
    species = species_or_404(species_slug)
    animal = get_farm_animal_or_404(animal_id)
    if animal.species != species["value"]:
        abort(404)
    if animal.status != "ON_FARM":
        flash(f"{animal.tag_number} {STATUS_WORDS[animal.status]}, so new records can't be added.", "warning")
        return species, animal, redirect(url_for("herd.animal_detail", animal_id=animal.animal_id))
    return species, animal, None


@records_bp.route("/add/<species_slug>/health/<int:animal_id>", methods=["GET", "POST"])
@login_required
def health_form(species_slug, animal_id):
    species, animal, leave = animal_for_record(species_slug, animal_id)
    if leave:
        return leave

    form = HealthForm(animal)
    if form.validate_on_submit():
        kind = form.record_type.data
        record = HealthRecord(animal_id=animal.animal_id, date=form.date.data, record_type=kind,
                              temperature=form.temperature.data, dosage=form.dosage.data or None,
                              description=form.description.data or None)
        if kind == "VACCINATION":
            # The model looks vaccines up by their exact name in treatment.
            record.treatment = form.vaccine.data
        else:
            # A check-up isn't about a disease, so a disease typed there is dropped.
            record.disease = form.disease.data if kind in ("ILLNESS", "TREATMENT") else None
            record.treatment = form.treatment.data or None
        db.session.add(record)
        db.session.commit()
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="health"))

    diseases = sorted({condition.name for condition in CONDITIONS[animal.species]})
    return render_template("records/health_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, diseases=diseases, today=date.today().isoformat())


@records_bp.route("/add/<species_slug>/weight/<int:animal_id>", methods=["GET", "POST"])
@login_required
def weight_form(species_slug, animal_id):
    species, animal, leave = animal_for_record(species_slug, animal_id)
    if leave:
        return leave

    form = WeightForm(animal)
    if form.validate_on_submit():
        db.session.add(WeightRecord(animal_id=animal.animal_id, date=form.date.data, weight=form.weight.data))
        db.session.commit()
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="weight"))

    last = animal.weight_records[-1] if animal.weight_records else None
    return render_template("records/weight_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, last=last, today=date.today().isoformat())


@records_bp.route("/saved/<int:animal_id>/<category_key>")
@login_required
def record_saved(animal_id, category_key):
    """The confirmation after saving a record, showing the newest record of
    that kind so the worker can check it. Post/Redirect/Get, as before."""
    animal = get_farm_animal_or_404(animal_id)
    if category_key == "health":
        record = HealthRecord.query.filter_by(animal_id=animal_id).order_by(HealthRecord.h_record_id.desc()).first()
    elif category_key == "weight":
        record = WeightRecord.query.filter_by(animal_id=animal_id).order_by(WeightRecord.w_record_id.desc()).first()
    else:
        abort(404)
    if record is None:
        abort(404)
    category = next(c for c in CATEGORIES if c["key"] == category_key)
    return render_template("records/record_saved.html", animal=animal, record=record, category=category,
                           species_slug=SLUG_FOR[animal.species])