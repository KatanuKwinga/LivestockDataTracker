from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.farm import (current_farm_id, farm_animals, get_farm_animal_or_404,
                      search_animals, still_on_farm, suggest_tag_number)
from app.csv_import import KINDS
from app.forms import AnimalForm, ImportFileForm
from app.models import Livestock

records_bp = Blueprint("records", __name__, url_prefix="/records")

# "mark" is the species' tag prefix (C001, CH001...), shown in place of an icon.
SPECIES_CHOICES = {
    "cattle": {"value": "CATTLE", "label": "Cattle", "mark": "C"},
    "chicken": {"value": "CHICKEN", "label": "Chickens", "mark": "CH"},
    "goat": {"value": "GOAT", "label": "Goats", "mark": "G"},
    "sheep": {"value": "SHEEP", "label": "Sheep", "mark": "S"},
}
# The other way round: "GOAT" -> "goat", for building links from an animal.
SLUG_FOR = {species["value"]: slug for slug, species in SPECIES_CHOICES.items()}

# Breeds kept in Kenya, offered as suggestions under the Breed box. They are
# only suggestions: a worker can still type a breed that isn't listed.
BREEDS = {
    "CATTLE": ["Friesian", "Ayrshire", "Jersey", "Guernsey", "Boran", "Sahiwal", "Zebu", "Cross"],
    "CHICKEN": ["Kienyeji", "Kuroiler", "Kenbro", "Rainbow Rooster", "Broiler", "Layer"],
    "GOAT": ["Galla", "Small East African", "Toggenburg", "Saanen", "Alpine", "Boer", "Cross"],
    "SHEEP": ["Dorper", "Red Maasai", "Blackhead Persian", "Merino", "Corriedale", "Cross"],
}

# "endpoint" is the form a category's records are entered on. Categories
# without one yet show as "Coming soon".
CATEGORIES = [
    {"key": "general", "title": "General", "blurb": "Basic animal details", "icon": "i-general", "endpoint": "records.general_form"},
    {"key": "health", "title": "Health", "blurb": "Illness, treatment and vaccination", "icon": "i-health", "endpoint": "records.health_form"},
    {"key": "weight", "title": "Weight", "blurb": "Weigh-ins and growth", "icon": "i-weight", "endpoint": "records.weight_form"},    
    {"key": "breeding", "title": "Breeding", "blurb": "Pregnancy and births", "icon": "i-breed", "endpoint": "records.breeding_form", "females_only": True},
    {"key": "production", "title": "Production", "blurb": "Milk and eggs", "icon": "i-prod", "endpoint": "records.production_form", "females_only": True},
    {"key": "commercial", "title": "Commercial", "blurb": "Purchases and sales", "icon": "i-sale", "endpoint": "records.commercial_form"},
    {"key": "mortality", "title": "Mortality", "blurb": "Death information", "icon": "i-loss", "endpoint": "records.mortality_form"},
    {"key": "departure", "title": "Left the farm", "blurb": "Given away, eaten, lost or stolen", "icon": "i-leave", "endpoint": "records.departure_form"},]


def species_or_404(species_slug):
    species = SPECIES_CHOICES.get(species_slug)
    if species is None:
        abort(404)
    return species


def category_or_404(key):
    """The category for this URL, if it exists and its form is built."""
    for category in CATEGORIES:
        if category["key"] == key and category["endpoint"]:
            return category
    abort(404)


@records_bp.route("/add")
@login_required
def choose_species():
    return render_template("records/choose_species.html", species_choices=SPECIES_CHOICES)


@records_bp.route("/add/<species_slug>")
@login_required
def choose_category(species_slug):
    species = species_or_404(species_slug)
    return render_template("records/choose_category.html", species=species,
                           species_slug=species_slug, categories=CATEGORIES)


@records_bp.route("/add/<species_slug>/<category_key>")
@login_required
def choose_animal(species_slug, category_key):
    """Step 3: pick the animal the record is about (or, for General,
    register a new one). Only this farm's animals of this species that are
    still on the farm are listed; ?q= narrows them by tag or breed."""
    species = species_or_404(species_slug)
    category = category_or_404(category_key)
    q = request.args.get("q", "").strip()

    animals = farm_animals().filter(Livestock.species == species["value"], still_on_farm())
    if category.get("females_only"):
        animals = animals.filter(Livestock.gender == "FEMALE")
    animals = search_animals(animals, q).order_by(Livestock.tag_number).all()


    return render_template("records/choose_animal.html", species=species, species_slug=species_slug,
                           category=category, animals=animals, q=q,
                           next_tag=suggest_tag_number(current_farm_id(), species["value"]))


@records_bp.route("/add/<species_slug>/general/new", methods=["GET", "POST"])
@records_bp.route("/add/<species_slug>/general/<int:animal_id>", methods=["GET", "POST"])
@login_required
def general_form(species_slug, animal_id=None):
    """Register a new animal, or correct an existing one's details."""
    species = species_or_404(species_slug)
    animal = None
    if animal_id is not None:
        animal = get_farm_animal_or_404(animal_id)
        if animal.species != species["value"]:
            abort(404)

    form = AnimalForm(current_farm_id(), animal)
    if request.method == "GET" and animal is None:
        form.tag_number.data = suggest_tag_number(current_farm_id(), species["value"])

    if form.validate_on_submit():
        is_new = animal is None
        if is_new:
            animal = Livestock(farmer_id=current_farm_id(), species=species["value"])
            db.session.add(animal)
        animal.tag_number = form.tag_number.data
        animal.gender = form.gender.data
        animal.castrated = form.castrated.data and form.gender.data == "MALE"
        animal.breed = form.breed.data or None
        animal.date_of_birth = form.date_of_birth.data
        animal.description = form.description.data or None
        try:
            db.session.commit()
        except IntegrityError:
            # Two people saved the same tag at the same moment: the
            # database's UNIQUE rule caught what the form's check couldn't.
            db.session.rollback()
            form.tag_number.errors.append("Another animal on this farm already has this tag.")
        else:
            return redirect(url_for("records.saved", animal_id=animal.animal_id,
                                    action="registered" if is_new else "updated"))

    return render_template("records/general_form.html", form=form, animal=animal, species=species,
                           species_slug=species_slug, breeds=BREEDS[species["value"]],
                           today=date.today().isoformat())


@records_bp.route("/saved/<int:animal_id>")
@login_required
def saved(animal_id):
    """The confirmation page after saving, with the next likely steps.

    It's a separate page we redirect to (Post/Redirect/Get), so refreshing
    it can't submit the form a second time."""
    animal = get_farm_animal_or_404(animal_id)
    action = "updated" if request.args.get("action") == "updated" else "registered"
    slug = SLUG_FOR[animal.species]
    return render_template("records/saved.html", animal=animal, action=action,
                           species=SPECIES_CHOICES[slug], species_slug=slug)



# ---------- adding many animals at once from a CSV file ----------

@records_bp.route("/import", defaults={"kind": "animals"}, methods=["GET", "POST"])
@records_bp.route("/import/<kind>", methods=["GET", "POST"])
@login_required
def import_file(kind):
    """Upload a CSV of animals, health records or weights. Every row is
    checked first: either all of them are saved, or none are and each
    problem is listed. The same route serves all three; KINDS says which
    reader checks the rows and what the page explains."""
    if kind not in KINDS:
        abort(404)
    info = KINDS[kind]
    form = ImportFileForm()
    problems = []
    if form.validate_on_submit():
        rows, problems = info["read"](form.file.data.read(), current_farm_id())
        if not problems:
            db.session.add_all(rows)
            try:
                db.session.commit()
            except IntegrityError:
                # Someone else changed the farm in the moment between the check
                # and the save (e.g. added one of these tags).
                db.session.rollback()
                problems = [(None, "Someone changed the farm's records just now. Upload the file again.")]
            else:
                flash(f"{len(rows)} {info['noun']}{'s' if len(rows) != 1 else ''} added from the file.", "success")
                if kind == "animals":
                    return redirect(url_for("herd.list_animals", status="all"))
                return redirect(url_for("records.import_file", kind=kind))
    return render_template("records/import.html", form=form, problems=problems,
                           kind=kind, info=info, kinds=KINDS)


@records_bp.route("/import/<kind>/template.csv")
@login_required
def import_template(kind):
    """An example file with the right column headings, to fill in."""
    if kind not in KINDS:
        abort(404)
    return Response(KINDS[kind]["template"], mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={kind}_template.csv"})