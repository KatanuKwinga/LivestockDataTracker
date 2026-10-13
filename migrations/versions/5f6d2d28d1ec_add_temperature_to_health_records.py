"""Add temperature to health records

Revision ID: 5f6d2d28d1ec
Revises: cbffe5b4e4d2
Create Date: 2026-10-13 09:37:31.994317

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f6d2d28d1ec'
down_revision = 'cbffe5b4e4d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('health_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('temperature', sa.Float(), nullable=True))
        # Added by hand: autogenerate doesn't notice a new CheckConstraint
        # on a table that already exists.
        batch_op.create_check_constraint(
            'ck_temperature_range',
            'temperature IS NULL OR (temperature >= 30 AND temperature <= 46)',
        )


def downgrade():
    with op.batch_alter_table('health_records', schema=None) as batch_op:
        # Added by hand: remove the constraint before the column it checks.
        batch_op.drop_constraint('ck_temperature_range', type_='check')
        batch_op.drop_column('temperature')