"""The groups a farm's animals are split into for the disease alerts.

The model doesn't predict for single animals: it predicts for groups that
share the same risks, such as calves, cows that have just calved, or the
adult goats. Which group an animal is in depends on its species, its age,
and whether it gave birth in the last 60 days.
"""
from ml.reference import EARLY_LACTATION_DAYS, YOUNG_DAYS, predicted_conditions

NEVER = 10_000      # "no upper age limit", in days

# For each species, its groups and the age range (in days) each covers.
# "after_birth" groups hold females that gave birth in the last 60 days,
# whatever their age; the age groups hold everyone else.
GROUPS = {
    "CATTLE": {
        "Calves": {"ages": (0, YOUNG_DAYS)},                    # under 6 months
        "Young stock": {"ages": (YOUNG_DAYS, 730)},             # 6 months to 2 years
        "Cows after calving": {"ages": (730, NEVER), "after_birth": True},
        "Adult cattle": {"ages": (730, NEVER)},
    },
    "GOAT": {
        "Kids": {"ages": (0, YOUNG_DAYS)},
        "Does after kidding": {"ages": (365, NEVER), "after_birth": True},
        "Adult goats": {"ages": (YOUNG_DAYS, NEVER)},
    },
    "SHEEP": {
        "Lambs": {"ages": (0, YOUNG_DAYS)},
        "Ewes after lambing": {"ages": (365, NEVER), "after_birth": True},
        "Adult sheep": {"ages": (YOUNG_DAYS, NEVER)},
    },
    # Kwetu's chickens are an adult laying flock, kept and treated together.
    "CHICKEN": {
        "Flock": {"ages": (0, NEVER)},
    },
}
AFTER_BIRTH_GROUP_DAYS = EARLY_LACTATION_DAYS     # 60 days


def group_name(species, age_days, female, days_since_birth):
    """Which group an animal belongs to today."""
    groups = GROUPS[species]
    if female and days_since_birth is not None and 0 <= days_since_birth < AFTER_BIRTH_GROUP_DAYS:
        for name, info in groups.items():
            if info.get("after_birth"):
                return name
    for name, info in groups.items():
        low, high = info["ages"]
        if not info.get("after_birth") and low <= age_days < high:
            return name
    return list(groups)[-1]            # older than every range: the adult group


def applies(condition, species, group):
    """Can animals in this group get this disease? Checks the disease's
    age limits and whether it only follows giving birth."""
    info = GROUPS[species][group]
    if condition.after_birth and not info.get("after_birth"):
        return False
    low, high = info["ages"]
    disease_low = condition.min_age_days or 0
    disease_high = condition.max_age_days or NEVER
    return disease_low < high and low < disease_high      # the two age ranges overlap


def diseases_for(species, group):
    """The diseases the model predicts for one group."""
    return [c for c in predicted_conditions(species) if applies(c, species, group)]


def pairs():
    """Every (species, group, disease) the model makes a prediction for."""
    return [(species, group, c.name)
            for species, groups in GROUPS.items()
            for group in groups
            for c in diseases_for(species, group)]