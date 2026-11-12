"""The farmer's El Nino switch for the disease alerts

Revision ID: 4d7a2c9e1b36
Revises: 8c41f0b7d2e5
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa


revision = "4d7a2c9e1b36"
down_revision = "8c41f0b7d2e5"
branch_labels = None
depends_on = None


def upgrade():
    # server_default fills in "off" for the farmers already in the database.
    with op.batch_alter_table("farmers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("el_nino_forecast", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("farmers", schema=None) as batch_op:
        batch_op.drop_column("el_nino_forecast")