"""The forms for each kind of record about one animal"""
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.farm import farm_animals, get_farm_animal_or_404, suggest_tag_number
from app.forms import BreedingForm, DeathForm, HealthForm, ProductionForm, SaleForm, WeightForm
from app.models import (BreedingRecord, CommercialInfo, HealthRecord, Farmer, Livestock, MortalityRecord,
                        ProductionData, WeightRecord)
from app.routes.records import CATEGORIES, SLUG_FOR, records_bp, species_or_404
from app.stock import add_line
from ml.reference import CONDITIONS, GESTATION_DAYS

# What happened to the animal, in words, for messages and the saved page.
STATUS_WORDS = {"SOLD": "was sold", "DIED": "has died"}

# Causes offered under the Cause of death box, on top of the species' diseases.
OTHER_CAUSES = ["Unknown", "Old age", "Predator", "Accident", "Poisoning", "Difficult birth"]

# Days from mating to birth, used to fill in the expected date. Eggs take
# 21 days to hatch, so chickens use that.
BIRTH_AFTER_DAYS = {**GESTATION_DAYS, "CHICKEN": 21}

# What each species' females produce, and the most that is believable in a
# day; more than that is treated as a typing mistake.
PRODUCTS = {
    "CATTLE": {"item": "Milk", "metric": "L", "label": "Milk in litres", "max": 60},
    "GOAT": {"item": "Milk", "metric": "L", "label": "Milk in litres", "max": 10},
    "SHEEP": {"item": "Milk", "metric": "L", "label": "Milk in litres", "max": 6},
    "CHICKEN": {"item": "Eggs", "metric": "eggs", "label": "Eggs laid", "max": 2},
}

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
        medicine = form.chosen_medicine
        if medicine is not None:
            # Take it off the pharmacy stock in the same step, so nobody has
            # to record the same treatment twice. The ledger line points to
            # this health record; a worker's goes on the farmer's check list.
            if kind != "VACCINATION" and not record.treatment:
                record.treatment = medicine.name
            if not record.dosage:
                record.dosage = f"{form.medicine_amount.data:g} {medicine.unit}"
            add_line(medicine, "USED", form.medicine_amount.data, form.date.data, current_user.user_id,
                     checked=isinstance(current_user, Farmer), animal_id=animal.animal_id,
                     remarks=record.disease or record.treatment or kind.title(), health_record=record)
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

def female_for_record(species_slug, animal_id):
    """animal_for_record(), plus: the animal must be female."""
    species, animal, leave = animal_for_record(species_slug, animal_id)
    if leave is None and animal.gender != "FEMALE":
        abort(404)
    return species, animal, leave


def newborn_breed(dam, sire):
    """The dam's breed, or "Cross" when the father is a different breed."""
    if sire is not None and sire.breed and dam.breed and sire.breed != dam.breed:
        return "Cross"
    return dam.breed or (sire.breed if sire else None)


def register_newborns(dam, record, sire, females, males):
    """Register each live newborn as a new animal, linked to its birth
    (b_record_id), so its page shows its mother and father. Tags are the
    next free numbers; they can be changed with Edit details."""
    for gender, count in (("FEMALE", females), ("MALE", males)):
        for _ in range(count):
            db.session.add(Livestock(
                farmer_id=dam.farmer_id, species=dam.species, gender=gender,
                tag_number=suggest_tag_number(dam.farmer_id, dam.species),
                breed=newborn_breed(dam, sire), date_of_birth=record.actual_delivery_date,
                b_record_id=record.b_record_id, description=f"Born to {dam.tag_number}"))
            db.session.flush()        # so the next suggest_tag_number() sees this tag


@records_bp.route("/add/<species_slug>/breeding/<int:animal_id>", methods=["GET", "POST"])
@login_required
def breeding_form(species_slug, animal_id):
    species, dam, leave = female_for_record(species_slug, animal_id)
    if leave:
        return leave

    # Her open pregnancy, if one was recorded: a birth or loss closes it.
    open_record = (BreedingRecord.query.filter_by(animal_id=dam.animal_id, status="EXPECTANT")
                   .order_by(BreedingRecord.b_record_id.desc()).first())
    males = (farm_animals().filter(Livestock.species == dam.species, Livestock.gender == "MALE")
             .order_by(Livestock.tag_number).all())
    form = BreedingForm(dam, males, open_record)
    if request.method == "GET" and open_record is not None:
        form.event.data = "BIRTH"                       # the likely next step
        form.sire.data = str(open_record.sire_id or "")

    if form.validate_on_submit():
        event = form.event.data
        sire_id = int(form.sire.data) if form.sire.data else None
        if event == "MATED":
            expected = form.expected_date.data
            if expected is None and form.mated_on.data:
                expected = form.mated_on.data + timedelta(days=BIRTH_AFTER_DAYS[dam.species])
            db.session.add(BreedingRecord(animal_id=dam.animal_id, sire_id=sire_id, status="EXPECTANT",
                                          expected_delivery_date=expected, num_stillborn=0))
        else:
            record = open_record
            if record is None:                           # the pregnancy wasn't recorded first
                record = BreedingRecord(animal_id=dam.animal_id)
                db.session.add(record)
            record.sire_id = sire_id or record.sire_id
            record.status = "SUCCESSFUL BIRTH" if event == "BIRTH" else "NO BIRTH"
            record.actual_delivery_date = form.birth_date.data
            record.num_stillborn = form.stillborn.data
            if event == "BIRTH":
                db.session.flush()                       # gives a new record its id for b_record_id
                sire = db.session.get(Livestock, record.sire_id) if record.sire_id else None
                register_newborns(dam, record, sire, form.females_born.data, form.males_born.data)
        try:
            db.session.commit()
        except IntegrityError:
            # Someone registered an animal with one of the new tags at the
            # same moment; nothing was saved, so it is safe to try again.
            db.session.rollback()
            flash("Another animal took one of the new tag numbers just now. Please save again.", "warning")
            return redirect(request.url)
        return redirect(url_for("records.record_saved", animal_id=dam.animal_id, category_key="breeding"))

    return render_template("records/breeding_form.html", form=form, animal=dam, species=species,
                           species_slug=species_slug, open_record=open_record,
                           gestation=BIRTH_AFTER_DAYS[dam.species], today=date.today().isoformat())


@records_bp.route("/add/<species_slug>/production/<int:animal_id>", methods=["GET", "POST"])
@login_required
def production_form(species_slug, animal_id):
    species, animal, leave = female_for_record(species_slug, animal_id)
    if leave:
        return leave

    product = PRODUCTS[animal.species]
    form = ProductionForm(animal, product)
    form.amount.label.text = product["label"]
    if form.validate_on_submit():
        db.session.add(ProductionData(animal_id=animal.animal_id, date=form.date.data, item=product["item"],
                                      yield_amount=form.amount.data, metric=product["metric"]))
        db.session.commit()
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="production"))

    last = animal.production_records[-1] if animal.production_records else None
    return render_template("records/production_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, product=product, last=last, today=date.today().isoformat())


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
    "breeding": (BreedingRecord, BreedingRecord.b_record_id),
    "production": (ProductionData, ProductionData.product_id),
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