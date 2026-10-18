import re

from flask_login import current_user
from sqlalchemy import and_, func, or_, select, true

from app.models import CommercialInfo, Livestock, MortalityRecord
from app.models.livestock import TAG_PREFIXES


def current_farm_id():
    return current_user.farmer_id


def farm_animals():
    return Livestock.query.filter_by(farmer_id=current_farm_id())


def get_farm_animal_or_404(animal_id):
    return farm_animals().filter_by(animal_id=animal_id).first_or_404()


def dead_ids():
    """The ids of animals that have died (they have a mortality record)."""
    return select(MortalityRecord.animal_id)


def sold_ids():
    """The ids of animals that have been sold (they have a SELL record)."""
    return select(CommercialInfo.animal_id).where(CommercialInfo.transaction_type == "SELL")


def still_on_farm():
    """A filter for animals that are still on the farm."""
    return and_(Livestock.animal_id.not_in(dead_ids()), Livestock.animal_id.not_in(sold_ids()))


def status_filter(status):
    """A filter for the herd page's Status box: "on_farm", "sold", "died" or "all"."""
    if status == "sold":
        return Livestock.animal_id.in_(sold_ids())
    if status == "died":
        return Livestock.animal_id.in_(dead_ids())
    if status == "all":
        return true()
    return still_on_farm()


def search_animals(query, q):
    """Narrow a Livestock query to animals whose tag or breed contains q."""
    q = (q or "").strip().lower()
    if not q:
        return query
    return query.filter(or_(
        func.lower(Livestock.tag_number).contains(q, autoescape=True),
        func.lower(Livestock.breed).contains(q, autoescape=True),
    ))

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
