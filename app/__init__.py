#Builds the Flask app. 
from flask import Flask
from sqlalchemy import text

from app.config import Config
from app.extensions import bcrypt, db, login_manager, migrate


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

    # Import the models so SQLAlchemy and Flask-Migrate know the tables exist.
    from app import models  

    @app.route("/health")
    def health():
        #Quick check that the app is running and can reach the database.
        try:
            db.session.execute(text("SELECT 1"))
            return {"app": "ok", "database": "ok"}
        except Exception:
            # A failed query leaves the session in an error state; rollback()
            # resets it so the next request starts clean.
            db.session.rollback()
            return {"app": "ok", "database": "unreachable"}, 503

    return app