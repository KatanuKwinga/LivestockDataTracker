"""Rainfall: what drives most seasonal livestock disease around Thika.

The model doesn't use the calendar ("it's April, so it's the rains"). It
uses the rain itself: how much fell in the last 30 days, in the 30 days
before that, and how much is forecast for the next 16 days. A wet year,
a dry year, El Nino or a late start to the rains all show up in those
numbers, and a farm somewhere else in Kenya can be judged by its own rain.

Two sources give the same kind of numbers:
- training: Thika's real daily rainfall since 1981 (ml/climate/thika_rainfall.csv,
  downloaded from Open-Meteo's historical weather archive);
- the app: the farm's own rainfall and forecast from Open-Meteo (app/weather.py),
  for the location the farmer sets. With no location, or no answer from the
  service, the rain is left unknown and the model works without it.
"""
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

THIKA_FILE = Path(__file__).parent / "climate" / "thika_rainfall.csv"

RECENT_DAYS = 30                # "rain in the last 30 days"
FORECAST_DAYS = 16              # Open-Meteo forecasts daily rain 16 days ahead
RAIN_FEATURES = ["rain_last_30_days", "rain_30_to_60_days_ago", "rain_next_16_days"]


@lru_cache(maxsize=1)
def thika_history():
    """Thika's daily rainfall (mm), indexed by date, 1981 to November 2026."""
    rain = pd.read_csv(THIKA_FILE, parse_dates=["date"])
    return rain.set_index("date")["rain_mm"]


@lru_cache(maxsize=1)
def monthly_normals():
    """The usual rainfall for each calendar month at Thika (mm), the
    average over 1981-2025. Used to explain the rain to the farmer
    in the training notebook."""
    rain = thika_history()
    rain = rain[rain.index < "2026-01-01"]
    by_month = rain.groupby([rain.index.year, rain.index.month]).sum()
    return by_month.groupby(level=1).mean().round(0).to_dict()


def thika_rain_table():
    """Thika's history as a table (date, rain_mm), the shape prepare() reads."""
    history = thika_history()
    return pd.DataFrame({"date": history.index, "rain_mm": history.to_numpy()})


def window(series, start, end):
    """Total rain (mm) with start <= date < end. Days missing from the
    series are left out, so callers make sure the days are there."""
    return float(series[(series.index >= start) & (series.index < end)].sum())


def rain_features(series, day):
    """The three rain clues for one snapshot day, from a daily series that
    covers the 60 days before it and the 16 days from it (observed rain in
    training; observed + forecast in the app)."""
    day = pd.Timestamp(day)
    return {
        "rain_last_30_days": window(series, day - timedelta(days=30), day),
        "rain_30_to_60_days_ago": window(series, day - timedelta(days=60), day - timedelta(days=30)),
        "rain_next_16_days": window(series, day, day + timedelta(days=FORECAST_DAYS)),
    }


def shifted_history(start, end, years_back):
    """Thika's real rainfall for the days start..end, but taken from
    `years_back` years earlier: a simulated farm running 2022-2026 can get
    the weather of, say, 1996-2000. 29 February borrows 28 February."""
    history = thika_history()
    days = pd.date_range(start, end)
    values = []
    for d in days:
        try:
            source = d.replace(year=d.year - years_back)
        except ValueError:                       # 29 Feb in a year without one
            source = d.replace(year=d.year - years_back, day=28)
        values.append(history.get(source, 0.0))
    return pd.Series(values, index=days, name="rain_mm")