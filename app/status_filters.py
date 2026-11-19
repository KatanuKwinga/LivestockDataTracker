"""Filters and a tag search for the pages behind the dashboard tiles:
Unwell animals, Pregnant animals and the Market list.

The filters only narrow the table on the page. The dashboard tile still
counts every animal, so "3 unwell" on the tile stays true whatever the
farmer filtered last.

The lists are short (the animals unwell in the last 14 days, the females
expecting, the animals marked for market), so they are filtered here in
Python after they're loaded, not with extra database queries.

Every value comes from the URL, so each one is checked against the
choices allowed: anything else is ignored, never trusted.
"""
from app.routes.records import SLUG_FOR, SPECIES_CHOICES

SEXES = {"female": "FEMALE", "male": "MALE"}
MARKS = {"sell": "SELL", "cull": "CULL"}

# Which filters each page offers. Every page also has the tag search.
FILTERS_FOR = {
    "health": ("species", "disease", "sex"),
    "condition": ("species",),
    "market": ("species", "sex", "mark"),
}


def read_filters(args, key, diseases=()):
    """The filters chosen in the URL (?species=goat&sex=female&q=G00),
    keeping only the ones this page offers and only allowed values."""
    offered = FILTERS_FOR.get(key, ())
    chosen = {"q": args.get("q", "").strip()[:30]}
    allowed = {"species": SPECIES_CHOICES, "sex": SEXES, "mark": MARKS, "disease": diseases}
    for name in offered:
        value = args.get(name, "")
        chosen[name] = value if value in allowed[name] else ""
    return chosen


def animal_matches(animal, chosen):
    """Does this animal pass the species, sex and tag search filters?"""
    species = SPECIES_CHOICES[chosen["species"]]["value"] if chosen.get("species") else None
    if species and animal.species != species:
        return False
    if chosen.get("sex") and animal.gender != SEXES[chosen["sex"]]:
        return False
    q = chosen.get("q", "").lower()
    return not q or q in animal.tag_number.lower()


def filter_page(key, s, args):
    """The rows to show on one status page, the filters chosen, and the
    choices for the drop-downs. Returns (rows, chosen, choices)."""
    if key == "health":
        # Only diseases someone is actually ill with: no empty choices.
        diseases = sorted({r.disease for r in s["records"] if r.disease})
        chosen = read_filters(args, key, diseases)
        rows = [r for r in s["records"] if animal_matches(r.animal, chosen)
                and (not chosen["disease"] or r.disease == chosen["disease"])]
        return rows, chosen, {"diseases": diseases, "species": species_here(r.animal for r in s["records"])}
    if key == "condition":
        chosen = read_filters(args, key)
        rows = [r for r in s["rows"] if animal_matches(r["event"].dam, chosen)]
        return rows, chosen, {"species": species_here(r["event"].dam for r in s["rows"])}
    if key == "market":
        chosen = read_filters(args, key)
        rows = [a for a in s["animals"] if animal_matches(a, chosen)
                and (not chosen["mark"] or a.market_status == MARKS[chosen["mark"]])]
        return rows, chosen, {"species": species_here(s["animals"])}
    return None, {}, {}


def species_here(animals):
    """The species drop-down: only species that appear in the list, in the
    usual order (cattle, chickens, goats, sheep)."""
    present = {SLUG_FOR[a.species] for a in animals}
    return {slug: choice for slug, choice in SPECIES_CHOICES.items() if slug in present}


def is_filtered(chosen):
    """True if the farmer chose any filter or typed a search."""
    return any(chosen.values())