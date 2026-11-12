"""Add notes to breeding records (e.g. why a pregnancy was lost)

Revision ID: 8c41f0b7d2e5
Revises: 6b2e9d4c1a07
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa


revision = "8c41f0b7d2e5"
down_revision = "6b2e9d4c1a07"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("breeding_record", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("breeding_record", schema=None) as batch_op:
        batch_op.drop_column("notes")