"""Tests for tag-number suggestions, tag uniqueness and farm scoping."""
import pytest
from flask_login import login_user
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound

from app.extensions import db
from app.farm import get_farm_animal_or_404, suggest_tag_number
from app.models import Farmer, Livestock, User, Worker


def make_farmer(email):
    user = User(name=email, email=email, password_hash="x")
    db.session.add(user)
    db.session.flush()
    farmer = Farmer(user_id=user.id)
    db.session.add(farmer)
    db.session.flush()
    return farmer


def add_animal(farmer, tag, species="GOAT"):
    animal = Livestock(farmer_id=farmer.farmer_id, tag_number=tag, species=species, gender="FEMALE")
    db.session.add(animal)
    db.session.flush()
    return animal


def test_first_suggestion_for_each_species(app_ctx):
    farmer = make_farmer("a@example.com")
    assert suggest_tag_number(farmer.farmer_id, "CATTLE") == "C001"
    assert suggest_tag_number(farmer.farmer_id, "CHICKEN") == "CH001"
    assert suggest_tag_number(farmer.farmer_id, "GOAT") == "G001"
    assert suggest_tag_number(farmer.farmer_id, "SHEEP") == "S001"


def test_suggestion_follows_the_highest_number_and_ignores_other_tags(app_ctx):
    farmer = make_farmer("a@example.com")
    add_animal(farmer, "G001")
    add_animal(farmer, "G007")                       # a gap: the next is G008, not G002
    add_animal(farmer, "EAR-TAG-55")                 # farmer's own style: ignored
    add_animal(farmer, "C010", species="CATTLE")
    add_animal(farmer, "CH020", species="CHICKEN")   # must not confuse the cattle "C" pattern

    assert suggest_tag_number(farmer.farmer_id, "GOAT") == "G008"
    assert suggest_tag_number(farmer.farmer_id, "CATTLE") == "C011"
    assert suggest_tag_number(farmer.farmer_id, "CHICKEN") == "CH021"


def test_suggestions_are_per_farm(app_ctx):
    farm_a, farm_b = make_farmer("a@example.com"), make_farmer("b@example.com")
    add_animal(farm_a, "G005")
    assert suggest_tag_number(farm_b.farmer_id, "GOAT") == "G001"   # farm A's goats don't count


def test_tag_must_be_unique_within_a_farm(app_ctx):
    farmer = make_farmer("a@example.com")
    add_animal(farmer, "G001")
    # pytest.raises: this block MUST raise IntegrityError, or the test fails.
    with pytest.raises(IntegrityError):
        add_animal(farmer, "G001")


def test_two_farms_may_use_the_same_tag(app_ctx):
    farm_a, farm_b = make_farmer("a@example.com"), make_farmer("b@example.com")
    add_animal(farm_a, "G001")
    add_animal(farm_b, "G001")
    db.session.commit()
    assert Livestock.query.filter_by(tag_number="G001").count() == 2


def test_animals_from_another_farm_are_not_found(app):
    with app.app_context():
        farm_a, farm_b = make_farmer("a@example.com"), make_farmer("b@example.com")
        mine = add_animal(farm_a, "G001")
        theirs = add_animal(farm_b, "G001")
        worker_user = User(name="W", email="w@example.com", password_hash="x")
        db.session.add(worker_user)
        db.session.flush()
        worker = Worker(user_id=worker_user.id, farmer_id=farm_a.farmer_id)
        db.session.add(worker)
        db.session.commit()
        mine_id, theirs_id, farmer_a_id, worker_id = mine.animal_id, theirs.animal_id, farm_a.farmer_id, worker.worker_id

    # Check as farm A's farmer AND as farm A's worker.
    for account_type, account_id in ((Farmer, farmer_a_id), (Worker, worker_id)):
        # test_request_context(): a pretend request, so login_user/current_user work.
        with app.test_request_context():
            login_user(db.session.get(account_type, account_id))
            assert get_farm_animal_or_404(mine_id).animal_id == mine_id
            with pytest.raises(NotFound):
                get_farm_animal_or_404(theirs_id)    # another farm's animal: 404
            with pytest.raises(NotFound):
                get_farm_animal_or_404(99999)        # doesn't exist: the same 404