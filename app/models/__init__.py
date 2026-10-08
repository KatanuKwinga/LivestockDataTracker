"""Imports every model, so that `from app.models import User` works anywhere
and Flask-Migrate can see all the tables when it builds a migration."""
from app.models.user import Farmer, User, Worker
from app.models.livestock import Livestock
from app.models.weight import WeightRecord
from app.models.health import HealthRecord