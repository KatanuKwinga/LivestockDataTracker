#Settings for the app, read from the .env file.
import os
import ssl

from dotenv import load_dotenv

# Reads .env and puts each NAME=value line into os.environ, as if it had been
# typed into the terminal. It must run before the Config class reads them.
load_dotenv()


def _engine_options(database_url):
    """Extra settings for SQLAlchemy's connection to the database."""
    # Supabase closes connections that sit idle, and a shaky network can cut
    # them. pool_pre_ping tests a saved connection with a tiny "SELECT 1"
    # before reusing it, and reconnects if it has died instead of failing.
    options = {"pool_pre_ping": True}

    # Encrypt the connection to Supabase so the password and data can't be
    # read on the way. pg8000 takes this as an "SSL context" object rather
    # than the ?sslmode=require text some other drivers read from the URL.
    if database_url and database_url.startswith("postgresql+pg8000"):
        ssl_context = ssl.create_default_context()
        # Encrypt, but don't check the server's certificate against a list of
        # trusted authorities: Supabase signs it with its own authority, which
        # Windows doesn't know. This matches what sslmode=require does.
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        options["connect_args"] = {"ssl_context": ssl_context}

    return options


class Config:
    # Signs the login cookie (and, later, password-reset links). Anyone who
    # knew it could forge a login, so it lives only in .env.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Where the database is: the Supabase address from .env.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    # An old Flask-SQLAlchemy feature that tracks every change in memory.
    # We don't use it and it costs memory, so it's switched off.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)