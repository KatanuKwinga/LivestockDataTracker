"""The weather (app/weather.py) and the farm's location (Settings).

Tests never call the real weather service: fake_weather() builds an answer
in the same shape, and fetch_json is replaced when the reading is tested."""
from datetime import date, datetime, timedelta

import pytest

import app.routes.main as app_routes_main
import app.weather as weather_module
from app.extensions import db
from app.models import Farmer
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import farm_id_of, farmer_logged_in


def set_location(app, name="Kilima Farm, Nyeri", latitude=-0.42, longitude=36.95):
    """Give Jane's farm a location, as the Settings page would."""
    with app.app_context():
        farmer = db.session.get(Farmer, farm_id_of())
        farmer.location_name, farmer.latitude, farmer.longitude = name, latitude, longitude
        db.session.commit()

TODAY = date.today()


def fake_weather(past_mm=2.0, forecast_mm=3.0, today=TODAY):
    """A weather answer: 60 days at past_mm a day, then 16 at forecast_mm."""
    def day(d, mm):
        return {"date": d, "rain": mm, "rain_chance": 60, "high": 26.0, "low": 14.0, "words": "Light rain"}
    return {
        "now": {"time": datetime.combine(today, datetime.min.time()).replace(hour=9), "temperature": 21.4,
                "humidity": 78, "rain": 0.4, "wind": 9.0, "words": "Light rain"},
        "today": today,
        "past": [day(today - timedelta(days=i), past_mm) for i in range(60, 0, -1)],
        "forecast": [day(today + timedelta(days=i), forecast_mm) for i in range(16)],
    }


OPEN_METEO_ANSWER = {
    "current": {"time": "2026-11-18T09:15", "temperature_2m": 21.4, "relative_humidity_2m": 78,
                "precipitation": 0.4, "weather_code": 61, "wind_speed_10m": 9.0},
    "daily": {"time": ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"],
              "precipitation_sum": [12.5, None, 3.0, 20.1], "precipitation_probability_max": [80, 10, 55, 90],
              "temperature_2m_max": [24.0, 26.1, 25.0, 23.2], "temperature_2m_min": [14.0, 13.5, 14.2, 15.0],
              "weather_code": [63, 2, 61, 65]},
}


# ------------------------------------------------------------- the service

def test_open_meteos_answer_is_read_into_past_and_forecast():
    weather = weather_module.read_answer(OPEN_METEO_ANSWER)
    assert weather["today"] == date(2026, 11, 18)
    assert weather["now"]["words"] == "Light rain" and weather["now"]["temperature"] == 21.4
    assert [d["rain"] for d in weather["past"]] == [12.5, 0.0]           # a missing value counts as no rain
    assert [d["words"] for d in weather["forecast"]] == ["Light rain", "Heavy rain"]


def test_answers_are_kept_and_failures_return_none(app, monkeypatch):
    calls = []
    def fake_fetch(lat, lon):
        calls.append((lat, lon))
        return OPEN_METEO_ANSWER
    monkeypatch.setattr(weather_module, "fetch_json", fake_fetch)
    monkeypatch.setattr(weather_module, "_kept", {})
    app.config["WEATHER_ENABLED"] = True
    with app.app_context():
        assert weather_module.get_weather(-1.04, 37.07)["today"] == date(2026, 11, 18)
        weather_module.get_weather(-1.04, 37.07)
        assert len(calls) == 1                                  # the second page used the kept answer

        def broken(lat, lon):
            raise OSError("no internet")
        monkeypatch.setattr(weather_module, "fetch_json", broken)
        assert weather_module.get_weather(0.5, 35.3) is None      # nothing kept for that place: no weather


def test_tests_never_call_the_weather_service(app):
    with app.app_context():
        assert weather_module.get_weather(-1.04, 37.07) is None


def test_the_rain_totals():
    totals = weather_module.totals(fake_weather(past_mm=2.0, forecast_mm=3.0))
    assert totals == {"last_30_days": 60.0, "next_7_days": 21.0, "next_16_days": 48.0}


# ------------------------------------------------------------- the pages

def test_the_farmers_home_shows_the_weather(app, client, monkeypatch):
    farmer_logged_in(client)
    set_location(app)
    monkeypatch.setattr(app_routes_main, "get_weather", lambda lat, lon: fake_weather())
    page = client.get("/dashboard").data.decode()
    assert "21&deg;C" in page or "21°C" in page
    assert "Humidity 78%" in page and "Kilima Farm, Nyeri" in page


def test_without_the_service_the_home_page_still_loads(app, client):
    farmer_logged_in(client)
    set_location(app)
    page = client.get("/dashboard").data
    assert b"can't be reached right now" in page


def test_the_farmer_sets_the_farms_location(app, client, monkeypatch):
    farmer_logged_in(client)
    asked = []
    monkeypatch.setattr(app_routes_main, "get_weather", lambda lat, lon: asked.append((lat, lon)) or fake_weather())
    page = client.get("/dashboard").data
    assert asked == []                                          # no location: no weather asked for
    assert b"Set your farm&#39;s location to see its weather" in page or b"Set your farm's location to see its weather" in page

    page = client.post("/settings", data={"location_name": "Kilima Farm, Nyeri", "latitude": "-0.4201",
                                          "longitude": "36.9476"}, follow_redirects=True).data
    assert b"Farm location saved" in page
    with app.app_context():
        farmer = db.session.get(Farmer, farm_id_of())
        assert (farmer.location_name, farmer.latitude, farmer.longitude) == ("Kilima Farm, Nyeri", -0.4201, 36.9476)
    client.get("/dashboard")
    assert asked[-1] == (-0.4201, 36.9476)
    assert b"Kilima Farm, Nyeri" in client.get("/dashboard").data


@pytest.mark.parametrize("latitude, longitude, message", [
    ("", "36.9", b"Enter the latitude."),
    ("95", "36.9", b"Latitude is between -90 and 90."),
    ("-0.42", "200", b"Longitude is between -180 and 180."),
])
def test_the_location_is_checked(client, latitude, longitude, message):
    farmer_logged_in(client)
    page = client.post("/settings", data={"location_name": "Farm", "latitude": latitude, "longitude": longitude}).data
    assert message in page


def test_workers_cannot_change_the_location(client):
    farm_with_worker(client)
    as_worker(client)
    assert client.get("/settings").headers["Location"].endswith("/dashboard")
    as_farmer(client)
    assert client.get("/settings").status_code == 200