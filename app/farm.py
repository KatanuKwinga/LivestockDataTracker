import re

from flask_login import current_user
from sqlalchemy import and_, select

from app.models import CommercialInfo, Livestock, MortalityRecord
from app.models.livestock import TAG_PREFIXES


def current_farm_id():
    return current_user.farmer_id


def farm_animals():
    return Livestock.query.filter_by(farmer_id=current_farm_id())


def get_farm_animal_or_404(animal_id):
    return farm_animals().filter_by(animal_id=animal_id).first_or_404()


def still_on_farm():
    """A filter for animals that are still on the farm. Their records are kept and not deleted when they die or are sold"""
    dead = select(MortalityRecord.animal_id)
    sold = select(CommercialInfo.animal_id).where(CommercialInfo.transaction_type == "SELL")
    return and_(Livestock.animal_id.not_in(dead), Livestock.animal_id.not_in(sold))


def tag_in_use(farm_id, tag, except_animal_id=None):
    """True if another animal on this farm already has this tag. Two different farms can both have a G001."""
    query = Livestock.query.filter_by(farmer_id=farm_id, tag_number=tag)
    if except_animal_id is not None:
        query = query.filter(Livestock.animal_id != except_animal_id)
    return query.first() is not None


def suggest_tag_number(farm_id, species):
    prefix = TAG_PREFIXES[species]
    pattern = re.compile(rf"^{prefix}(\d+)$")
    existing = Livestock.query.with_entities(Livestock.tag_number).filter_by(farmer_id=farm_id, species=species)
    numbers = [int(m.group(1)) for (tag,) in existing if (m := pattern.match(tag))]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"
