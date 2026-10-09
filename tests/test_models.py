"""Tests for the database models: tables, calculated values, links between tables."""
from datetime import date

from app.extensions import db
from app.models import BreedingRecord, Farmer, HealthRecord, Livestock, User, WeightRecord, Worker
from app.models.user import load_user


def make_farmer(email="f@example.com"):
    """Save a farmer directly in the database (no web form needed)."""
    user = User(name="Farmer", email=email, password_hash="not-a-real-hash")
    db.session.add(user)
    db.session.flush()
    farmer = Farmer(user_id=user.id)
    db.session.add(farmer)
    db.session.flush()
    return farmer


def test_all_ten_tables_exist(app_ctx):
    expected = {
        "users", "farmers", "workers", "livestock", "weight_records", "health_records",
        "breeding_record", "production_data", "commercial_info", "mortality_records",
    }
    assert expected == set(db.metadata.tables)


def test_age_is_calculated_from_date_of_birth(app_ctx):
    # These animals are never saved, so they don't need a tag number.
    today = date.today()
    animal = Livestock(species="GOAT", gender="FEMALE", date_of_birth=date(today.year - 3, 1, 1))
    assert animal.age == 3
    # No date of birth: age is unknown, not 0.
    assert Livestock(species="GOAT", gender="MALE").age is None


def test_age_counts_a_birthday_not_yet_reached_this_year(app_ctx):
    # Born on 31 December two years ago: until this year's 31 December,
    # the animal is still only 1.
    today = date.today()
    born_on_new_years_eve = date(today.year - 2, 12, 31)
    animal = Livestock(species="SHEEP", gender="MALE", date_of_birth=born_on_new_years_eve)
    expected = 2 if (today.month, today.day) >= (12, 31) else 1
    assert animal.age == expected


def test_deleting_an_animal_deletes_its_records(app_ctx):
    farmer = make_farmer()
    cow = Livestock(farmer_id=farmer.farmer_id, tag_number="C001", species="CATTLE", gender="FEMALE")
    db.session.add(cow)
    db.session.flush()
    db.session.add_all([
        WeightRecord(animal_id=cow.animal_id, date=date(2026, 9, 1), weight=300),
        HealthRecord(animal_id=cow.animal_id, date=date(2026, 9, 2), record_type="CHECKUP"),
    ])
    db.session.commit()

    db.session.delete(cow)
    db.session.commit()

    # cascade="all, delete-orphan" removed the records too.
    assert WeightRecord.query.count() == 0
    assert HealthRecord.query.count() == 0


def test_num_born_alive_counts_registered_offspring(app_ctx):
    farmer = make_farmer()
    dam = Livestock(farmer_id=farmer.farmer_id, tag_number="G001", species="GOAT", gender="FEMALE")
    db.session.add(dam)
    db.session.flush()
    birth = BreedingRecord(animal_id=dam.animal_id, status="SUCCESSFUL BIRTH", num_stillborn=1)
    db.session.add(birth)
    db.session.flush()
    for tag, gender in (("G002", "MALE"), ("G003", "FEMALE")):
        db.session.add(Livestock(farmer_id=farmer.farmer_id, tag_number=tag, species="GOAT", gender=gender,
                                 b_record_id=birth.b_record_id))
    db.session.commit()

    assert birth.num_born_alive == 2
    # The circular link works both ways: a kid -> its birth -> its mother.
    assert birth.offspring[0].birth_event.dam is dam


def test_load_user_reads_the_role_prefix(app_ctx):
    farmer = make_farmer()
    worker_user = User(name="Worker", email="w@example.com", password_hash="x")
    db.session.add(worker_user)
    db.session.flush()
    worker = Worker(user_id=worker_user.id, farmer_id=farmer.farmer_id)
    db.session.add(worker)
    db.session.commit()

    assert load_user(f"farmer:{farmer.farmer_id}") == farmer
    assert load_user(f"worker:{worker.worker_id}") == worker
    # Anything unknown or damaged means "not logged in", never a crash.
    assert load_user("worker:999") is None
    assert load_user("admin:1") is None
    assert load_user("garbage") is None