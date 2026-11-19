"""The forms for each kind of record about one animal"""
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.farm import current_farm_id, farm_animals, get_farm_animal_or_404, suggest_tag_number
from app.forms import (MAX_MEDICINES, NEW_MEDICINE, BreedingForm, DeathForm, DepartureForm, HealthForm, LinkYoungForm,
                       ProductionForm, SaleForm, WeightForm)
from app.models import (BreedingRecord, CommercialInfo, Departure, HealthMedicine, HealthRecord, Farmer, Livestock,
                        MortalityRecord, PharmacyItem, ProductionData, WeightRecord)
from app.routes.herd import MARKET_WORDS
from app.routes.records import CATEGORIES, SLUG_FOR, records_bp, species_or_404
from app.stock import add_line
from ml.reference import CONDITIONS, GESTATION_DAYS

# What happened to the animal, in words, for messages and the saved page.
STATUS_WORDS = {"SOLD": "was sold", "DIED": "has died", "LEFT": "has left the farm"}
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

def shorten(text, longest):
    """Text cut to fit a column, with "..." if anything was cut."""
    return text if len(text) <= longest else text[:longest - 3] + "..."

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
                              temperature=form.temperature.data, description=form.description.data or None)
        if kind == "VACCINATION":
            # The model looks vaccines up by their exact name in treatment.
            record.treatment = form.vaccine.data
        else:
            # A check-up isn't about a disease, so a disease typed there is dropped.
            record.disease = form.disease.data if kind in ("ILLNESS", "TREATMENT") else None

        # One row per medicine given. The treatment and dosage boxes keep a
        # short summary too, so the CSV export, older pages and the group
        # treatment check still read the record as before.
        for given in form.given:
            record.medicines.append(HealthMedicine(item=given["item"], name=given["name"],
                                                   amount=given["amount"], unit=given["unit"]))
        if form.given:
            if kind != "VACCINATION":
                record.treatment = shorten(", ".join(g["name"] for g in form.given), 100)
            record.dosage = shorten(", ".join(f"{g['amount']:g} {g['unit']}" for g in form.given), 50)

        # Medicines from the pharmacy come off the stock in the same step, so
        # nobody has to record the same treatment twice. Each ledger line
        # points to this health record; a worker's goes on the farmer's check list.
        for given in form.given:
            if given["item"] is not None:
                add_line(given["item"], "USED", given["amount"], form.date.data, current_user.user_id,
                         checked=isinstance(current_user, Farmer), animal_id=animal.animal_id,
                         remarks=record.disease or record.treatment or kind.title(), health_record=record)
        db.session.add(record)
        db.session.commit()
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="health"))

    diseases = sorted({condition.name for condition in CONDITIONS[animal.species]})
    # What the page's script needs to lock a pharmacy medicine's unit and
    # to spot a "new" medicine the pharmacy already has.
    stock = {key: {"name": item.name, "unit": item.unit} for key, item in form.pharmacy.items()}
    return render_template("records/health_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, diseases=diseases, today=date.today().isoformat(),
                           stock=stock, new_medicine=NEW_MEDICINE, max_medicines=MAX_MEDICINES)

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

# Young born more than this long ago aren't offered as a new birth's young.
YOUNG_FOR_DAYS = 365


def possible_young(dam, record=None):
    """The animals that could be this mother's young: the same species, on
    the same farm, with no mother recorded yet (or already linked to this
    birth), and born in the last year or with no date of birth. Animals that
    are already a mother or father themselves are left out."""
    since = date.today() - timedelta(days=YOUNG_FOR_DAYS)
    free = Livestock.b_record_id.is_(None)
    if record is not None and record.b_record_id:
        free = free | (Livestock.b_record_id == record.b_record_id)
    parents = select(BreedingRecord.animal_id).union(
        select(BreedingRecord.sire_id).where(BreedingRecord.sire_id.isnot(None)))
    return (farm_animals()
            .filter(Livestock.species == dam.species, Livestock.animal_id != dam.animal_id, free,
                    Livestock.animal_id.not_in(parents),
                    Livestock.date_of_birth.is_(None) | (Livestock.date_of_birth >= since))
            .order_by(Livestock.date_of_birth.desc(), Livestock.tag_number).all())


def link_young(record, young_ids, young_by_id):
    """Point each ticked young one at this birth, and unlink any that were
    linked before but are now unticked. One with no date of birth gets the
    birth date."""
    for animal in young_by_id.values():
        if animal.animal_id in young_ids:
            animal.b_record_id = record.b_record_id
            if animal.date_of_birth is None:
                animal.date_of_birth = record.actual_delivery_date
        elif animal.b_record_id == record.b_record_id:
            animal.b_record_id = None


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
    form = BreedingForm(dam, males, open_record, possible_young(dam, open_record))
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
                                          expected_delivery_date=expected, num_stillborn=0, notes=form.notes.data or None))
        else:
            record = open_record
            if record is None:                           # the pregnancy wasn't recorded first
                record = BreedingRecord(animal_id=dam.animal_id)
                db.session.add(record)
            record.sire_id = sire_id or record.sire_id
            record.status = "SUCCESSFUL BIRTH" if event == "BIRTH" else "NO BIRTH"
            record.actual_delivery_date = form.birth_date.data
            record.num_stillborn = form.stillborn.data
            record.notes = form.notes.data or record.notes
            if event == "BIRTH":
                db.session.flush()                       # gives a new record its id for b_record_id
                link_young(record, set(form.young.data or []), form.young_by_id)
        db.session.commit()
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
    if not form.is_submitted() and animal.market_status:
        form.market.data, form.market_note.data = animal.market_status, animal.market_note
    if form.validate_on_submit():
        if form.transaction_type.data == "MARK":
            # Identified for sale or culling: it goes on the market list for
            # the farmer's monthly review. It stays on the farm until sold.
            animal.market_status = form.market.data
            animal.market_marked_on, animal.market_note = form.date.data, form.market_note.data or None
            db.session.commit()
            flash(f"{animal.tag_number} is on the market list, {MARKET_WORDS[animal.market_status]}.", "success")
            return redirect(url_for("herd.animal_detail", animal_id=animal.animal_id))
        if form.transaction_type.data == "SELL":
            animal.market_status = None              # sold: it comes off the market list
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

@records_bp.route("/add/<species_slug>/departure/<int:animal_id>", methods=["GET", "POST"])
@login_required
def departure_form(species_slug, animal_id):
    """Given away, slaughtered at home, lost, stolen or missing: the animal
    leaves the herd lists like a sold or dead one, and its records are kept."""
    species, animal, leave = animal_for_record(species_slug, animal_id)
    if leave:
        return leave

    form = DepartureForm(animal)
    if form.validate_on_submit():
        db.session.add(Departure(animal_id=animal.animal_id, date=form.date.data, reason=form.reason.data,
                                 description=form.description.data or None))
        try:
            db.session.commit()
        except IntegrityError:
            # animal_id is UNIQUE: if two people record it at once, the second is refused here.
            db.session.rollback()
            flash(f"{animal.tag_number} has already been recorded as having left the farm.", "warning")
            return redirect(url_for("herd.animal_detail", animal_id=animal.animal_id))
        return redirect(url_for("records.record_saved", animal_id=animal.animal_id, category_key="departure"))

    return render_template("records/departure_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, today=date.today().isoformat())


# For the saved page: each category's table, and the id column whose
# highest value is the newest row.
NEWEST = {
    "health": (HealthRecord, HealthRecord.h_record_id),
    "weight": (WeightRecord, WeightRecord.w_record_id),
    "commercial": (CommercialInfo, CommercialInfo.transaction_id),
    "mortality": (MortalityRecord, MortalityRecord.m_record_id),
    "departure": (Departure, Departure.departure_id),
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
                           species_slug=SLUG_FOR[animal.species],
                           to_add=not_in_pharmacy(record) if category_key == "health" else [])
def not_in_pharmacy(record):
    """The medicines on this health record that the pharmacy doesn't have
    (by name, ignoring capitals), so the saved page can offer to add them."""
    stocked = {item.name.lower() for item in PharmacyItem.query.filter_by(farmer_id=current_farm_id())}
    return [m for m in record.medicines if m.item_id is None and m.name.lower() not in stocked]

def farm_birth_or_404(b_record_id):
    """A birth record on THIS farm (through its mother), or 404."""
    return (BreedingRecord.query.join(BreedingRecord.dam)
            .filter(BreedingRecord.b_record_id == b_record_id, Livestock.farmer_id == current_farm_id(),
                    BreedingRecord.status == "SUCCESSFUL BIRTH")
            .first_or_404())


@records_bp.route("/breeding/<int:b_record_id>/young", methods=["GET", "POST"])
@login_required
def birth_young(b_record_id):
    """Tick which registered young came from a birth already recorded."""
    record = farm_birth_or_404(b_record_id)
    dam = record.dam
    form = LinkYoungForm(record, possible_young(dam, record))
    if request.method == "GET":
        form.young.data = [animal.animal_id for animal in record.offspring]
    if form.validate_on_submit():
        link_young(record, set(form.young.data or []), form.young_by_id)
        db.session.commit()
        flash(f"{dam.tag_number}'s young are saved: {record.num_born_alive} linked.", "success")
        return redirect(url_for("herd.animal_detail", animal_id=dam.animal_id))
    return render_template("records/birth_young.html", form=form, record=record, dam=dam,
                           species_slug=SLUG_FOR[dam.species])