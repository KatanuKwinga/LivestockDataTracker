"""The farm pharmacy, laid out like the farm's ledger book: a list of
medicines, and for each one its history of uses and deliveries.
"""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.decorators import farmer_required
from app.extensions import db
from app.farm import current_farm_id
from app.forms import CorrectStockForm, DeliveryForm, MedicineForm, UseForm
from app.models import Farmer, PharmacyItem, StockMovement
from app.models.pharmacy import KINDS
from app.stock import add_line, undo_line
from ml.reference import CONDITIONS

pharmacy_bp = Blueprint("pharmacy", __name__, url_prefix="/pharmacy")

# Suggestions under the "Treats" box: the same names the health records
# and the simulator use, so the same disease isn't spelt three ways.
DISEASES = sorted({c.name for conditions in CONDITIONS.values() for c in conditions})


def farm_items():
    """This farm's medicines: the starting point of every query here."""
    return PharmacyItem.query.filter_by(farmer_id=current_farm_id())


def farm_lines():
    """Ledger lines of this farm's medicines."""
    return StockMovement.query.join(PharmacyItem).filter(PharmacyItem.farmer_id == current_farm_id())


def is_farmer():
    return isinstance(current_user, Farmer)


def to_check():
    """What the farmer hasn't looked at yet: medicines and lines workers
    added, and requests to reorder."""
    items = farm_items().filter_by(checked=False).order_by(PharmacyItem.added_at).all()
    lines = (farm_lines().filter(StockMovement.checked.is_(False), StockMovement.kind != "OPENING")
             .order_by(StockMovement.movement_id).all())
    reorders = farm_items().filter(PharmacyItem.reorder_asked_at.isnot(None)).order_by(PharmacyItem.reorder_asked_at).all()
    return items, lines, reorders


@pharmacy_bp.app_context_processor
def inject_to_check():
    """The number on the navbar's Pharmacy link, for the farmer only."""
    if not (current_user.is_authenticated and isinstance(current_user, Farmer)):
        return {"pharmacy_to_check": 0}
    return {"pharmacy_to_check": sum(len(group) for group in to_check())}


def locked_item(item_id):
    """The medicine, locked until we commit when a form is being saved, so
    two people changing its stock at the same moment go one after the
    other and neither change is lost. (SQLite, used by the tests, ignores
    the lock harmlessly.)"""
    query = farm_items().filter_by(item_id=item_id)
    if request.method == "POST":
        query = query.with_for_update()
    return query.first_or_404()


# ------------------------------------------------------------------ medicines

@pharmacy_bp.route("/")
@login_required
def index():
    items = farm_items().order_by(PharmacyItem.kind, PharmacyItem.name).all()
    return render_template("pharmacy/index.html", items=items,
                           out=[i.name for i in items if i.status == "OUT"],
                           low=[i.name for i in items if i.status == "LOW"])


@pharmacy_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_item():
    form = MedicineForm(current_farm_id())
    if form.validate_on_submit():
        farmer = is_farmer()
        item = PharmacyItem(farmer_id=current_farm_id(), quantity=0, added_by=current_user.user_id, checked=farmer)
        fill_item(item, form)
        db.session.add(item)
        # What is on the shelf is the first ledger line, so the ledger
        # always adds up to the balance.
        add_line(item, "OPENING", form.quantity.data, date.today(), current_user.user_id,
                 checked=farmer, remarks="Opening balance")
        if save(form):
            flash(f"{item.name} added." if farmer else f"{item.name} added. The farmer will check it.", "success")
            return redirect(url_for("pharmacy.item", item_id=item.item_id))
    return render_template("pharmacy/medicine_form.html", form=form, item=None, diseases=DISEASES)


@pharmacy_bp.route("/<int:item_id>")
@login_required
def item(item_id):
    """One medicine: its details and every line of its history, newest first."""
    item = farm_items().filter_by(item_id=item_id).first_or_404()
    return render_template("pharmacy/item.html", item=item, kinds=KINDS)


@pharmacy_bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
@farmer_required
def edit_item(item_id):
    item = farm_items().filter_by(item_id=item_id).first_or_404()
    form = MedicineForm(current_farm_id(), item)
    if form.validate_on_submit():
        fill_item(item, form)
        item.checked = True                 # the farmer has looked at it now
        if save(form):
            flash(f"{item.name} updated.", "success")
            return redirect(url_for("pharmacy.item", item_id=item.item_id))
    return render_template("pharmacy/medicine_form.html", form=form, item=item, diseases=DISEASES)


def fill_item(item, form):
    """Copy the form's boxes onto the medicine. Never the balance: that
    only changes through ledger lines."""
    for name in ("name", "disease", "kind", "unit", "reorder_level"):
        setattr(item, name, form[name].data)
    item.notes = form.notes.data or None


def save(form):
    """Commit. If two people added the same name at the same moment, the
    database refuses the second; say so on the form instead of crashing."""
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        form.name.errors.append("The pharmacy already has a medicine with this name.")
        return False


# ------------------------------------------------------------ ledger lines

@pharmacy_bp.route("/<int:item_id>/use", methods=["GET", "POST"])
@login_required
def record_use(item_id):
    item = locked_item(item_id)
    form = UseForm(item)
    if form.validate_on_submit():
        add_line(item, "USED", form.amount.data, form.date.data, current_user.user_id, checked=is_farmer(),
                 remarks=form.reason.data, animal_id=form.animal)
        db.session.commit()
        flash(f"Saved. {item.quantity:g} {item.unit} left.", "success")
        return redirect(url_for("pharmacy.item", item_id=item.item_id))
    return render_template("pharmacy/line_form.html", item=item, form=form, title="Record a use",
                           today=date.today().isoformat())


@pharmacy_bp.route("/<int:item_id>/delivery", methods=["GET", "POST"])
@login_required
def record_delivery(item_id):
    item = locked_item(item_id)
    form = DeliveryForm(item)
    if form.validate_on_submit():
        add_line(item, "RECEIVED", form.amount.data, form.date.data, current_user.user_id, checked=is_farmer(),
                 remarks="Delivery", cost=form.cost.data, supplier=form.supplier.data or None,
                 expiry_date=form.expiry_date.data)
        # The stock the worker asked for has come, so the request is done.
        item.reorder_asked_by = item.reorder_asked_at = None
        db.session.commit()
        flash(f"Saved. {item.quantity:g} {item.unit} in stock.", "success")
        return redirect(url_for("pharmacy.item", item_id=item.item_id))
    return render_template("pharmacy/line_form.html", item=item, form=form, title="Record a delivery",
                           today=date.today().isoformat())


@pharmacy_bp.route("/<int:item_id>/correct", methods=["GET", "POST"])
@farmer_required
def correct_stock(item_id):
    """Set the balance to what is really on the shelf, with the reason."""
    item = locked_item(item_id)
    form = CorrectStockForm(item)
    if form.validate_on_submit():
        add_line(item, "CORRECTED", form.amount.data, date.today(), current_user.user_id, remarks=form.reason.data)
        db.session.commit()
        flash(f"Saved. {item.quantity:g} {item.unit} in stock.", "success")
        return redirect(url_for("pharmacy.item", item_id=item.item_id))
    return render_template("pharmacy/line_form.html", item=item, form=form, title="Correct the stock",
                           today=date.today().isoformat())


@pharmacy_bp.route("/<int:item_id>/reorder", methods=["POST"])
@login_required
def ask_reorder(item_id):
    item = farm_items().filter_by(item_id=item_id).first_or_404()
    if item.reorder_asked_at is None:
        item.reorder_asked_by, item.reorder_asked_at = current_user.user_id, datetime.utcnow()
        db.session.commit()
    flash("The farmer has been asked to reorder it.", "success")
    return redirect(url_for("pharmacy.item", item_id=item.item_id))


# ------------------------------------------------------ the farmer's checks

@pharmacy_bp.route("/check")
@farmer_required
def check():
    items, lines, reorders = to_check()
    return render_template("pharmacy/check.html", items=items, lines=lines, reorders=reorders)


@pharmacy_bp.route("/check/ok", methods=["POST"])
@farmer_required
def mark_ok():
    """Mark one entry (or, with all=1, everything on the list) as looked at."""
    if request.form.get("all"):
        items, lines, _ = to_check()
        for entry in items + lines:
            entry.checked = True
    elif request.form.get("line_id"):
        farm_lines().filter(StockMovement.movement_id == request.form.get("line_id", type=int)).first_or_404().checked = True
    else:
        farm_items().filter_by(item_id=request.form.get("item_id", type=int)).first_or_404().checked = True
    db.session.commit()
    return redirect(url_for("pharmacy.check"))


@pharmacy_bp.route("/lines/<int:line_id>/undo", methods=["POST"])
@farmer_required
def undo(line_id):
    line = farm_lines().filter(StockMovement.movement_id == line_id).first_or_404()
    farm_items().filter_by(item_id=line.item_id).with_for_update().one()
    db.session.refresh(line)                # read it again now that we hold the lock
    if line.undone or line.kind not in ("USED", "RECEIVED"):
        flash("That line can't be undone.", "warning")
    elif undo_line(line, current_user.user_id) is None:
        flash("Can't undo it: some of that stock has been used since. Correct the stock instead.", "warning")
    else:
        db.session.commit()
        flash(f"Undone. {line.item.name}: {line.item.quantity:g} {line.item.unit} in stock.", "success")
    return redirect(url_for("pharmacy.check"))


@pharmacy_bp.route("/<int:item_id>/remove", methods=["POST"])
@farmer_required
def remove_item(item_id):
    """Delete a medicine added by mistake. Only while nothing has been
    used or delivered, so no real history is ever thrown away."""
    item = farm_items().filter_by(item_id=item_id).first_or_404()
    if any(m.kind != "OPENING" for m in item.movements):
        flash("It has a history, so it can't be removed.", "warning")
        return redirect(url_for("pharmacy.item", item_id=item.item_id))
    name = item.name                        # read it now: a deleted row can't be read after the commit
    db.session.delete(item)
    db.session.commit()
    flash(f"{name} removed.", "success")
    return redirect(url_for("pharmacy.check") if request.form.get("from_check") else url_for("pharmacy.index"))


@pharmacy_bp.route("/<int:item_id>/reorder/clear", methods=["POST"])
@farmer_required
def clear_reorder(item_id):
    """The farmer has dealt with a reorder request (ordered, or decided not to)."""
    item = farm_items().filter_by(item_id=item_id).first_or_404()
    item.reorder_asked_by = item.reorder_asked_at = None
    db.session.commit()
    return redirect(url_for("pharmacy.check"))