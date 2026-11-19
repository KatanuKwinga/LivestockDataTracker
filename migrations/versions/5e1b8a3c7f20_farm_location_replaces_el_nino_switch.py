"""The farm's location to replace El Nino switch

Revision ID: 5e1b8a3c7f20
Revises: 4d7a2c9e1b36
Create Date: 2026-11-18

The disease alerts now use the farm's real rain and forecast from the
weather service, which needs to know where the farm is. El Nino shows up
in that rain, so the farmer's El Nino switch is no longer needed.
"""
from alembic import op
import sqlalchemy as sa


revision = "5e1b8a3c7f20"
down_revision = "4d7a2c9e1b36"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("farmers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("location_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.drop_column("el_nino_forecast")


def downgrade():
    with op.batch_alter_table("farmers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("el_nino_forecast", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
        batch_op.drop_column("location_name")