"""Simulating goats for one year, one day at a time."""
from datetime import date, timedelta

import numpy as np

from ml.reference import ILLNESS_RECOVERY_DAYS, LONG_RAINS, RAINS_MULTIPLIER, SHORT_RAINS, YEARLY_CHANCE

YEARLY = YEARLY_CHANCE["common"]                   # 20% a year, e.g. pneumonia in goats
DAILY = 1 - (1 - YEARLY) ** (1 / 365)              # the daily chance from lesson S1
START = date(2026, 1, 1)


def chance_today(day):
    """The daily chance, made bigger in the rainy months."""
    if day.month in LONG_RAINS:
        return DAILY * RAINS_MULTIPLIER["long"]
    if day.month in SHORT_RAINS:
        return DAILY * RAINS_MULTIPLIER["short"]
    return DAILY


def one_year(rng):
    """One goat's year: the days it fell ill."""
    ill_days = []
    for i in range(365):
        day = START + timedelta(days=i)
        # A goat that fell ill recently is still recovering, so it can't fall ill again yet.
        if ill_days and (day - ill_days[-1]).days < ILLNESS_RECOVERY_DAYS:
            continue
        if rng.random() < chance_today(day):
            ill_days.append(day)
    return ill_days


rng = np.random.default_rng(42)

print("One goat:", one_year(rng))

illnesses_by_month = [0] * 12
for goat in range(1000):
    for day in one_year(rng):
        illnesses_by_month[day.month - 1] += 1

print("\n1,000 goats, illnesses per month:")
for month, count in enumerate(illnesses_by_month, start=1):
    rains = "  rains" if month in LONG_RAINS + SHORT_RAINS else ""
    print(f"  {date(2026, month, 1):%b}  {count:3}  {'#' * (count // 2)}{rains}")
print("Total:", sum(illnesses_by_month))