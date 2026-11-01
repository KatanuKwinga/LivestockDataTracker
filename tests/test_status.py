"""The farmer's dashboard: the six farm statuses the farm asked for, and
the pages behind them."""
from datetime import date, timedelta

from app import status
from app.extensions import db
from app.models import BreedingRecord, HealthRecord, HerdActivity, Livestock
from tests.conftest import login, register_farmer
from tests.test_herd import bury, sell
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker, medicine
from tests.test_records_general import add_animal, farm_id_of, farmer_logged_in

TODAY = date.today()


def days_ago(n):
    return TODAY - timedelta(days=n)


def statuses(app):
    with app.app_context():
        return status.all_statuses(farm_id_of())


def add_health(app, animal_id, days, record_type="ILLNESS", disease="East Coast Fever", treatment=None):
    with app.app_context():
        db.session.add(HealthRecord(animal_id=animal_id, date=days_ago(days), record_type=record_type,
                                    disease=disease, treatment=treatment))
        db.session.commit()


def add_pregnancy(app, dam_id, due_in_days, status_="EXPECTANT"):
    with app.app_context():
        db.session.add(BreedingRecord(animal_id=dam_id, status=status_,
                                      expected_delivery_date=TODAY + timedelta(days=due_in_days)))
        db.session.commit()


# ------------------------------------------------------------------ the page

def test_the_farmer_sees_six_statuses_and_workers_do_not(client):
    farm_with_worker(client)
    as_farmer(client)
    page = client.get("/dashboard").data
    for label in (b">Animals<", b">Health<", b">Condition<", b">Market<", b">Pharmacy<", b">Health outlook<"):
        assert label in page
    as_worker(client)
    assert b"status-grid" not in client.get("/dashboard").data


def test_status_pages_are_for_farmers_only(client):
    farm_with_worker(client)
    as_worker(client)
    assert client.get("/status/health").headers["Location"].endswith("/dashboard")
    as_farmer(client)
    for key in ("health", "condition", "market", "outlook"):
        assert client.get(f"/status/{key}").status_code == 200
    assert client.get("/status/nonsense").status_code == 404


# --------------------------------------------------------------- 1. animals

def test_cattle_are_counted_in_the_farms_groups(app, client):
    farmer_logged_in(client)
    add_animal(app, "C001", species="CATTLE", date_of_birth=TODAY - timedelta(days=150))          # calf
    add_animal(app, "C002", species="CATTLE", date_of_birth=TODAY - timedelta(days=800))          # heifer
    cow = add_animal(app, "C003", species="CATTLE", date_of_birth=TODAY - timedelta(days=1500))   # has calved
    add_animal(app, "C004", species="CATTLE", gender="MALE", date_of_birth=TODAY - timedelta(days=1200))  # bull
    add_animal(app, "C005", species="CATTLE")                                                    # age unknown: grown
    gone = add_animal(app, "C006", species="CATTLE")
    bury(app, gone)
    add_animal(app, "G001")
    add_pregnancy(app, cow, -30, status_="SUCCESSFUL BIRTH")

    animals = statuses(app)["animals"]
    assert animals["total"] == 6
    assert animals["cattle"] == {"Calves": 1, "Heifers": 2, "Cows": 1, "Steers": 0, "Bulls": 1}    
    assert animals["others"] == {"GOAT": 1}
    page = client.get("/dashboard").data
    assert b"Cattle: 1 calf \xc2\xb7 2 heifers \xc2\xb7 1 cow \xc2\xb7 1 bull" in page and b"1 goat" in page


# ---------------------------------------------------------------- 2. health

def test_an_animal_ill_in_the_last_two_weeks_raises_an_alert(app, client):
    farmer_logged_in(client)
    sick, recovered = add_animal(app, "C001", species="CATTLE"), add_animal(app, "C002", species="CATTLE")
    add_health(app, sick, 3, treatment="Butalex")
    add_health(app, recovered, 20)                         # too long ago to count

    with app.app_context():
        health = status.unwell(farm_id_of())
        assert health["state"] == "Alert" and [r.animal.tag_number for r in health["records"]] == ["C001"]
    assert b"1 unwell: C001" in client.get("/dashboard").data
    page = client.get("/status/health").data
    assert b"C001" in page and b"East Coast Fever" in page and b"Butalex" in page and b"C002" not in page


def test_health_is_ok_with_no_recent_illness(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    add_health(app, goat, 1, record_type="CHECKUP", disease=None)    # a check-up isn't an illness
    dead = add_animal(app, "G002")
    add_health(app, dead, 2)
    bury(app, dead)                                                  # only animals still on the farm count
    assert statuses(app)["health"]["state"] == "OK"


# ------------------------------------------------------------- 3. condition

def test_pregnant_animals_soonest_due_first(app, client):
    farmer_logged_in(client)
    late, soon, later = (add_animal(app, t, species="CATTLE") for t in ("C001", "C002", "C003"))
    add_pregnancy(app, later, 60)
    add_pregnancy(app, soon, 10)
    add_pregnancy(app, late, -3)                           # overdue

    with app.app_context():
        condition = status.pregnant(farm_id_of())
        assert condition["state"] == "3 pregnant" and condition["tone"] == "warn"
        assert [r["event"].dam.tag_number for r in condition["rows"]] == ["C001", "C002", "C003"]
    assert b"Next due: C001, overdue by 3 days" in client.get("/dashboard").data
    page = client.get("/status/condition").data.decode()
    assert page.index("C001") < page.index("C002") < page.index("C003")


def test_no_pregnancies(app, client):
    farmer_logged_in(client)
    assert statuses(app)["condition"]["state"] == "None"


# ---------------------------------------------------------------- 4. market

def test_the_farmer_marks_animals_to_sell_or_cull(app, client):
    farmer_logged_in(client)
    first, second = add_animal(app, "G001"), add_animal(app, "G002")
    assert b"Mark to sell" in client.get(f"/herd/{first}").data
    client.post(f"/herd/{first}/market", data={"market": "SELL"})
    client.post(f"/herd/{second}/market", data={"market": "CULL"})

    market = statuses(app)["market"]
    assert (market["state"], market["sell"], market["cull"]) == ("Available", 1, 1)
    assert b"1 to sell \xc2\xb7 1 to cull" in client.get("/dashboard").data
    assert b"G001" in client.get("/status/market").data

    client.post(f"/herd/{first}/market", data={"market": ""})        # take it off the list
    client.post(f"/herd/{second}/market", data={"market": ""})
    assert statuses(app)["market"]["state"] == "None"


def test_odd_market_values_are_ignored_and_gone_animals_drop_off(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    client.post(f"/herd/{goat}/market", data={"market": "STEAL"})
    with app.app_context():
        assert db.session.get(Livestock, goat).market_status is None
    client.post(f"/herd/{goat}/market", data={"market": "SELL"})
    sell(app, goat)                                                  # once sold, it leaves the list
    assert statuses(app)["market"]["state"] == "None"


def test_only_the_farmer_marks_and_only_their_own_animals(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G900", email="other@example.com")
    farm_with_worker(client)
    as_farmer(client)
    assert client.post(f"/herd/{theirs}/market", data={"market": "SELL"}).status_code == 404
    goat = add_animal(app, "G001")
    as_worker(client)
    assert client.post(f"/herd/{goat}/market", data={"market": "SELL"}).headers["Location"].endswith("/dashboard")
    assert b"Mark to sell" not in client.get(f"/herd/{goat}").data
    with app.app_context():
        assert db.session.get(Livestock, goat).market_status is None


# -------------------------------------------------------------- 5. pharmacy

def test_pharmacy_is_low_when_a_medicine_reaches_its_reorder_level(app, client):
    farm_with_worker(client)
    as_farmer(client)
    assert statuses(app)["pharmacy"]["state"] == "OK"
    client.post("/pharmacy/new", data=medicine(name="Butalex", quantity="200", reorder_level="50"))
    client.post("/pharmacy/new", data=medicine(name="Dominex", quantity="40", reorder_level="300"))
    client.post("/pharmacy/new", data=medicine(name="Almatix", quantity="0", reorder_level="100"))

    pharmacy = statuses(app)["pharmacy"]
    assert (pharmacy["state"], pharmacy["tone"]) == ("Low", "bad")
    tile = client.get("/dashboard").data.split(b'class="label">Pharmacy<')[1].split(b"</a>")[0]
    assert b"Out: Almatix" in tile and b"Low: Dominex" in tile and b"Butalex" not in tile


# --------------------------------------------------------------- 6. outlook

def deworm(app, species, days):
    with app.app_context():
        db.session.add(HerdActivity(farmer_id=farm_id_of(), species=species, date=days_ago(days),
                                    activity="DEWORMING", product="Nilzan"))
        db.session.commit()


def vaccinate(app, animal_id, vaccine, days):
    with app.app_context():
        db.session.add(HealthRecord(animal_id=animal_id, date=days_ago(days), record_type="VACCINATION", treatment=vaccine))
        db.session.commit()


def test_routines_never_done_are_due_now(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    outlook = statuses(app)["outlook"]
    # Goats: deworming, and the farm plan's goat vaccines (CCPP and FMD).
    assert {(r["name"], r["days"]) for r in outlook["rows"]} == {
        ("Deworming", 0), ("CCPP vaccine", 0), ("FMD vaccine", 0)}
    assert outlook["state"] == "Alert"
    assert b"due today" in client.get("/dashboard").data


def test_outlook_is_ok_when_nothing_is_due_within_a_month(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    deworm(app, "GOAT", 10)                                  # next in 80 days
    vaccinate(app, goat, "CCPP vaccine", 10)                 # next in 172 days: beyond 3 months
    vaccinate(app, goat, "FMD vaccine", 100)                 # next in 82 days

    outlook = statuses(app)["outlook"]
    assert outlook["state"] == "OK"
    assert [(r["name"], r["days"]) for r in outlook["rows"]] == [("Deworming", 80), ("FMD vaccine", 82)]
    assert b"Next: Deworming (goats), in 80 days" in client.get("/dashboard").data


def test_a_routine_due_within_a_month_is_an_alert(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    deworm(app, "GOAT", 80)                                  # due in 10 days
    vaccinate(app, goat, "CCPP vaccine", 10)
    vaccinate(app, goat, "FMD vaccine", 10)
    outlook = statuses(app)["outlook"]
    assert outlook["state"] == "Alert" and [r["name"] for r in outlook["soon"]] == ["Deworming"]
    page = client.get("/status/outlook").data
    assert b"Deworming" in page and b"in 10 days" in page


def test_another_farms_records_do_not_count(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    login(client, "farmer", email="other@example.com")
    theirs = add_animal(app, "C900", species="CATTLE", email="other@example.com")
    add_health(app, theirs, 1)
    client.post(f"/herd/{theirs}/market", data={"market": "SELL"})
    client.post("/auth/logout")
    farmer_logged_in(client)
    s = statuses(app)
    assert (s["animals"]["total"], s["health"]["state"], s["market"]["state"]) == (0, "OK", "None")