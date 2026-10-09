#Helpers every livestock page uses to stay inside the logged-in user's farm.
import re

from flask_login import current_user

from app.models import Livestock
from app.models.livestock import TAG_PREFIXES


def current_farm_id():
    #The farm the logged-in user works on.
    return current_user.farmer_id


def farm_animals():
    #A query for the current farm's animals ONLY. 
    return Livestock.query.filter_by(farmer_id=current_farm_id())


def get_farm_animal_or_404(animal_id):
    #Fetch one animal by its ID, but only if it belongs to the current farm.
    return farm_animals().filter_by(animal_id=animal_id).first_or_404()


def suggest_tag_number(farm_id, species):
    #The next free tag for a species on a farm: G001, G002, ...
    prefix = TAG_PREFIXES[species]
    # ^ and $ = the WHOLE tag must match: the prefix, then only digits.
    # So the cattle pattern "C" + digits doesn't match chicken tags like "CH020".
    pattern = re.compile(rf"^{prefix}(\d+)$")
    existing = Livestock.query.with_entities(Livestock.tag_number).filter_by(farmer_id=farm_id, species=species)
    numbers = [int(m.group(1)) for (tag,) in existing if (m := pattern.match(tag))]
    # :03d = at least 3 digits, padded with zeros: 8 -> "008".
    return f"{prefix}{max(numbers, default=0) + 1:03d}"