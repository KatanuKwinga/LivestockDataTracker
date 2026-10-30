"""Health records and group treatments taking medicine from the pharmacy,
so a treatment is recorded once and the stock goes down by itself."""
from app.extensions import db
from app.models import HealthRecord, HerdActivity, PharmacyItem, StockMovement
from tests.conftest import login, register_farmer
from tests.test_group import session_data
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker, medicine
from tests.test_records_general import add_animal
from tests.test_records_health import illness


def pharmacy_with(client, *medicines):
    """Jane's farm (with Wanjiru) and these medicines. Jane is logged in."""
    farm_with_worker(client)
    as_farmer(client)
    for data in medicines:
        client.post("/pharmacy/new", data=data)


def item(app, name):
    with app.app_context():
        return db.session.get(PharmacyItem, PharmacyItem.query.filter_by(name=name).one().item_id)


def item_id(app, name):
    with app.app_context():
        return PharmacyItem.query.filter_by(name=name).one().item_id


def uses(app):
    """(medicine, amount, animal tag, reason, checked, linked to health?, linked to session?) per use."""
    with app.app_context():
        return [(m.item.name, m.amount, m.animal.tag_number if m.animal else None, m.remarks, m.checked,
                 m.health_record_id is not None, m.activity_id is not None)
                for m in StockMovement.query.filter_by(kind="USED").order_by(StockMovement.movement_id)]


# ------------------------------------------------------------ health records

def test_a_health_record_can_take_medicine_from_the_pharmacy(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%"))
    goat = add_animal(app, "G001")
    page = client.get(f"/records/add/goat/health/{goat}").data
    assert b"From the pharmacy" in page and b"Tylosin 20% (100 ml left)" in page

    tylosin = item_id(app, "Tylosin 20%")
    client.post(f"/records/add/goat/health/{goat}",
                data=illness(treatment="", dosage="", medicine=str(tylosin), medicine_amount="8"))

    assert item(app, "Tylosin 20%").quantity == 92
    assert uses(app) == [("Tylosin 20%", 8, "G001", "Pneumonia", True, True, False)]
    with app.app_context():
        record = HealthRecord.query.one()
        # An empty Medicine given / Dose box is filled from the pharmacy.
        assert (record.disease, record.treatment, record.dosage) == ("Pneumonia", "Tylosin 20%", "8 ml")
        assert StockMovement.query.filter_by(kind="USED").one().health_record_id == record.h_record_id


def test_a_health_record_without_pharmacy_medicine_changes_no_stock(app, client):
    pharmacy_with(client, medicine())
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/health/{goat}", data=illness(medicine="", medicine_amount=""))
    assert uses(app) == [] and item(app, "Tylosin 20%").quantity == 100
    with app.app_context():
        assert HealthRecord.query.count() == 1


def test_the_amount_is_checked_and_nothing_is_saved_if_wrong(app, client):
    pharmacy_with(client, medicine())
    goat = add_animal(app, "G001")
    tylosin = str(item_id(app, "Tylosin 20%"))
    url = f"/records/add/goat/health/{goat}"
    assert b"Enter how much was used" in client.post(url, data=illness(medicine=tylosin, medicine_amount="")).data
    assert b"Only 100 ml in stock" in client.post(url, data=illness(medicine=tylosin, medicine_amount="150")).data
    with app.app_context():
        assert HealthRecord.query.count() == 0
    assert item(app, "Tylosin 20%").quantity == 100


def test_a_follow_up_can_name_the_medicine_by_picking_it(app, client):
    # "Medicine given" is needed for a follow-up treatment, unless it is
    # picked from the pharmacy instead.
    pharmacy_with(client, medicine())
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/health/{goat}",
                data=illness(record_type="TREATMENT", treatment="", medicine=str(item_id(app, "Tylosin 20%")),
                             medicine_amount="5"))
    with app.app_context():
        assert HealthRecord.query.one().treatment == "Tylosin 20%"


def test_a_workers_treatment_goes_on_the_farmers_check_list(app, client):
    pharmacy_with(client, medicine())
    goat = add_animal(app, "G001")
    as_worker(client)
    client.post(f"/records/add/goat/health/{goat}",
                data=illness(medicine=str(item_id(app, "Tylosin 20%")), medicine_amount="6"))
    assert uses(app)[0][4] is False                                   # checked=False
    as_farmer(client)
    page = client.get("/pharmacy/check").data
    assert b"-6 ml" in page and b"G001" in page and b"Pneumonia" in page


def test_another_farms_medicine_cannot_be_picked(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    login(client, "farmer", email="other@example.com")
    client.post("/pharmacy/new", data=medicine(name="Theirs"))
    pharmacy_with(client, medicine())
    goat = add_animal(app, "G001")
    page = client.post(f"/records/add/goat/health/{goat}",
                       data=illness(medicine=str(item_id(app, "Theirs")), medicine_amount="5")).data
    assert b"Not a valid choice" in page
    assert item(app, "Theirs").quantity == 100
    with app.app_context():
        assert HealthRecord.query.count() == 0


# ------------------------------------------------------------ group sessions

def test_spraying_takes_the_spray_from_the_pharmacy(app, client):
    pharmacy_with(client, medicine(name="Dominex", disease="External parasites", kind="ACARICIDE", quantity="1000"))
    add_animal(app, "C001", species="CATTLE")
    add_animal(app, "C002", species="CATTLE")
    dominex = str(item_id(app, "Dominex"))
    # The farm's usual product "Dip Dominex" picks Dominex by itself.
    page = client.get("/group/spray/cattle").data.decode()
    assert f'<option selected value="{dominex}">' in page

    client.post("/group/spray/cattle", data=session_data(product="Dip Dominex", medicine=dominex, medicine_amount="300"))
    assert item(app, "Dominex").quantity == 700
    assert uses(app) == [("Dominex", 300, None, "Tick spraying, 2 cattle", True, False, True)]
    with app.app_context():
        assert StockMovement.query.filter_by(kind="USED").one().activity_id == HerdActivity.query.one().activity_id


def test_a_session_can_leave_the_product_box_empty_if_the_medicine_is_picked(app, client):
    pharmacy_with(client, medicine(name="Nilzan", disease="Gastrointestinal worms", kind="DEWORMER"))
    first, second = add_animal(app, "G001"), add_animal(app, "G002")
    client.post("/group/deworm/goat", data={**session_data(product="", medicine=str(item_id(app, "Nilzan")),
                                                           medicine_amount="20"), "animals": [first, second]})
    with app.app_context():
        assert HerdActivity.query.one().product == "Nilzan"
        assert {r.treatment for r in HealthRecord.query.all()} == {"Nilzan"}
    assert uses(app)[0][3] == "Deworming, 2 goats" and item(app, "Nilzan").quantity == 80


def test_group_vaccination_takes_the_doses(app, client):
    pharmacy_with(client, medicine(name="CCPP doses", disease="CCPP", kind="VACCINE", unit="doses", quantity="50"))
    first, second = add_animal(app, "G001"), add_animal(app, "G002")
    client.post("/group/vaccinate/goat", data={**session_data(vaccine="CCPP vaccine", medicine=str(item_id(app, "CCPP doses")),
                                                              medicine_amount="2"), "animals": [first, second]})
    with app.app_context():
        # The vaccine's name stays in treatment, where the model looks for it.
        assert {r.treatment for r in HealthRecord.query.all()} == {"CCPP vaccine"}
    assert item(app, "CCPP doses").quantity == 48


def test_a_session_cannot_use_more_than_is_in_stock(app, client):
    pharmacy_with(client, medicine(name="Dominex", kind="ACARICIDE", quantity="200"))
    add_animal(app, "C001", species="CATTLE")
    page = client.post("/group/spray/cattle", data=session_data(product="Dip Dominex", medicine=str(item_id(app, "Dominex")),
                                                                 medicine_amount="300")).data
    assert b"Only 200 ml in stock" in page
    with app.app_context():
        assert HerdActivity.query.count() == 0
    assert item(app, "Dominex").quantity == 200