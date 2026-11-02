"""Adding many animals at once from a CSV file."""
import io
from datetime import date, timedelta

from app.extensions import db
from app.models import Livestock
from tests.conftest import register_farmer
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal, farm_id_of


def upload(client, text, name="animals.csv", encoding="utf-8"):
    data = {"file": (io.BytesIO(text.encode(encoding)), name)}
    return client.post("/records/import", data=data, content_type="multipart/form-data", follow_redirects=True)


def tags(app, email="jane@example.com"):
    with app.app_context():
        return sorted(a.tag_number for a in Livestock.query.filter_by(farmer_id=farm_id_of(email)))


def test_a_good_file_adds_every_animal(app, client):
    farm_with_worker(client)
    as_farmer(client)
    # Excel's "CSV UTF-8" adds a hidden marker at the start; both date styles; F/M; any capitals.
    text = ("\ufefftag_number,species,sex,breed,date_of_birth,castrated,notes\n"
            "c101,Cattle,F,Boran,2023-05-14,,Bought from a neighbour\n"
            "G045,goat,male,Galla,01/03/2025,yes,\n"
            ",,,,,,\n")                                  # an empty row at the end is ignored
    page = upload(client, text).data.decode()
    assert "2 animals added from the file" in page
    assert tags(app) == ["C101", "G045"]
    with app.app_context():
        goat = Livestock.query.filter_by(tag_number="G045").one()
        assert (goat.species, goat.gender, goat.castrated, goat.date_of_birth) == ("GOAT", "MALE", True, date(2025, 3, 1))


def test_any_problem_means_nothing_is_added_and_every_problem_is_listed(app, client):
    farm_with_worker(client)
    as_farmer(client)
    add_animal(app, "G001")
    future = (date.today() + timedelta(days=5)).isoformat()
    text = ("tag_number,species,sex,breed,date_of_birth,castrated,notes\n"
            "C101,cattle,female,,,,\n"            # fine on its own
            "C101,cattle,female,,,,\n"            # same tag twice in the file
            "G001,goat,female,,,,\n"              # already on the farm
            "S001,horse,female,,,,\n"             # not a species
            f"S002,sheep,female,,{future},,\n"    # born in the future
            "G002,goat,female,,,yes,\n"           # a castrated female
            ",goat,male,,,,\n")                   # no tag
    page = upload(client, text).data.decode()
    assert "Nothing was added: 6 problems to fix" in page
    for message in ("Tag C101 is also on row 2", "Tag G001 is already used", "Species &#34;horse&#34;",
                    "can&#39;t be in the future", "Only a male can be castrated", "Every animal needs a tag number"):
        assert message in page
    assert tags(app) == ["G001"]                  # nothing new saved


def test_wrong_headings_or_a_non_csv_file_are_refused(app, client):
    farm_with_worker(client)
    as_farmer(client)
    assert "Missing: tag_number, species, sex" in upload(client, "tag,colour\nC1,brown\n").data.decode()
    assert "Upload a .csv file" in upload(client, "anything", name="animals.xlsx").data.decode()
    assert tags(app) == []


def test_semicolon_files_from_excel_work_too(app, client):
    farm_with_worker(client)
    as_farmer(client)
    upload(client, "tag_number;species;sex\nS010;sheep;female\n")
    assert tags(app) == ["S010"]


def test_a_worker_imports_into_their_farmers_farm_only(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    farm_with_worker(client)
    as_worker(client)
    upload(client, "tag_number,species,sex\nC200,cattle,female\n")
    assert tags(app) == ["C200"] and tags(app, "other@example.com") == []


def test_the_template_can_be_downloaded(client):
    farm_with_worker(client)
    as_farmer(client)
    response = client.get("/records/import/template.csv")
    assert response.mimetype == "text/csv"
    assert response.data.decode().startswith("tag_number,species,sex,breed,date_of_birth,castrated,notes")
    assert b"Add many from a CSV file" in client.get("/records/add").data