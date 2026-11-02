"""The farmer's Analytics page: the numbers behind each chart."""
from datetime import date

from app.analytics import farm_analytics, month_starts
from app.extensions import db
from app.models import BreedingRecord, CommercialInfo, HealthRecord, Livestock, MortalityRecord
from tests.conftest import register_farmer
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal, farm_id_of

TODAY = date(2026, 11, 2)


def test_the_last_twelve_months_end_with_this_month():
    starts = month_starts(12, TODAY)
    assert starts[0] == date(2025, 12, 1) and starts[-1] == date(2026, 11, 1) and len(starts) == 12


def test_each_chart_counts_the_right_records(app, client):
    register_farmer(client)
    register_farmer(client, name="Other Farmer", email="other@example.com")
    cow = add_animal(app, "C001", species="CATTLE", date_of_birth=date(2020, 1, 1))
    bull = add_animal(app, "C002", species="CATTLE", gender="MALE", date_of_birth=date(2020, 1, 1))
    goat = add_animal(app, "G001", date_of_birth=date(2022, 1, 1))
    add_animal(app, "G900", email="other@example.com", date_of_birth=date(2022, 1, 1))   # not this farm
    with app.app_context():
        birth = BreedingRecord(animal_id=cow, status="SUCCESSFUL BIRTH", actual_delivery_date=date(2026, 3, 10))
        db.session.add(birth)
        db.session.flush()
        db.session.add(Livestock(farmer_id=farm_id_of(), tag_number="C003", species="CATTLE", gender="FEMALE",
                                 date_of_birth=date(2026, 3, 10), b_record_id=birth.b_record_id))
        db.session.add(CommercialInfo(animal_id=bull, transaction_type="SELL", date=date(2026, 6, 30), amount=100000))
        db.session.add(MortalityRecord(animal_id=goat, date_of_death=date(2026, 8, 3), cause_of_death="Lung problem"))
        db.session.add(HealthRecord(animal_id=goat, date=date(2026, 7, 29), record_type="ILLNESS", disease="Pneumonia"))
        db.session.add(HealthRecord(animal_id=goat, date=date(2026, 7, 30), record_type="TREATMENT", disease="Pneumonia"))
        db.session.commit()
        data = farm_analytics(farm_id_of(), months=12, today=TODAY)

    month = {m: i for i, m in enumerate(data["months"])}
    assert data["born"][month["Mar 2026"]] == 1 and data["totals"]["born"] == 1
    assert data["sold"][month["Jun 2026"]] == 1 and data["totals"]["income"] == 100000
    assert data["died"][month["Aug 2026"]] == 1
    assert data["causes"] == [{"cause": "Lung problem", "count": 1}]
    goats = next(s for s in data["species"] if s["code"] == "GOAT")
    assert goats["ill"][month["Jul 2026"]] == 1 and data["totals"]["ill"] == 1     # the treatment isn't a new illness
    cattle = next(s for s in data["species"] if s["code"] == "CATTLE")
    assert cattle["herd"][month["Feb 2026"]] == 2           # cow and bull
    assert cattle["herd"][month["Mar 2026"]] == 3           # + the calf
    assert cattle["herd"][month["Jun 2026"]] == 2           # the bull sold on 30 June
    assert goats["herd"][month["Aug 2026"]] == 0            # the goat died; the other farm's goat never counts


def test_farmers_see_analytics_and_workers_do_not(client):
    farm_with_worker(client)
    as_farmer(client)
    page = client.get("/analytics/").data.decode()
    assert "A Farm Analysis" in page and "Herd size" in page and 'id="analyticsData"' in page    assert ">Analytics<" in client.get("/dashboard").data.decode()
    assert len(client.get("/analytics/?months=24").data) > len(page)      # 24 months of table rows
    as_worker(client)
    assert client.get("/analytics/").headers["Location"].endswith("/dashboard")
    assert ">Analytics<" not in client.get("/dashboard").data.decode()