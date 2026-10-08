"""Access rules that can be put on any page with one line."""
from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user, login_required

from app.models import Farmer


def farmer_required(view):
    """Only farmers may open the page; everyone else is turned away.

    Use it like @login_required:

        @workers_bp.route("/")
        @farmer_required
        def list_workers(): ...

    It includes @login_required, so visitors who aren't logged in are sent
    to the welcome page first.
    """
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        # Logged in, but as a worker: send them to their dashboard.
        if not isinstance(current_user, Farmer):
            flash("Only a farmer account can open that page.", "warning")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)
    return wrapped