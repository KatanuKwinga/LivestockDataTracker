"""The forms for each kind of record about one animal"""
from datetime import date

from flask import abort, flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.farm import get_farm_animal_or_404
from app.forms import DeathForm, HealthForm, SaleForm, WeightForm
from app.models import CommercialInfo, HealthRecord, MortalityRecord, WeightRecord
from app.routes.records import CATEGORIES, SLUG_FOR, records_bp, species_or_404
from ml.reference import CONDITIONS

# What happened to the animal, in words, for messages and the saved page.
STATUS_WORDS = {"SOLD": "was sold", "DIED": "has died"}

# Causes offered under the Cause of death box, on top of the species' diseases.
OTHER_CAUSES = ["Unknown", "Old age", "Predator", "Accident", "Poisoning", "Difficult birth"]

def animal_for_record(species_slug, animal_id):
    """The animal a new record is about, after three checks:
    it is on this farm (else 404), it is the species in the URL (else 404),
    and it is still on the farm. """
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


@records_bp.route("/add/<species_slug>/commercial/<int:animal_id>", methods=["GET", "POST"])
@login_required
def commercial_form(species_slug, animal_id):
    species, animal, leave = animal_for_record(species_slug, animal_id)
    if leave:
        return leave

    form = SaleForm(animal)
    if form.validate_on_submit():
        db.session.add(CommercialInfo(animal_id=animal.animal_id, transaction_type=form.transaction_type.data,
                                      date=form.date.data, amount=form.amount.data,
                                      other_party=form.other_party.data or None, location=form.location.data or None))
        db.session.commit()
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="commercial"))

    return render_template("records/commercial_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, today=date.today().isoformat())


def whole_years(born, day):
    """Whole years between two dates, the same way Livestock.age counts them."""
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


@records_bp.route("/add/<species_slug>/mortality/<int:animal_id>", methods=["GET", "POST"])
@login_required
def mortality_form(species_slug, animal_id):
    species, animal, leave = animal_for_record(species_slug, animal_id)
    if leave:
        return leave

    form = DeathForm(animal)
    if form.validate_on_submit():
        died = form.date_of_death.data
        db.session.add(MortalityRecord(
            animal_id=animal.animal_id, date_of_death=died, cause_of_death=form.cause_of_death.data,
            age_at_death=whole_years(animal.date_of_birth, died) if animal.date_of_birth else None,
            description=form.description.data or None))
        try:
            db.session.commit()
        except IntegrityError:
            # An animal has one death record (animal_id is UNIQUE). If two
            # people record the same death at once, the second is refused here.
            db.session.rollback()
            flash(f"{animal.tag_number}'s death has already been recorded.", "warning")
            return redirect(url_for("herd.animal_detail", animal_id=animal.animal_id))
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="mortality"))

    causes = sorted({condition.name for condition in CONDITIONS[animal.species]}) + OTHER_CAUSES
    return render_template("records/mortality_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, causes=causes, today=date.today().isoformat())


# For the saved page: each category's table, and the id column whose
# highest value is the newest row.
NEWEST = {
    "health": (HealthRecord, HealthRecord.h_record_id),
    "weight": (WeightRecord, WeightRecord.w_record_id),
    "commercial": (CommercialInfo, CommercialInfo.transaction_id),
    "mortality": (MortalityRecord, MortalityRecord.m_record_id),
}


@records_bp.route("/saved/<int:animal_id>/<category_key>")
@login_required
def record_saved(animal_id, category_key):
    """The confirmation after saving a record, showing the newest record of
    that kind so the worker can check it. Post/Redirect/Get, as before."""
    animal = get_farm_animal_or_404(animal_id)
    if category_key not in NEWEST:
        abort(404)
    model, id_column = NEWEST[category_key]
    record = model.query.filter_by(animal_id=animal_id).order_by(id_column.desc()).first()
    if record is None:
        abort(404)
    category = next(c for c in CATEGORIES if c["key"] == category_key)
    return render_template("records/record_saved.html", animal=animal, record=record, category=category,
                           species_slug=SLUG_FOR[animal.species])