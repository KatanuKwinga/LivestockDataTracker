"""Changing pharmacy stock. Every page that changes stock (uses, deliveries, corrections, and later
health records and group treatments) goes through add_line(), so the
balance and the ledger can never disagree.
"""
from datetime import date

from app.extensions import db
from app.models import StockMovement


def add_line(item, kind, amount, day, user_id, checked=True, remarks=None, animal_id=None, **delivery):
    """Write one ledger line and update the balance. Returns the line."""
    if kind == "CORRECTED":
        change = amount - item.quantity
    elif kind == "USED":
        change = -amount
    else:                                   # OPENING, RECEIVED
        change = amount
    item.quantity = item.quantity + change
    line = StockMovement(item=item, kind=kind, date=day, amount=amount, change=change,
                         balance_after=item.quantity, remarks=remarks, animal_id=animal_id,
                         recorded_by=user_id, checked=checked, **delivery)
    db.session.add(line)
    return line


def undo_line(line, user_id):
    """Cancel a wrong line by writing one that does the opposite.

    The wrong line stays in the history, marked undone, so the ledger still
    shows what happened. Returns None if undoing would make the balance
    negative (e.g. a delivery whose stock has since been used)."""
    item = line.item
    if item.quantity - line.change < 0:
        return None
    item.quantity = item.quantity - line.change
    line.undone, line.checked = True, True
    reversal = StockMovement(item=item, kind="UNDONE", date=date.today(), amount=abs(line.change),
                             change=-line.change, balance_after=item.quantity, recorded_by=user_id,
                             remarks=f"Cancelled the line of {line.date:%d %b}")
    db.session.add(reversal)
    return reversal