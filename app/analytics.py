"""The numbers behind the farmer's Analytics page, worked out from the records.

Everything is counted per calendar month, over the last 12 (or 24) months
up to today. The page is worked out fresh each time, so it always matches the records.
"""
from collections import Counter
from datetime import date, timedelta

from app.models import CommercialInfo, HealthRecord, Livestock, MortalityRecord

SPECIES = [("CATTLE", "Cattle"), ("GOAT", "Goats"), ("SHEEP", "Sheep")]
TOP_CAUSES = 6          # the commonest causes of death; the rest are added up as "Other"


def month_starts(months, today):
    """The first day of each of the last `months` months, oldest first, ending with this month."""
    year, month = today.year, today.month
    starts = []
    for _ in range(months):
        starts.append(date(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return starts[::-1]


def month_end(start):
    """The last day of the month that begins on `start`."""
    following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return following - timedelta(days=1)


def farm_analytics(farm_id, months=12, today=None):
    today = today or date.today()
    starts = month_starts(months, today)
    position = {(s.year, s.month): i for i, s in enumerate(starts)}

    def slot(day):
        """Which month of the chart a date falls in, or None if it's outside the period."""
        return position.get((day.year, day.month)) if day else None

    animals = Livestock.query.filter_by(farmer_id=farm_id).all()
    ids = [a.animal_id for a in animals]
    deaths = MortalityRecord.query.filter(MortalityRecord.animal_id.in_(ids)).all()
    sales = (CommercialInfo.query.filter(CommercialInfo.animal_id.in_(ids), CommercialInfo.transaction_type == "SELL")
             .order_by(CommercialInfo.date).all())
    illnesses = (HealthRecord.query.join(HealthRecord.animal)
                 .filter(Livestock.farmer_id == farm_id, HealthRecord.record_type == "ILLNESS").all())

    # The day each animal left the farm: its death, or its (first) sale.
    left = {d.animal_id: d.date_of_death for d in deaths}
    for sale in sales:
        left.setdefault(sale.animal_id, sale.date)

    # Herd size at the end of each month (this month: today).
    ends = [min(month_end(s), today) for s in starts]
    herd = {code: [0] * months for code, _ in SPECIES}
    for animal in animals:
        if animal.species not in herd:
            continue
        gone = left.get(animal.animal_id)
        for i, end in enumerate(ends):
            born = animal.date_of_birth is None or animal.date_of_birth <= end
            if born and (gone is None or gone > end):
                herd[animal.species][i] += 1

    born = [0] * months
    for animal in animals:
        i = slot(animal.date_of_birth) if animal.b_record_id else None    # born on the farm
        if i is not None:
            born[i] += 1

    died = [0] * months
    causes = Counter()
    for death in deaths:
        i = slot(death.date_of_death)
        if i is not None:
            died[i] += 1
            causes[death.cause_of_death or "Not recorded"] += 1

    sold, income = [0] * months, [0] * months
    seen = set()
    for sale in sales:
        i = slot(sale.date)
        if i is not None and sale.animal_id not in seen:
            seen.add(sale.animal_id)
            sold[i] += 1
            income[i] += sale.amount

    ill = {code: [0] * months for code, _ in SPECIES}
    for record in illnesses:
        i = slot(record.date)
        if i is not None and record.animal.species in ill:
            ill[record.animal.species][i] += 1

    top = causes.most_common(TOP_CAUSES)
    other = sum(causes.values()) - sum(n for _, n in top)
    if other:
        top.append(("Other", other))

    return {
        "months": [f"{s:%b %Y}" for s in starts],
        "species": [{"code": code, "name": name, "herd": herd[code], "ill": ill[code]} for code, name in SPECIES],
        "born": born, "died": died, "sold": sold, "income": income,
        "causes": [{"cause": cause, "count": n} for cause, n in top],
        "totals": {"born": sum(born), "died": sum(died), "sold": sum(sold), "income": sum(income),
                   "ill": sum(sum(v) for v in ill.values())},
    }