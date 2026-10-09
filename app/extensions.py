"""The Flask extensions, created once here and shared by the whole app.

They are created *without* an app and connected to it later, in create_app()
(app/__init__.py). That way models and routes can simply write
`from app.extensions import db` without needing the app to exist yet, which
avoids "circular import" errors.
"""
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail

db = SQLAlchemy()               # talks to the database
migrate = Migrate()             # creates and updates tables to match the models
login_manager = LoginManager()  # remembers who is logged in between pages
bcrypt = Bcrypt()               # hashes passwords so they're never stored as-is
csrf = CSRFProtect()            # requires a CSRF token on EVERY POST, not just WTForms forms

mail = Mail()                   # sends email (password reset)