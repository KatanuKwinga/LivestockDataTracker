"""The farm pharmacy: adding medicines, recording uses and deliveries,
correcting stock, asking to reorder, and the farmer's "to check" list."""
from datetime import date, timedelta

from app.extensions import db
from app.models import Farmer, Livestock, MortalityRecord, PharmacyItem, StockMovement
from app.seed_pharmacy import BOOK_MEDICINES, add_book_medicines, remove_book_medicines
from tests.conftest import login, register_farmer


# ---------------------------------------------------------------- helpers

def medicine(**changes):
    data = {"name": "Tylosin 20%", "disease": "Pneumonia", "kind": "MEDICINE", "unit": "ml",
            "quantity": "100", "reorder_level": "30", "notes": ""}
    data.update(changes)
    return data


def farm_with_worker(client):
    """Jane's farm, with Wanjiru as a worker. Nobody is left logged in."""
    client.post("/auth/logout")                     # in case someone else was logged in
    register_farmer(client)
    login(client, "farmer")
    client.post("/workers/new", data={"name": "Wanjiru Kamau", "email": "w@example.com", "phone": "",
                                      "password": "workerpass1", "confirm_password": "workerpass1"})
    client.post("/auth/logout")


def as_farmer(client):
    client.post("/auth/logout")
    login(client, "farmer")


def as_worker(client):
    client.post("/auth/logout")
    login(client, "worker", email="w@example.com", password="workerpass1")


def add_cow(app, tag="C001", email="jane@example.com"):
    with app.app_context():
        farmer = Farmer.query.join(Farmer.user).filter_by(email=email).one()
        cow = Livestock(farmer_id=farmer.farmer_id, tag_number=tag, species="CATTLE", gender="FEMALE")
        db.session.add(cow)
        db.session.commit()
        return cow.animal_id


def tylosin(app, client):
    """Jane's farm with Wanjiru and 100 ml of Tylosin (reorder at 30). Jane is logged in."""
    farm_with_worker(client)
    as_farmer(client)
    client.post("/pharmacy/new", data=medicine())
    with app.app_context():
        return PharmacyItem.query.one().item_id


def use(client, item_id, **changes):
    data = {"date": date.today().isoformat(), "amount": "10", "animal_id": "", "reason": "Pneumonia, temp 40"}
    data.update(changes)
    return client.post(f"/pharmacy/{item_id}/use", data=data)


def delivery(client, item_id, **changes):
    data = {"date": date.today().isoformat(), "amount": "200", "cost": "3500", "supplier": "Agrovet", "expiry_date": ""}
    data.update(changes)
    return client.post(f"/pharmacy/{item_id}/delivery", data=data)


def ledger(app, item_id):
    """(balance, [(kind, change, balance_after, checked, undone), ...])."""
    with app.app_context():
        item = db.session.get(PharmacyItem, item_id)
        return item.quantity, [(m.kind, m.change, m.balance_after, m.checked, m.undone) for m in item.movements]


# ---------------------------------------------------------------- medicines

def test_pharmacy_needs_a_login_and_is_in_the_navigation(client):
    assert client.get("/pharmacy/").headers["Location"].startswith("/?next=")
    farm_with_worker(client)
    as_worker(client)
    home = client.get("/dashboard").data
    assert b'href="/pharmacy/"' in home and b"Record medicine used or delivered" in home


def test_adding_a_medicine_writes_its_opening_balance(app, client):
    item_id = tylosin(app, client)
    assert ledger(app, item_id) == (100, [("OPENING", 100, 100, True, False)])
    page = client.get(f"/pharmacy/{item_id}").data
    assert b"Opening balance" in page and b"Jane" in page and b"Pneumonia" in page


def test_bad_details_are_refused(app, client):
    farm_with_worker(client)
    as_farmer(client)
    for data, message in ((medicine(name=""), b"Write the medicine"), (medicine(disease=""), b"Write what it treats"),
                          (medicine(quantity=""), b"Enter what is on the shelf"),
                          (medicine(reorder_level="-1"), b"can&#39;t be negative"),
                          (medicine(unit="buckets"), b"Not a valid choice")):
        assert message in client.post("/pharmacy/new", data=data).data
    with app.app_context():
        assert PharmacyItem.query.count() == 0


def test_names_are_unique_per_farm_ignoring_capitals(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    login(client, "farmer", email="other@example.com")
    client.post("/pharmacy/new", data=medicine())
    farm_with_worker(client)
    as_farmer(client)
    client.post("/pharmacy/new", data=medicine())                       # another farm may use the name
    again = client.post("/pharmacy/new", data=medicine(name="TYLOSIN 20%"))
    assert b"already has a medicine with this name" in again.data
    with app.app_context():
        assert PharmacyItem.query.count() == 2


def test_editing_never_changes_the_balance(app, client):
    item_id = tylosin(app, client)
    client.post(f"/pharmacy/{item_id}/edit", data=medicine(name="Tylosin LA", reorder_level="40", quantity="9999"))
    with app.app_context():
        item = db.session.get(PharmacyItem, item_id)
        assert (item.name, item.reorder_level, item.quantity) == ("Tylosin LA", 40, 100)


def test_status_follows_the_reorder_level(app, client):
    item_id = tylosin(app, client)                                      # 100 ml, reorder at 30
    statuses = []
    for amount in ("60", "10", "30"):                                   # 40, then 30, then 0 left
        use(client, item_id, amount=amount)
        with app.app_context():
            statuses.append(db.session.get(PharmacyItem, item_id).status)
    assert statuses == ["OK", "LOW", "OUT"]
    page = client.get("/pharmacy/").data
    assert b"Out: Tylosin 20%." in page


# ------------------------------------------------------------- uses

def test_a_use_comes_off_the_stock_at_once(app, client):
    item_id = tylosin(app, client)
    cow = add_cow(app)
    response = use(client, item_id, amount="15", animal_id=str(cow))
    assert ledger(app, item_id)[0] == 85
    page = client.get(response.headers["Location"]).data
    assert b"Saved. 85 ml left." in page and b"C001" in page and b"Pneumonia, temp 40" in page


def test_uses_are_checked(app, client):
    item_id = tylosin(app, client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for changes, message in (({"amount": "0"}, b"Enter more than 0"), ({"amount": ""}, b"Enter the amount used"),
                             ({"amount": "101"}, b"Only 100 ml in stock"), ({"reason": ""}, b"Say why it was used"),
                             ({"date": tomorrow}, b"can&#39;t be in the future")):
        assert message in use(client, item_id, **changes).data
    assert ledger(app, item_id)[0] == 100


def test_only_this_farms_animals_still_on_the_farm_can_be_chosen(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    theirs = add_cow(app, "C900", email="other@example.com")
    item_id = tylosin(app, client)
    add_cow(app, "C001")
    dead = add_cow(app, "C002")
    with app.app_context():
        db.session.add(MortalityRecord(animal_id=dead, date_of_death=date.today(), cause_of_death="ECF"))
        db.session.commit()
    form = client.get(f"/pharmacy/{item_id}/use").data
    assert b"C001" in form and b"C002" not in form and b"C900" not in form
    assert b"Not a valid choice" in use(client, item_id, animal_id=str(theirs)).data


def test_the_medicine_page_lists_every_use_and_who_recorded_it(app, client):
    item_id = tylosin(app, client)
    long_ago = (date.today() - timedelta(days=40)).isoformat()
    use(client, item_id, amount="5", date=long_ago, reason="Eye infection")
    use(client, item_id, amount="15", reason="ECF, temp 40")
    as_worker(client)
    use(client, item_id, amount="7", reason="Repeat dose")
    page = client.get(f"/pharmacy/{item_id}").data.decode()
    history = page.split("<h3>History")[1]
    # Newest first, each with its amount and who recorded it.
    assert history.index("Repeat dose") < history.index("ECF, temp 40") < history.index("Eye infection")
    assert "-7" in history and "-15" in history and "Wanjiru" in history and "Jane" in history
    assert "Used, last 30 days</dt><dd>22 ml" in page                  # the old use is left out


# --------------------------------------------------- deliveries and corrections

def test_a_delivery_adds_stock_with_its_cost_and_supplier(app, client):
    item_id = tylosin(app, client)
    delivery(client, item_id, expiry_date="2027-06-30")
    with app.app_context():
        line = StockMovement.query.filter_by(kind="RECEIVED").one()
        assert (line.change, line.balance_after, float(line.cost), line.supplier, line.expiry_date) == (
            200, 300, 3500, "Agrovet", date(2027, 6, 30))
    page = client.get(f"/pharmacy/{item_id}").data
    assert b"Agrovet" in page and b"KES 3,500" in page and b"expires Jun 2027" in page


def test_a_delivery_needs_an_amount(app, client):
    item_id = tylosin(app, client)
    assert b"Enter more than 0" in delivery(client, item_id, amount="0").data
    assert b"Enter the amount received" in delivery(client, item_id, amount="").data
    assert ledger(app, item_id)[0] == 100


def test_the_farmer_corrects_the_stock_to_what_is_on_the_shelf(app, client):
    item_id = tylosin(app, client)
    assert b"Say why" in client.post(f"/pharmacy/{item_id}/correct", data={"amount": "80", "reason": ""}).data
    client.post(f"/pharmacy/{item_id}/correct", data={"amount": "80", "reason": "One bottle expired"})
    assert ledger(app, item_id)[1][-1] == ("CORRECTED", -20, 80, True, False)


def test_workers_cannot_correct_stock_or_edit(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    for url in (f"/pharmacy/{item_id}/correct", f"/pharmacy/{item_id}/edit", "/pharmacy/check"):
        assert client.get(url).headers["Location"].endswith("/dashboard")
    assert b"Correct the stock" not in client.get(f"/pharmacy/{item_id}").data


# -------------------------------------------------------------- reorders

def test_a_worker_asks_to_reorder_and_a_delivery_clears_it(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    client.post(f"/pharmacy/{item_id}/reorder")
    assert b"Reorder asked by Wanjiru" in client.get(f"/pharmacy/{item_id}").data
    as_farmer(client)
    page = client.get("/pharmacy/check").data
    assert b"Asked to reorder" in page and b"Tylosin 20%" in page
    delivery(client, item_id)
    assert b"Asked to reorder" not in client.get("/pharmacy/check").data


def test_the_farmer_can_clear_a_reorder_request(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    client.post(f"/pharmacy/{item_id}/reorder")
    as_farmer(client)
    client.post(f"/pharmacy/{item_id}/reorder/clear")
    with app.app_context():
        assert db.session.get(PharmacyItem, item_id).reorder_asked_at is None


# ---------------------------------------------------- the farmer's checks

def test_workers_entries_count_at_once_and_wait_to_be_checked(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    use(client, item_id, amount="10")
    client.post("/pharmacy/new", data=medicine(name="Butalex", disease="East Coast Fever"))
    assert ledger(app, item_id)[0] == 90                               # no waiting: it counts now

    as_farmer(client)
    assert b'class="nav-count">2<' in client.get("/pharmacy/").data
    page = client.get("/pharmacy/check").data
    assert b"Butalex" in page and b"-10 ml" in page and b"Wanjiru Kamau" in page

    client.post("/pharmacy/check/ok", data={"all": "1"})
    assert b'class="nav-count"' not in client.get("/pharmacy/").data
    assert b"Nothing new" in client.get("/pharmacy/check").data


def test_the_farmer_undoes_a_wrong_use(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    use(client, item_id, amount="80")
    as_farmer(client)
    with app.app_context():
        line_id = StockMovement.query.filter_by(kind="USED").one().movement_id
    client.post(f"/pharmacy/lines/{line_id}/undo")
    balance, lines = ledger(app, item_id)
    # The wrong line stays, marked undone, and a new line puts the stock back.
    assert balance == 100
    assert lines[1:] == [("USED", -80, 20, True, True), ("UNDONE", 80, 100, True, False)]
    assert b'class="undone"' in client.get(f"/pharmacy/{item_id}").data
    client.post(f"/pharmacy/lines/{line_id}/undo")                     # twice does nothing more
    assert ledger(app, item_id)[0] == 100


def test_a_delivery_already_used_cannot_be_undone(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    delivery(client, item_id, amount="50")
    as_farmer(client)
    use(client, item_id, amount="120")                                 # 30 left: less than the 50 delivered
    with app.app_context():
        line_id = StockMovement.query.filter_by(kind="RECEIVED").one().movement_id
    page = client.post(f"/pharmacy/lines/{line_id}/undo", follow_redirects=True).data
    assert b"Correct the stock instead" in page
    assert ledger(app, item_id)[0] == 30


def test_a_medicine_added_by_mistake_can_be_removed_until_it_has_history(app, client):
    item_id = tylosin(app, client)
    as_worker(client)
    client.post("/pharmacy/new", data=medicine(name="Tylosine"))       # a misspelt copy
    as_farmer(client)
    with app.app_context():
        typo = PharmacyItem.query.filter_by(name="Tylosine").one().item_id
    client.post(f"/pharmacy/{typo}/remove")
    use(client, item_id, amount="5")
    client.post(f"/pharmacy/{item_id}/remove")                         # has history: kept
    with app.app_context():
        assert [i.name for i in PharmacyItem.query.all()] == ["Tylosin 20%"]


def test_another_farms_pharmacy_is_not_found(app, client):
    register_farmer(client, name="Other Farmer", email="other@example.com")
    login(client, "farmer", email="other@example.com")
    client.post("/pharmacy/new", data=medicine())
    with app.app_context():
        theirs = PharmacyItem.query.one().item_id
        their_line = StockMovement.query.one().movement_id
    farm_with_worker(client)
    as_farmer(client)
    for url in (f"/pharmacy/{theirs}", f"/pharmacy/{theirs}/use", f"/pharmacy/{theirs}/edit"):
        assert client.get(url).status_code == 404
    assert client.post(f"/pharmacy/lines/{their_line}/undo").status_code == 404
    assert b'class="row-link"' not in client.get("/pharmacy/").data


# ------------------------------------------------------------------ demo

def test_demo_medicines_from_the_ledger_book(app, client):
    farm_with_worker(client)
    as_farmer(client)
    client.post("/pharmacy/new", data=medicine(name="My own medicine"))
    with app.app_context():
        farmer = Farmer.query.one()
        assert add_book_medicines(farmer) == len(BOOK_MEDICINES)
        assert add_book_medicines(farmer) == 0                         # running it twice adds nothing
        assert {i.status for i in PharmacyItem.query.all()} == {"OK", "LOW", "OUT"}
        assert remove_book_medicines(farmer) == len(BOOK_MEDICINES)
        assert [i.name for i in PharmacyItem.query.all()] == ["My own medicine"]


def test_logging_out_clears_unread_messages(client):
    # One person's messages must not show to the next on a shared computer.
    farm_with_worker(client)
    as_farmer(client)
    client.post("/pharmacy/new", data=medicine())                       # leaves an unread "added" message
    client.post("/auth/logout")
    register_farmer(client, name="Next Person", email="next@example.com")
    login(client, "farmer", email="next@example.com")
    assert b"Tylosin 20% added" not in client.get("/dashboard").data