"""The health form's medicines table: several medicines on one record, each
with a dose and a unit; a pharmacy medicine's unit can't change and its dose
comes off the stock; a "new" medicine the pharmacy already has is refused;
and after saving, new medicines can be added to the pharmacy."""
from app.models import HealthRecord
from tests.test_pharmacy import as_worker, medicine
from tests.test_pharmacy_links import from_pharmacy, item, pharmacy_with
from tests.test_records_general import add_animal
from tests.test_records_health import illness


def new_medicine(name, amount, unit, row=0):
    """One row of the medicines table: a medicine that isn't in the pharmacy."""
    return {f"medicines-{row}-item": "new", f"medicines-{row}-name": name,
            f"medicines-{row}-amount": amount, f"medicines-{row}-unit": unit}


def saved_record(app):
    with app.app_context():
        record = HealthRecord.query.one()
        return record, [(m.name, m.amount, m.unit, m.item_id is not None) for m in record.medicines]


def health_count(app):
    with app.app_context():
        return HealthRecord.query.count()


# ------------------------------------------------------------ several medicines

def test_several_medicines_are_saved_on_one_record(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%"), medicine(name="Multivitamin", unit="ml"))
    goat = add_animal(app, "G001")
    data = illness(treatment="", **from_pharmacy(app, "Tylosin 20%", "8", row=0),
                   **from_pharmacy(app, "Multivitamin", "5", row=1),
                   **new_medicine("Meloxicam", "2", "tablets", row=2))
    response = client.post(f"/records/add/goat/health/{goat}", data=data)

    assert response.status_code == 302
    record, medicines = saved_record(app)
    assert medicines == [("Tylosin 20%", 8, "ml", True), ("Multivitamin", 5, "ml", True),
                         ("Meloxicam", 2, "tablets", False)]
    # Both pharmacy medicines came off the stock; the new one changes no stock.
    assert item(app, "Tylosin 20%").quantity == 92 and item(app, "Multivitamin").quantity == 95
    # The short summary in the old boxes, for the CSV export and older pages.
    assert record.treatment == "Tylosin 20%, Multivitamin, Meloxicam"
    assert record.dosage == "8 ml, 5 ml, 2 tablets"

    saved = client.get(response.headers["Location"]).data.decode()
    assert "Tylosin 20% 8 ml, Multivitamin 5 ml, Meloxicam 2 tablets" in saved
    animal_page = client.get(f"/herd/{goat}").data.decode()
    assert "Meloxicam 2 tablets" in animal_page


def test_rows_left_empty_are_ignored(app, client):
    pharmacy_with(client, medicine())
    goat = add_animal(app, "G001")
    data = illness(**{"medicines-1-item": "", "medicines-1-name": "", "medicines-1-amount": "", "medicines-1-unit": ""})
    client.post(f"/records/add/goat/health/{goat}", data=data)
    _, medicines = saved_record(app)
    assert medicines == [("Oxytetracycline", 5, "ml", False)]


def test_a_checkup_needs_no_medicine(app, client):
    pharmacy_with(client)
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/health/{goat}", data=illness(record_type="CHECKUP", treatment=""))
    record, medicines = saved_record(app)
    assert medicines == [] and record.treatment is None


# ------------------------------------------------------------ the unit

def test_a_pharmacy_medicines_unit_is_filled_in_and_cannot_change(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%", unit="ml"))
    goat = add_animal(app, "G001")
    url = f"/records/add/goat/health/{goat}"

    page = client.post(url, data=illness(treatment="", **from_pharmacy(app, "Tylosin 20%", "8", unit="tablets"))).data
    assert b"Tylosin 20% is kept in ml in the pharmacy, so its unit is ml" in page
    assert health_count(app) == 0 and item(app, "Tylosin 20%").quantity == 100

    client.post(url, data=illness(treatment="", **from_pharmacy(app, "Tylosin 20%", "8", unit="")))
    assert saved_record(app)[1] == [("Tylosin 20%", 8, "ml", True)]


def test_a_new_medicine_needs_a_name_a_dose_and_a_unit(app, client):
    pharmacy_with(client)
    goat = add_animal(app, "G001")
    page = client.post(f"/records/add/goat/health/{goat}",
                       data=illness(treatment="", **new_medicine("", "", ""))).data
    assert b"Write the medicine&#39;s name" in page or b"Write the medicine's name" in page
    assert b"Enter the dose given" in page and b"Choose the unit" in page
    assert health_count(app) == 0


def test_a_unit_that_is_not_ours_is_refused(app, client):
    pharmacy_with(client)
    goat = add_animal(app, "G001")
    page = client.post(f"/records/add/goat/health/{goat}",
                       data=illness(treatment="", **new_medicine("Meloxicam", "2", "spoons"))).data
    assert b"Not a valid choice" in page and health_count(app) == 0


# ------------------------------------------------------------ already in stock

def test_a_new_medicine_the_pharmacy_already_has_is_refused(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%"))
    goat = add_animal(app, "G001")
    # Typed as "not in the pharmacy", with different capitals.
    page = client.post(f"/records/add/goat/health/{goat}",
                       data=illness(treatment="", **new_medicine("tylosin 20%", "8", "ml"))).data
    assert b"Tylosin 20% is already in the pharmacy" in page
    assert health_count(app) == 0 and item(app, "Tylosin 20%").quantity == 100


def test_the_form_gives_the_page_what_the_pop_ups_need(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%", unit="ml"))
    goat = add_animal(app, "G001")
    page = client.get(f"/records/add/goat/health/{goat}").data.decode()
    assert '"name": "Tylosin 20%", "unit": "ml"' in page            # the pharmacy, for the script
    assert 'id="medDialog"' in page and "already in stock in the pharmacy" in page
    assert "Not in the pharmacy: type its name" in page
    assert 'id="medicineRow"' in page and "medicines-__i__-item" in page      # the row "Add another" copies


# ------------------------------------------------------------ stock

def test_the_same_pharmacy_medicine_twice_must_fit_the_stock_together(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%", quantity="10"))
    goat = add_animal(app, "G001")
    page = client.post(f"/records/add/goat/health/{goat}",
                       data=illness(treatment="", **from_pharmacy(app, "Tylosin 20%", "6", row=0),
                                    **from_pharmacy(app, "Tylosin 20%", "6", row=1))).data
    assert b"Only 10 ml of Tylosin 20% in stock" in page
    assert health_count(app) == 0 and item(app, "Tylosin 20%").quantity == 10


# ------------------------------------------------------------ add to the pharmacy

def test_after_saving_new_medicines_can_be_added_to_the_pharmacy(app, client):
    pharmacy_with(client, medicine(name="Tylosin 20%"))
    goat = add_animal(app, "G001")
    response = client.post(f"/records/add/goat/health/{goat}",
                           data=illness(treatment="", **from_pharmacy(app, "Tylosin 20%", "8", row=0),
                                        **new_medicine("Meloxicam", "2", "tablets", row=1)))
    saved = client.get(response.headers["Location"]).data.decode()
    assert "Add to the farm&#39;s pharmacy?" in saved or "Add to the farm's pharmacy?" in saved
    assert "/pharmacy/new?name=Meloxicam&amp;unit=tablets&amp;treats=Pneumonia" in saved
    assert "name=Tylosin" not in saved                    # already in the pharmacy: not offered

    # The link fills in the pharmacy's form...
    form = client.get("/pharmacy/new?name=Meloxicam&unit=tablets&treats=Pneumonia").data.decode()
    assert 'value="Meloxicam"' in form and 'value="Pneumonia"' in form
    assert '<option selected value="tablets">' in form or 'value="tablets" selected' in form
    # ...and once it's added, the offer goes away.
    client.post("/pharmacy/new", data=medicine(name="Meloxicam", disease="Pneumonia", unit="tablets", quantity="18"))
    assert "Add to the farm" not in client.get(response.headers["Location"]).data.decode()


def test_workers_get_the_offer_too(app, client):
    pharmacy_with(client)
    goat = add_animal(app, "G001")
    as_worker(client)
    response = client.post(f"/records/add/goat/health/{goat}", data=illness())
    assert b"Add to pharmacy" in client.get(response.headers["Location"]).data


def test_the_pharmacy_form_ignores_a_unit_it_does_not_know(app, client):
    pharmacy_with(client)
    form = client.get("/pharmacy/new?name=X&unit=spoons").data.decode()
    assert "spoons" not in form