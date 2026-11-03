"""Add departures table (animals that left the farm without a sale or death)

Revision ID: a3f1c9e27b64
Revises: d478ab7f40b3
Create Date: 2026-11-02 16:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f1c9e27b64'
down_revision = 'd478ab7f40b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'departures',
        sa.Column('departure_id', sa.Integer(), nullable=False),
        sa.Column('animal_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['animal_id'], ['livestock.animal_id']),
        sa.PrimaryKeyConstraint('departure_id'),
        sa.UniqueConstraint('animal_id'),
    )


def downgrade():
    op.drop_table('departures')