"""General pages that aren't about accounts: the welcome page and the dashboard."""
from datetime import datetime

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

# A blueprint is a group of related pages. "main" is its name, which is why
# templates refer to these pages as url_for('main.index') and so on.
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Wireframe 1: 'Which account are you logging in to?'"""
    # Already logged in? There's nothing to choose, so go to the dashboard.
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required  # not logged in? Flask-Login sends them to the welcome page
def dashboard():
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    # isinstance() asks "is the logged-in account a Farmer object?". This is
    # how the app tells the two roles apart, and it decides what's shown.
    return render_template("dashboard.html", greeting=greeting)