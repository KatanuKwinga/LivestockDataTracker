"""Treat a group: one session of tick spraying, deworming or vaccination
for many animals at once."""
from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.farm import current_farm_id, farm_animals, still_on_farm
from app.forms import GroupForm
from app.models import Farmer, HealthRecord, HerdActivity, Livestock
from app.models.livestock import SPECIES
from app.routes.records import SLUG_FOR, SPECIES_CHOICES
from app.stock import add_line 
from ml.reference import DEWORM_MIN_AGE_DAYS, DEWORMER, SPRAY_PRODUCT, SPRAYS_PER_WEEK

group_bp = Blueprint("group", __name__, url_prefix="/group")

# Must match DEWORMING in ml/features.py: the model finds dewormings by it.
DEWORMING_NOTE = "Routine deworming"

ACTIVITIES = {
    "spray": {"code": "TICK_SPRAY", "title": "Tick spraying", "icon": "i-spray",
              "blurb": "Spray or dip a whole herd against ticks",
              "species": tuple(SPRAYS_PER_WEEK), "per_animal": False},   # chickens aren't sprayed
    "deworm": {"code": "DEWORMING", "title": "Deworming", "icon": "i-deworm",
               "blurb": "Drench a group against worms",
               "species": SPECIES, "per_animal": True},
    "vaccinate": {"code": "VACCINATION", "title": "Vaccination", "icon": "i-vaccine",
                  "blurb": "Vaccinate many animals in one go",
                  "species": SPECIES, "per_animal": True},
}
TITLE_FOR_CODE = {activity["code"]: activity["title"] for activity in ACTIVITIES.values()}


def activity_or_404(key):
    activity = ACTIVITIES.get(key)
    if activity is None:
        abort(404)
    return activity


def animals_treated(session):
    """How many animals a deworming or vaccination session covered, counted
    from the health records saved with it."""
    if session.activity == "TICK_SPRAY":
        return None
    query = (HealthRecord.query.join(HealthRecord.animal)
             .filter(Livestock.farmer_id == session.farmer_id, Livestock.species == session.species,
                     HealthRecord.date == session.date, HealthRecord.treatment == session.product))
    if session.activity == "DEWORMING":
        query = query.filter(HealthRecord.description == DEWORMING_NOTE)
    else:
        query = query.filter(HealthRecord.record_type == "VACCINATION")
    return query.count()


def too_young_to_deworm(animal):
    """Leave out animals under 30 days old (DEWORM_MIN_AGE_DAYS)."""
    return animal.date_of_birth is not None and (date.today() - animal.date_of_birth).days < DEWORM_MIN_AGE_DAYS


@group_bp.route("/")
@login_required
def index():
    """Step 1: choose the activity. Below it, the farm's latest sessions."""
    recent = (HerdActivity.query.filter_by(farmer_id=current_farm_id())
              .order_by(HerdActivity.date.desc(), HerdActivity.activity_id.desc()).limit(10).all())
    rows = [{"session": s, "title": TITLE_FOR_CODE.get(s.activity, s.activity.title()),
             "count": animals_treated(s)} for s in recent]
    return render_template("group/index.html", activities=ACTIVITIES, rows=rows)


@group_bp.route("/<activity_key>")
@login_required
def choose_species(activity_key):
    """Step 2: which herd. Only the species this activity is done to."""
    activity = activity_or_404(activity_key)
    choices = [(slug, species) for slug, species in SPECIES_CHOICES.items() if species["value"] in activity["species"]]
    counts = {species["value"]: farm_animals().filter(Livestock.species == species["value"], still_on_farm()).count()
              for _, species in choices}
    return render_template("group/choose_species.html", activity=activity, activity_key=activity_key,
                           choices=choices, counts=counts)


@group_bp.route("/<activity_key>/<species_slug>", methods=["GET", "POST"])
@login_required
def treat(activity_key, species_slug):
    """Step 3: the session's details, and (for deworming and vaccination)
    which animals were treated."""
    activity = activity_or_404(activity_key)
    species = SPECIES_CHOICES.get(species_slug)
    if species is None or species["value"] not in activity["species"]:
        abort(404)

    animals = (farm_animals().filter(Livestock.species == species["value"], still_on_farm())
               .order_by(Livestock.tag_number).all())
    form = GroupForm(activity_key, species["value"], animals, current_farm_id())
    if request.method == "GET":
        if activity_key == "spray":
            form.product.data = SPRAY_PRODUCT
        elif activity_key == "deworm":
            form.product.data = DEWORMER[species["value"]]
        # Pick the pharmacy medicine whose name is in the product, e.g.
        # Dominex for "Dip Dominex", so the usual case needs no choosing.
        product = (form.product.data or "").lower() if activity_key != "vaccinate" else ""
        form.medicine.data = next((key for key, item in form.pharmacy.items()
                                   if product and item.name.lower() in product), "")
        # Everyone is ticked to start with, except animals too young to deworm.
        form.animals.data = [a.animal_id for a in animals
                             if not (activity_key == "deworm" and too_young_to_deworm(a))]

    if form.validate_on_submit():
        medicine = form.chosen_medicine
        product = form.vaccine.data if activity_key == "vaccinate" else (form.product.data or medicine.name)        
        session = HerdActivity(farmer_id=current_farm_id(), species=species["value"], date=form.date.data,
                               activity=activity["code"], product=product, notes=form.notes.data or None)
        db.session.add(session)
        if activity["per_animal"]:
            for animal_id in form.animals.data:
                if activity_key == "deworm":
                    record = HealthRecord(record_type="TREATMENT", treatment=product, description=DEWORMING_NOTE)
                else:
                    record = HealthRecord(record_type="VACCINATION", treatment=product, description="Group vaccination")
                record.animal_id, record.date = animal_id, form.date.data
                db.session.add(record)
        if medicine is not None:
            # One ledger line for the whole session (e.g. 300 ml of Dominex
            # for the herd), pointing back to it.
            treated = len(form.animals.data) if activity["per_animal"] else len(animals)
            add_line(medicine, "USED", form.medicine_amount.data, form.date.data, current_user.user_id,
                     checked=isinstance(current_user, Farmer), activity=session,
                     remarks=f"{activity['title']}, {treated} {species['label'].lower()}")
        db.session.commit()
        return redirect(url_for("group.saved", activity_id=session.activity_id))

    young = {a.animal_id for a in animals if activity_key == "deworm" and too_young_to_deworm(a)}
    return render_template("group/treat.html", form=form, activity=activity, activity_key=activity_key,
                           species=species, species_slug=species_slug, animals=animals, young=young,
                           min_age=DEWORM_MIN_AGE_DAYS, today=date.today().isoformat())


@group_bp.route("/saved/<int:activity_id>")
@login_required
def saved(activity_id):
    """The confirmation page. filter_by(farmer_id=...) keeps other farms'
    sessions out of reach, just as get_farm_animal_or_404 does for animals."""
    session = HerdActivity.query.filter_by(activity_id=activity_id, farmer_id=current_farm_id()).first_or_404()
    key = next(k for k, a in ACTIVITIES.items() if a["code"] == session.activity)
    return render_template("group/saved.html", session=session, activity=ACTIVITIES[key], activity_key=key,
                           species=SPECIES_CHOICES[SLUG_FOR[session.species]], species_slug=SLUG_FOR[session.species],
                           count=animals_treated(session))