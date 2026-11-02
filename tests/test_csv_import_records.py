"""Adding health records and weights from a CSV file. The shared checks
(headings, semicolons, Excel's hidden marker) are tested in test_csv_import.py."""
import io
from datetime import date, timedelta

from app.extensions import db
from app.models import CommercialInfo, HealthRecord, MortalityRecord, WeightRecord
from tests.conftest import register_farmer
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal

HEALTH_HEADINGS = "tag_number,date,record_type,disease,temperature,treatment,dosage,notes\n"


def upload(client, kind, text):
    data = {"file": (io.BytesIO(text.encode()), f"{kind}.csv")}
    return client.post(f"/records/import/{kind}", data=data, content_type="multipart/form-data",
                       follow_redirects=True).data.decode()


def count(app, model):
    with app.app_context():
        return db.session.query(model).count()


def test_a_good_health_file_is_saved_the_way_the_health_form_saves_it(app, client):
    farm_with_worker(client)
    as_farmer(client)
    cow = add_animal(app, "C101", species="CATTLE", date_of_birth=date(2023, 5, 14))
    add_animal(app, "G045")
    page = upload(client, "health", HEALTH_HEADINGS +
                  "c101,2025-04-02,Illness,East Coast Fever,\"40,5\",Butalex,10 ml,Lying down\n"
                  "C101,2025-04-05,treatment,East Coast Fever,,Oxytetracycline,20 ml,\n"
                  "G045,12/05/2025,vaccination,,,ppr vaccine,,\n"
                  "G045,01/06/2025,check-up,Nothing,38.9,,,Healthy\n")
    assert "4 health records added from the file" in page
    with app.app_context():
        rows = {(r.animal.tag_number, r.record_type): r for r in HealthRecord.query}
        ill = rows[("C101", "ILLNESS")]
        assert (ill.animal_id, ill.date, ill.disease, ill.temperature) == (cow, date(2025, 4, 2), "East Coast Fever", 40.5)
        # The model finds vaccinations by the vaccine's exact name in treatment.
        vaccination = rows[("G045", "VACCINATION")]
        assert (vaccination.treatment, vaccination.disease) == ("PPR vaccine", None)
        assert rows[("G045", "CHECKUP")].disease is None      # a check-up has no disease, as on the form


def test_any_health_problem_means_nothing_is_saved_and_every_problem_is_listed(app, client):
    farm_with_worker(client)
    as_farmer(client)
    add_animal(app, "C101", species="CATTLE", date_of_birth=date(2024, 1, 1))
    future = (date.today() + timedelta(days=3)).isoformat()
    page = upload(client, "health", HEALTH_HEADINGS +
                  "C101,2025-04-02,illness,Mastitis,,,,\n"           # fine on its own
                  "C102,2025-04-02,illness,Mastitis,,,,\n"           # no such animal
                  f"C101,{future},illness,Mastitis,,,,\n"            # in the future
                  "C101,2023-06-01,illness,Mastitis,,,,\n"           # before it was born
                  "C101,2025-04-03,illness,,,,,\n"                   # an illness without a disease
                  "C101,2025-04-04,treatment,Mastitis,,,,\n"         # a treatment without a medicine
                  "C101,2025-04-05,vaccination,,,PPR vaccine,,\n"    # a goat and sheep vaccine
                  "C101,2025-04-06,vaccination,,,Wonder jab,,\n"     # not a vaccine the app knows
                  "C101,2025-04-07,checkup,,395,,,\n"                # temperature typo
                  "C101,2025-04-08,operation,,,,,\n"                 # not a record type
                  "C101,2025-04-02,illness,Mastitis,,,,\n")          # the same as row 2
    assert "Nothing was added: 10 problems to fix" in page
    for message in ("no animal with tag C102", "can&#39;t be in the future", "born on 01 Jan 2024",
                    "needs the disease", "needs the medicine", "PPR vaccine isn&#39;t given to cattle",
                    "Wonder jab", "Temperature &#34;395&#34;", "Record type &#34;operation&#34;",
                    "same as row 2"):
        assert message in page
    assert count(app, HealthRecord) == 0


def test_old_records_for_animals_that_left_are_allowed_up_to_the_day_they_left(app, client):
    farm_with_worker(client)
    as_farmer(client)
    sold = add_animal(app, "C101", species="CATTLE")
    died = add_animal(app, "G001")
    with app.app_context():
        db.session.add(CommercialInfo(animal_id=sold, transaction_type="SELL", date=date(2025, 6, 30), amount=50000))
        db.session.add(MortalityRecord(animal_id=died, date_of_death=date(2025, 3, 1)))
        db.session.commit()
    page = upload(client, "weights", "tag_number,date,weight_kg\n"
                  "C101,2025-06-01,300\nG001,2025-02-01,30\nC101,2025-07-01,310\nG001,2025-03-02,31\n")
    assert "C101 was sold on 30 Jun 2025" in page and "G001 died on 01 Mar 2025" in page
    page = upload(client, "weights", "tag_number,date,weight_kg\nC101,2025-06-01,300\nG001,2025-02-01,30\n")
    assert "2 weights added from the file" in page


def test_weights_are_checked_and_saved(app, client):
    farm_with_worker(client)
    as_farmer(client)
    goat = add_animal(app, "G001")
    page = upload(client, "weights", "tag_number,date,weight_kg\n"
                  "G001,2025-04-01,280\n"            # heavier than any goat: an extra zero
                  "G001,2025-04-02,0\n"
                  "G001,2025-04-03,heavy\n"
                  "G001,2025-04-04,28\nG001,2025-04-04,29\n")   # the same day twice
    assert "Nothing was added: 4 problems to fix" in page
    assert "heavier than any goat (150 kg)" in page and "on row 5 too" in page
    assert count(app, WeightRecord) == 0

    assert "1 weight added from the file" in upload(client, "weights", "tag_number,date,weight_kg\nG001,2025-04-04,28.5\n")
    with app.app_context():
        weight = WeightRecord.query.one()
        assert (weight.animal_id, weight.date, weight.weight) == (goat, date(2025, 4, 4), 28.5)
    # Uploading the same file again would double every weight, so it is refused.
    assert "G001 already has a weight on 04 Apr 2025" in upload(
        client, "weights", "tag_number,date,weight_kg\nG001,2025-04-04,28.5\n")
    assert count(app, WeightRecord) == 1


def test_a_file_can_only_name_animals_on_your_own_farm(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    add_animal(app, "G777", email="other@example.com")      # on the other farm
    farm_with_worker(client)
    as_worker(client)                                        # a worker imports into their farmer's farm
    add_animal(app, "G001")
    page = upload(client, "weights", "tag_number,date,weight_kg\nG777,2025-04-01,30\n")
    assert "no animal with tag G777 on this farm" in page
    assert "1 weight added" in upload(client, "weights", "tag_number,date,weight_kg\nG001,2025-04-01,30\n")
    assert count(app, WeightRecord) == 1


def test_each_kind_has_its_own_template_and_unknown_kinds_are_404(client):
    farm_with_worker(client)
    as_farmer(client)
    assert client.get("/records/import/health/template.csv").data.decode().startswith(HEALTH_HEADINGS)
    assert client.get("/records/import/weights/template.csv").data.decode().startswith("tag_number,date,weight_kg")
    assert client.get("/records/import/pharmacy").status_code == 404
    assert client.get("/records/import/pharmacy/template.csv").status_code == 404
    page = client.get("/records/import/health").data.decode()
    assert "Add health records from a" in page and "record_type" in page and "not taken off the pharmacy stock" in page