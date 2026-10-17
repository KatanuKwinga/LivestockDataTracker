from datetime import date, datetime

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app.extensions import db
from app.farm import current_farm_id
from app.models import CommercialInfo, Farmer, Livestock, MortalityRecord, Worker

main_bp = Blueprint("main", __name__)

# Species in the order the home pages show them, with the CSS class that
# colours each one in the herd bar.
HERD_ORDER = [
    ("CATTLE", "Cattle", "sp-cattle"),
    ("GOAT", "Goats", "sp-goat"),
    ("SHEEP", "Sheep", "sp-sheep"),
    ("CHICKEN", "Chickens", "sp-chicken"),
]


def herd_summary(farm_id):
    """How many animals of each species are on the farm right now.

    Animals that have died (a mortality record) or been sold (a SELL record)
    are no longer on the farm, so they are left out. Returns a list of
    dicts for the template, and the total."""
    dead = select(MortalityRecord.animal_id)
    sold = select(CommercialInfo.animal_id).where(CommercialInfo.transaction_type == "SELL")
    rows = db.session.execute(
        select(Livestock.species, func.count())
        .where(Livestock.farmer_id == farm_id,
               Livestock.animal_id.not_in(dead), Livestock.animal_id.not_in(sold))
        .group_by(Livestock.species)
    ).all()
    counts = dict(rows)
    total = sum(counts.values())
    herd = [{"label": label, "css": css, "count": counts.get(key, 0),
             "share": round(100 * counts.get(key, 0) / total, 1) if total else 0}
            for key, label, css in HERD_ORDER]
    return herd, total


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """Home page. Farmers and workers get different pages: each only sees
    what their role needs."""
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    today = date.today()
    herd, total = herd_summary(current_farm_id())
    context = {
        "greeting": greeting,
        "first_name": current_user.name.split()[0],
        "today": f"{today:%A} {today.day} {today:%B %Y}",
        "herd": herd,
        "total": total,
    }
    if isinstance(current_user, Farmer):
        context["worker_count"] = Worker.query.filter_by(farmer_id=current_user.farmer_id).count()
        return render_template("home_farmer.html", **context)
    return render_template("home_worker.html", **context)
