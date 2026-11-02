"""The farmer's Analytics page: the farm's records as charts."""
from flask import Blueprint, render_template, request

from app.analytics import farm_analytics
from app.decorators import farmer_required
from app.farm import current_farm_id

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/")
@farmer_required
def index():
    months = 24 if request.args.get("months") == "24" else 12
    return render_template("analytics/index.html", data=farm_analytics(current_farm_id(), months), months=months)