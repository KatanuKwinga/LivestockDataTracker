"""Health and weight records for one animal."""
from datetime import date, timedelta

from app.extensions import db
from app.models import HealthRecord, WeightRecord
from tests.conftest import register_farmer
from tests.test_herd import bury, sell
from tests.test_records import add_worker_and_log_in_as_them
from tests.test_records_general import add_animal, farmer_logged_in


def illness(**changes):
    data = {"record_type": "ILLNESS", "date": "2026-09-14", "disease": "Pneumonia", "vaccine": "",
            "temperature": "40.6", "treatment": "Oxytetracycline", "dosage": "5 ml",
            "description": "Coughing, not eating"}
    data.update(changes)
    return data


def health_records(app):
    with app.app_context():
        return HealthRecord.query.all()


# ------------------------------------------------------------------- health

def test_health_and_weight_tiles_lead_to_choosing_an_animal(app, client):
    farmer_logged_in(client)
    add_animal(app, "G001")
    page = client.get("/records/add/goat").data
    assert b"/records/add/goat/health" in page and b"/records/add/goat/weight" in page
    assert b"/records/add/goat/health/" in client.get("/records/add/goat/health").data


def test_health_form_offers_only_this_species_vaccines(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    cow = add_animal(app, "C001", species="CATTLE")

    goat_page = client.get(f"/records/add/goat/health/{goat}").data
    cow_page = client.get(f"/records/add/cattle/health/{cow}").data

    assert b"CCPP vaccine" in goat_page and b"Lumpy skin vaccine" not in goat_page
    assert b"Lumpy skin vaccine" in cow_page and b"CCPP vaccine" not in cow_page
    assert b"East Coast Fever" in cow_page                  # disease suggestions for cattle


def test_recording_an_illness(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")

    response = client.post(f"/records/add/goat/health/{goat}", data=illness())

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/records/saved/{goat}/health")
    record = health_records(app)[0]
    assert (record.record_type, record.disease, record.temperature) == ("ILLNESS", "Pneumonia", 40.6)
    assert (record.treatment, record.dosage, record.date) == ("Oxytetracycline", "5 ml", date(2026, 9, 14))

    saved = client.get(response.headers["Location"]).data
    assert b"Saved for" in saved and b"Pneumonia" in saved and b"40.6" in saved


def test_illness_needs_a_disease_and_treatment_needs_a_medicine(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")

    no_disease = client.post(f"/records/add/goat/health/{goat}", data=illness(disease=""))
    no_medicine = client.post(f"/records/add/goat/health/{goat}", data=illness(record_type="TREATMENT", treatment=""))

    assert b"Write the disease or problem" in no_disease.data
    assert b"Write the medicine that was given" in no_medicine.data
    assert health_records(app) == []


def test_vaccination_is_saved_the_way_the_model_reads_it(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")

    # A disease typed before switching to "Vaccinated" must not be saved:
    # the model would count a vaccination with a disease as an illness.
    client.post(f"/records/add/goat/health/{goat}",
                data=illness(record_type="VACCINATION", vaccine="CCPP vaccine", disease="Pneumonia", treatment=""))

    record = health_records(app)[0]
    assert (record.record_type, record.treatment, record.disease) == ("VACCINATION", "CCPP vaccine", None)


def test_vaccination_needs_a_vaccine_meant_for_the_species(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")

    missing = client.post(f"/records/add/goat/health/{goat}", data=illness(record_type="VACCINATION", vaccine=""))
    wrong = client.post(f"/records/add/goat/health/{goat}", data=illness(record_type="VACCINATION", vaccine="Lumpy skin vaccine"))

    assert b"Choose the vaccine that was given" in missing.data
    assert b"Not a valid choice" in wrong.data
    assert health_records(app) == []


def test_checkup_drops_any_disease(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/health/{goat}", data=illness(record_type="CHECKUP", treatment=""))
    record = health_records(app)[0]
    assert (record.record_type, record.disease) == ("CHECKUP", None)


def test_impossible_temperature_and_dates_are_refused(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001", date_of_birth=date(2024, 1, 10))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    cases = [
        (illness(temperature="395"), b"That reading isn&#39;t possible"),
        (illness(date=tomorrow), b"can&#39;t be in the future"),
        (illness(date="2023-12-31"), b"was born on 10 Jan 2024"),
    ]
    for data, message in cases:
        response = client.post(f"/records/add/goat/health/{goat}", data=data)
        assert message in response.data
    assert health_records(app) == []


def test_a_worker_can_record_health(app, client):
    add_worker_and_log_in_as_them(client)
    goat = add_animal(app, "G001")
    assert client.post(f"/records/add/goat/health/{goat}", data=illness()).status_code == 302
    assert len(health_records(app)) == 1


def test_sold_or_dead_animals_get_no_new_records(app, client):
    farmer_logged_in(client)
    sold = add_animal(app, "G001")
    dead = add_animal(app, "G002")
    sell(app, sold)
    bury(app, dead)

    response = client.post(f"/records/add/goat/health/{sold}", data=illness())
    assert response.headers["Location"].endswith(f"/herd/{sold}")
    assert b"was sold" in client.get(response.headers["Location"]).data
    assert client.post(f"/records/add/goat/weight/{dead}", data={"date": "2026-09-01", "weight": "40"}).status_code == 302
    assert health_records(app) == []
    with app.app_context():
        assert WeightRecord.query.count() == 0


def test_another_farms_animal_or_wrong_species_is_not_found(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_animal(app, "G001", email="other@example.com")
    farmer_logged_in(client)
    mine = add_animal(app, "G001")

    assert client.post(f"/records/add/goat/health/{theirs}", data=illness()).status_code == 404
    assert client.get(f"/records/add/cattle/health/{mine}").status_code == 404
    assert client.get(f"/records/saved/{theirs}/health").status_code == 404
    assert health_records(app) == []


# ------------------------------------------------------------------- weight

def test_recording_a_weight(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")

    response = client.post(f"/records/add/goat/weight/{goat}", data={"date": "2026-09-01", "weight": "41.5"})

    assert response.headers["Location"].endswith(f"/records/saved/{goat}/weight")
    with app.app_context():
        assert WeightRecord.query.one().weight == 41.5
    assert b"41.5 kg" in client.get(response.headers["Location"]).data
    assert b"Last weighed on 01 Sep 2026" in client.get(f"/records/add/goat/weight/{goat}").data


def test_impossible_weights_are_refused(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    for weight, message in (("0", b"must be more than 0"), ("415", b"heavier than any goat"), ("", b"Enter the weight")):
        response = client.post(f"/records/add/goat/weight/{goat}", data={"date": "2026-09-01", "weight": weight})
        assert message in response.data
    with app.app_context():
        assert WeightRecord.query.count() == 0


def test_saved_page_for_an_unknown_category_is_not_found(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    assert client.get(f"/records/saved/{goat}/nonsense").status_code == 404
    assert client.get(f"/records/saved/{goat}/health").status_code == 404     # nothing saved yet