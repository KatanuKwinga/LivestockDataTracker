#The data-entry flow from choosing a species then the data category

from flask import Blueprint, abort, render_template
from flask_login import login_required

records_bp = Blueprint("records", __name__, url_prefix="/records")

# The species, keyed by how they appear in the web address (/records/add/goat).
#   value: what's stored in the database (Livestock.species)
#   label: what people see
#   icon:  a picture for the card (an emoji, so no image files are needed)
SPECIES_CHOICES = {
    "cattle": {"value": "CATTLE", "label": "Cattle", "icon": "🐄"},
    "chicken": {"value": "CHICKEN", "label": "Chickens", "icon": "🐔"},
    "goat": {"value": "GOAT", "label": "Goats", "icon": "🐐"},
    "sheep": {"value": "SHEEP", "label": "Sheep", "icon": "🐑"},
}

# The 6 categories from wireframe 3, in the same order and with the same wording.
# "endpoint" is the route that handles each category's form. None = not built
# yet, so the card shows "Coming soon" instead of a link that goes nowhere.
# Each later batch fills in one endpoint.
CATEGORIES = [
    {"key": "general", "title": "General", "blurb": "Basic animal details", "endpoint": None},
    {"key": "health", "title": "Health", "blurb": "Diseases and treatments", "endpoint": None},
    {"key": "breeding", "title": "Breeding", "blurb": "Pregnancy and lineage", "endpoint": None},
    {"key": "production", "title": "Production", "blurb": "Tracking produce", "endpoint": None},
    {"key": "commercial", "title": "Commercial", "blurb": "Purchases and sales", "endpoint": None},
    {"key": "mortality", "title": "Mortality", "blurb": "Death information", "endpoint": None},
]


def species_or_404(species_slug):
    """Look up a species from the web address; anything else is 'Not Found'.
    This stops someone typing /records/add/horse and reaching a broken page."""
    species = SPECIES_CHOICES.get(species_slug)
    if species is None:
        abort(404)
    return species


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