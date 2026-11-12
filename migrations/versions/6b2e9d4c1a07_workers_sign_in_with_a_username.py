"""Workers sign in with a username; only farmers have an email

Revision ID: 6b2e9d4c1a07
Revises: a3f1c9e27b64
Create Date: 2026-11-11

Existing workers get a username made from the start of their old email
(wanjiru@example.com -> wanjiru, or wanjiru2 if that is taken), and their
email is cleared, so password resets by email are for farmers only. Check
the Workers page afterwards to see each worker's new username.
"""
import re

from alembic import op
import sqlalchemy as sa


revision = "6b2e9d4c1a07"
down_revision = "a3f1c9e27b64"
branch_labels = None
depends_on = None


def username_from(email, taken):
    """wanjiru.k@example.com -> wanjiru.k; adds 2, 3... if already taken."""
    base = re.sub(r"[^a-z0-9._-]", "", (email or "").split("@")[0].lower())[:26] or "worker"
    if len(base) < 3:
        base = f"worker{base}"
    name, number = base, 2
    while name in taken:
        name, number = f"{base}{number}", number + 1
    taken.add(name)
    return name


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(length=30), nullable=True))
        batch_op.create_unique_constraint("uq_users_username", ["username"])
        batch_op.alter_column("email", existing_type=sa.String(length=150), nullable=True)

    # Give every existing worker a username, and clear their email.
    connection = op.get_bind()
    workers = connection.execute(sa.text(
        "SELECT users.id, users.email FROM users JOIN workers ON workers.user_id = users.id ORDER BY users.id"
    )).fetchall()
    taken = set()
    for user_id, email in workers:
        connection.execute(sa.text("UPDATE users SET username = :u, email = NULL WHERE id = :id"),
                           {"u": username_from(email, taken), "id": user_id})


def downgrade():
    # Email can't be empty again, so workers get a made-up one from their username.
    op.execute("UPDATE users SET email = username || '@worker.invalid' WHERE email IS NULL")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=150), nullable=False)
        batch_op.drop_constraint("uq_users_username", type_="unique")
        batch_op.drop_column("username")