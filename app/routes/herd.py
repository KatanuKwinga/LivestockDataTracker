"""Viewing the herd: the records table and one animal's full history.

Adding records lives in records.py; this blueprint only reads. Keeping them
apart also lets the navbar highlight "Add record" and "Records" separately.
"""
from datetime import date

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.farm import farm_animals, get_farm_animal_or_404, search_animals, status_filter
from app.models import Livestock
from app.routes.records import SLUG_FOR, SPECIES_CHOICES

herd_bp = Blueprint("herd", __name__, url_prefix="/herd")

STATUSES = {"on_farm": "On the farm", "sold": "Sold", "died": "Died", "all": "All animals"}
PER_PAGE = 25


@herd_bp.route("/")
@login_required
def list_animals():
    """Every animal on the farm in a table, with search and two filters."""
    species_slug = request.args.get("species", "")
    if species_slug not in SPECIES_CHOICES:
        species_slug = ""
    status = request.args.get("status", "on_farm")
    if status not in STATUSES:
        status = "on_farm"
    q = request.args.get("q", "").strip()

    query = farm_animals().filter(status_filter(status))
    if species_slug:
        query = query.filter(Livestock.species == SPECIES_CHOICES[species_slug]["value"])
    query = search_animals(query, q)

    # selectinload fetches every row's mortality and sales records in two
    # extra queries, instead of two per animal, when the table shows status.
    page = (query.options(selectinload(Livestock.mortality_record), selectinload(Livestock.commercial_records))
            .order_by(Livestock.species, Livestock.tag_number)
            .paginate(page=request.args.get("page", 1, type=int), per_page=PER_PAGE, error_out=False))

    filters = {key: value for key, value in {"species": species_slug, "status": status, "q": q}.items() if value}
    return render_template("herd/list.html", page=page, filters=filters, species_slug=species_slug,
                           status=status, q=q, statuses=STATUSES, species_choices=SPECIES_CHOICES,
                           slug_for=SLUG_FOR)


@herd_bp.route("/<int:animal_id>")
@login_required
def animal_detail(animal_id):
    """One animal's page: its details, then each kind of record, newest first.
    get_farm_animal_or_404 means another farm's animal is "Not found"."""
    animal = get_farm_animal_or_404(animal_id)
    # A female's breeding records are the times she was the mother; a male's
    # are the times he was the father.
    events = animal.dam_events if animal.gender == "FEMALE" else animal.sire_events
    breeding = sorted(events, key=lambda b: b.actual_delivery_date or b.expected_delivery_date or date.min,
                      reverse=True)
    return render_template("herd/detail.html", animal=animal, species_slug=SLUG_FOR[animal.species],
                           breeding=breeding,
                           latest_weight=animal.weight_records[-1] if animal.weight_records else None)
