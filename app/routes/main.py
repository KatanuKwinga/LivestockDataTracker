from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app import status
from app.decorators import farmer_required
from app.extensions import db
from app.farm import current_farm_id, still_on_farm
from app.forms import FarmSettingsForm
from app.status_filters import filter_page, is_filtered
from app.weather import get_weather
from app.models import Farmer, Livestock, Worker
from app.routes.records import SLUG_FOR

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
    """How many animals of each species are on the farm right now."""
    rows = db.session.execute(
        select(Livestock.species, func.count())
        .where(Livestock.farmer_id == farm_id, still_on_farm())
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
        context["status"] = status.all_statuses(current_farm_id())
        context["weather"], context["place"] = farm_weather(current_user)
        return render_template("home_farmer.html", **context)
    return render_template("home_worker.html", **context)



# The dashboard tiles that open a page of details, and what each page shows.
STATUS_PAGES = {
    "health": ("Unwell animals", status.unwell),
    "condition": ("Pregnant animals", status.pregnant),
    "market": ("Market list", status.market),
    "outlook": ("Coming up", status.outlook),
}


@main_bp.route("/status/<key>")
@farmer_required
def status_detail(key):
    """The details behind one dashboard tile, e.g. which animals are unwell."""
    if key not in STATUS_PAGES:
        abort(404)
    title, work_out = STATUS_PAGES[key]
    s = work_out(current_farm_id())
    # The tile's full list is `s`; the filtered rows are what the table shows.
    rows, chosen, choices = filter_page(key, s, request.args)
    return render_template(f"status/{key}.html", title=title, s=s, rows=rows, chosen=chosen,
                           choices=choices, filtered=is_filtered(chosen),
                           unwell_days=status.UNWELL_DAYS, today=date.today())

def farm_place(farmer):
    """Where the farm is: its name, and whether the farmer has set its
    location. There is no default: the weather is only for a real place."""
    return {"name": farmer.location_name, "set": farmer.latitude is not None and farmer.longitude is not None}


def farm_weather(farmer):
    """The weather at the farm and its place. The weather is None until the
    location is set, or when the weather service can't be reached."""
    place = farm_place(farmer)
    weather = get_weather(farmer.latitude, farmer.longitude) if place["set"] else None
    return weather, place


@main_bp.route("/alerts")
@farmer_required
def disease_alerts():
    """Which diseases each group of animals is likely to get in the next 30
    days (the model in ml/), with the reasons and what to do, plus the farm's
    weather, the rule-based warnings and the watch list."""
    # Imported here, not at the top: pandas and scikit-learn are only loaded
    # when someone opens this page, so the rest of the app starts quickly.
    from ml.alerts import farm_alerts

    weather, place = farm_weather(current_user)
    try:
        alerts = farm_alerts(current_farm_id(), weather=weather)
    except FileNotFoundError:
        return render_template("status/alerts.html", missing=True, weather=weather, place=place)
    return render_template("status/alerts.html", missing=False, a=alerts, today=date.today(),
                           weather=weather, place=place)


@main_bp.route("/settings", methods=["GET", "POST"])
@farmer_required
def farm_settings():
    """Where the farm is: the weather and the disease alerts use it."""
    form = FarmSettingsForm(obj=current_user)
    if form.validate_on_submit():
        current_user.location_name = form.location_name.data.strip()
        # 4 decimals is about 11 m: plenty for weather, and no false precision.
        current_user.latitude = round(form.latitude.data, 4)
        current_user.longitude = round(form.longitude.data, 4)
        db.session.commit()
        flash("Farm location saved. The weather and disease alerts now use it.", "success")
        return redirect(url_for("main.farm_settings"))
    return render_template("settings.html", form=form, place=farm_place(current_user))