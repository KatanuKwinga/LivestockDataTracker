"""Several medicines per health record (the health_medicines table)

Revision ID: 7a2d4f9c1e08
Revises: 5e1b8a3c7f20
Create Date: 2026-11-19

One illness or follow-up can need more than one medicine (an antibiotic
and a painkiller, say), each with its own amount and unit, so they get a
table of their own: one row per medicine given, linked to the health record.
Old records keep their single treatment and dosage boxes as they are.
"""
from alembic import op
import sqlalchemy as sa


revision = "7a2d4f9c1e08"
down_revision = "5e1b8a3c7f20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "health_medicines",
        sa.Column("medicine_id", sa.Integer(), nullable=False),
        sa.Column("h_record_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_health_medicine_amount_positive"),
        sa.CheckConstraint("unit IN ('ml', 'L', 'tablets', 'doses', 'g', 'kg', 'bags', 'bottles', 'sachets')",
                           name="ck_health_medicine_unit"),
        sa.ForeignKeyConstraint(["h_record_id"], ["health_records.h_record_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["pharmacy_items.item_id"]),
        sa.PrimaryKeyConstraint("medicine_id"),
    )
    with op.batch_alter_table("health_medicines", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_health_medicines_h_record_id"), ["h_record_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_health_medicines_item_id"), ["item_id"], unique=False)


def downgrade():
    with op.batch_alter_table("health_medicines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_health_medicines_item_id"))
        batch_op.drop_index(batch_op.f("ix_health_medicines_h_record_id"))
    op.drop_table("health_medicines")