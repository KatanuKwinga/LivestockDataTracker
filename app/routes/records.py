from flask import Blueprint, abort, render_template
from flask_login import login_required

records_bp = Blueprint("records", __name__, url_prefix="/records")

# "mark" is the species' tag prefix (C001, CH001...), shown in place of an icon.
SPECIES_CHOICES = {
    "cattle": {"value": "CATTLE", "label": "Cattle", "mark": "C"},
    "chicken": {"value": "CHICKEN", "label": "Chickens", "mark": "CH"},
    "goat": {"value": "GOAT", "label": "Goats", "mark": "G"},
    "sheep": {"value": "SHEEP", "label": "Sheep", "mark": "S"},
}

CATEGORIES = [
    {"key": "general", "title": "General", "blurb": "Basic animal details", "icon": "i-general", "endpoint": None},
    {"key": "health", "title": "Health", "blurb": "Diseases and treatments", "icon": "i-health", "endpoint": None},
    {"key": "breeding", "title": "Breeding", "blurb": "Pregnancy and lineage", "icon": "i-breed", "endpoint": None},
    {"key": "production", "title": "Production", "blurb": "Tracking produce", "icon": "i-prod", "endpoint": None},
    {"key": "commercial", "title": "Commercial", "blurb": "Purchases and sales", "icon": "i-sale", "endpoint": None},
    {"key": "mortality", "title": "Mortality", "blurb": "Death information", "icon": "i-loss", "endpoint": None},
]

#To stop someone from tying in an animal that isn't one of the 4
def species_or_404(species_slug):
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
