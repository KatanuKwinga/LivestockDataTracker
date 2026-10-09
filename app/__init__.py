"""Builds the Flask app. This is the "application factory" pattern."""
from flask import Flask
from sqlalchemy import text

from app.config import Config
from app.extensions import bcrypt, csrf, db, login_manager, mail, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Stop at start-up with a clear message, instead of failing later with a
    # confusing error on the first page that needs the database.
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is missing. Add it to your .env file.")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL is missing. Add it to your .env file.")

    # Connect each tool from extensions.py to this app.
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    # Where @login_required sends visitors who aren't logged in: the welcome
    # page, where they pick Farmer or Worker. The message appears as a flash.
    login_manager.login_view = "main.index"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"

    # Import the models so SQLAlchemy and Flask-Migrate know the tables exist.
    from app import models  # noqa: F401

    # Each blueprint is a group of related pages. Registering it switches
    # its routes on.
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.workers import workers_bp
    app.register_blueprint(workers_bp)

    # A context processor adds variables to EVERY template automatically.
    # Here: is_farmer, so base.html can show farmer-only links (like
    # "Workers") without every route having to pass it in.
    @app.context_processor
    def inject_role():
        from flask_login import current_user
        from app.models import Farmer
        return {"is_farmer": current_user.is_authenticated and isinstance(current_user, Farmer)}
    
    @app.route("/health")
    def health():
        """Quick check that the app is running and can reach the database."""
        try:
            db.session.execute(text("SELECT 1"))
            return {"app": "ok", "database": "ok"}
        except Exception:
            # A failed query leaves the session in an error state; rollback()
            # resets it so the next request starts clean.
            db.session.rollback()
            return {"app": "ok", "database": "unreachable"}, 503

    return app