"""The farm's weather, from Open-Meteo (https://open-meteo.com).

One request gives everything the app shows and the model needs, for the
farm's own latitude and longitude:
- the weather now (temperature, humidity, rain, wind), updated about every 15 minutes;
- the daily rain of the last 60 days, for the model's "rain in the last 30
  days" and "30 to 60 days ago" clues;
- the daily forecast of the next 16 days (rain, chance of rain, temperatures).

Open-Meteo is free for non-commercial use and needs no key or account.
Answers are kept for 30 minutes per location, so pages load quickly and the
app stays far below the service's limit of 10,000 requests a day.

If the service can't be reached (no internet, a timeout), get_weather()
returns None and the pages carry on without it: the alerts are then
worked out without the rain (the model was trained to cope with that).
"""
import json
import time
from datetime import date, datetime
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import current_app

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 60
FORECAST_DAYS = 16
KEEP_SECONDS = 30 * 60        # how long an answer is reused
TIMEOUT_SECONDS = 6           # give up rather than leave the page hanging

# Open-Meteo describes the sky with WMO weather codes; these are the words
# the farmer sees.
WEATHER_WORDS = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}

_kept = {}    # (latitude, longitude) rounded -> (time fetched, weather)


def fetch_json(latitude, longitude):
    """Ask Open-Meteo for one location. Kept separate so tests can replace it."""
    query = urlencode({
        "latitude": latitude, "longitude": longitude, "timezone": "auto",
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,weather_code",
        "past_days": PAST_DAYS, "forecast_days": FORECAST_DAYS,
    })
    with urlopen(f"{FORECAST_URL}?{query}", timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def read_answer(answer):
    """Open-Meteo's answer, in the shape the app uses."""
    now = answer["current"]
    daily = answer["daily"]
    days = []
    for i, day in enumerate(daily["time"]):
        days.append({
            "date": date.fromisoformat(day),
            "rain": daily["precipitation_sum"][i] or 0.0,
            "rain_chance": (daily.get("precipitation_probability_max") or [None] * len(daily["time"]))[i],
            "high": daily["temperature_2m_max"][i],
            "low": daily["temperature_2m_min"][i],
            "words": WEATHER_WORDS.get(daily["weather_code"][i], ""),
        })
    today = date.fromisoformat(now["time"][:10])
    return {
        "now": {"time": datetime.fromisoformat(now["time"]), "temperature": now["temperature_2m"],
                "humidity": now["relative_humidity_2m"], "rain": now["precipitation"],
                "wind": now["wind_speed_10m"], "words": WEATHER_WORDS.get(now["weather_code"], "")},
        "today": today,
        "past": [d for d in days if d["date"] < today],
        "forecast": [d for d in days if d["date"] >= today],
    }


def get_weather(latitude, longitude):
    """The weather for a location, or None if it can't be had right now."""
    if not current_app.config.get("WEATHER_ENABLED", True):
        return None
    key = (round(latitude, 2), round(longitude, 2))
    kept = _kept.get(key)
    if kept and time.time() - kept[0] < KEEP_SECONDS:
        return kept[1]
    try:
        weather = read_answer(fetch_json(*key))
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
        current_app.logger.warning("Weather unavailable for %s: %s", key, error)
        return kept[1] if kept else None          # an older answer beats none
    _kept[key] = (time.time(), weather)
    return weather


def rain_table(weather):
    """Daily rain, observed then forecast, as the model's prepare() reads it."""
    import pandas as pd       # only when the alerts need it, so other pages start quickly
    days = weather["past"] + weather["forecast"]
    return pd.DataFrame({"date": [d["date"] for d in days], "rain_mm": [d["rain"] for d in days]})


def totals(weather):
    """The rain totals the alerts page explains: last 30 days, next 7 and 16 days."""
    past, ahead = weather["past"], weather["forecast"]
    return {"last_30_days": round(sum(d["rain"] for d in past[-30:]), 1),
            "next_7_days": round(sum(d["rain"] for d in ahead[:7]), 1),
            "next_16_days": round(sum(d["rain"] for d in ahead[:16]), 1)}