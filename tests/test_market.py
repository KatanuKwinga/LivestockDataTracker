"""Identifying animals for sale or culling under Add record, Commercial:
they go on the market list without being sold."""
from datetime import date

from app.extensions import db
from app.models import CommercialInfo, Livestock
from tests.test_pharmacy import as_farmer, as_worker, farm_with_worker
from tests.test_records_general import add_animal, farmer_logged_in
from tests.test_records_sale_death import sale


def identify(**changes):
    data = {"transaction_type": "MARK", "date": "2026-10-20", "market": "CULL", "market_note": "Old, low milk yield"}
    data.update(changes)
    return data


def goat_row(app, goat):
    with app.app_context():
        g = db.session.get(Livestock, goat)
        return g.market_status, g.market_marked_on, g.market_note, g.status


def test_the_commercial_form_offers_to_sell_or_cull(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    page = client.get(f"/records/add/goat/commercial/{goat}").data
    assert b"To sell or cull" in page and b"Sell or cull?" in page


def test_identifying_an_animal_puts_it_on_the_market_list_without_selling_it(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    response = client.post(f"/records/add/goat/commercial/{goat}", data=identify())   # no price needed
    assert response.headers["Location"].endswith(f"/herd/{goat}")
    assert goat_row(app, goat) == ("CULL", date(2026, 10, 20), "Old, low milk yield", "ON_FARM")
    with app.app_context():
        assert CommercialInfo.query.count() == 0                     # nothing was sold
    assert b"Old, low milk yield" in client.get("/status/market").data
    assert b"since 20 Oct 2026: Old, low milk yield" in client.get(f"/herd/{goat}").data
    assert b"1 to cull" in client.get("/dashboard").data


def test_selling_an_identified_animal_takes_it_off_the_list(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    client.post(f"/records/add/goat/commercial/{goat}", data=identify(market="SELL"))
    assert b"already on the market list, to sell" in client.get(f"/records/add/goat/commercial/{goat}").data
    client.post(f"/records/add/goat/commercial/{goat}", data=sale())
    assert goat_row(app, goat)[0] is None and goat_row(app, goat)[3] == "SOLD"
    assert b"No animals identified" in client.get("/status/market").data


def test_a_sale_or_purchase_still_needs_a_price(app, client):
    farmer_logged_in(client)
    goat = add_animal(app, "G001")
    for kind in ("SELL", "BUY"):
        assert b"Enter the price in KES" in client.post(f"/records/add/goat/commercial/{goat}",
                                                        data=sale(transaction_type=kind, amount="")).data
    assert b"Not a valid choice" in client.post(f"/records/add/goat/commercial/{goat}", data=identify(market="EAT")).data
    assert goat_row(app, goat)[0] is None


def test_a_worker_can_identify_animals_for_the_farmer(app, client):
    farm_with_worker(client)
    goat = add_animal(app, "G001")
    as_worker(client)
    client.post(f"/records/add/goat/commercial/{goat}", data=identify(market="SELL", market_note=""))
    assert goat_row(app, goat)[:3] == ("SELL", date(2026, 10, 20), None)
    as_farmer(client)
    assert b"G001" in client.get("/status/market").data