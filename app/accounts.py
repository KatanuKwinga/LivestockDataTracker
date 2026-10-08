"""Creating accounts, shared by farmer registration and "Add worker".

Both save a User row plus a role row (Farmer or Worker) in one go. Rather
than writing that code twice, both routes call create_account() and only
say which role row to add.
"""
from sqlalchemy.exc import IntegrityError

from app.extensions import bcrypt, db
from app.models import User


def create_account(form, make_role):
    """Save a new User from a filled-in form, plus their role row.

    make_role is a function that receives the new User and returns the role
    object to save with it, e.g. a Farmer or a Worker. Returns the new User,
    or None if the email was already taken.
    """
    user = User(
        name=form.name.data,
        email=form.email.data,
        phone=form.phone.data or None,
        # bcrypt: a one-way hash, so the real password is never stored.
        password_hash=bcrypt.generate_password_hash(form.password.data).decode("utf-8"),
    )
    db.session.add(user)
    try:
        # flush() gives us user.id without committing; the role row needs it.
        # User and role are then committed together, or not at all.
        db.session.flush()
        db.session.add(make_role(user))
        db.session.commit()
    except IntegrityError:
        # Two sign-ups with the same email at the same instant: the
        # database's unique rule rejects the second. Undo and report it.
        db.session.rollback()
        return None
    return user