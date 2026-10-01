"""create outages and fetch runs

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # needed later for geocoded streets and areas
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("records_total", sa.Integer(), nullable=True),
        sa.Column("records_rejected", sa.Integer(), nullable=True),
        sa.Column("records_new", sa.Integer(), nullable=True),
        sa.Column("records_withdrawn", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'ok', 'failed')", name=op.f("ck_fetch_runs_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fetch_runs")),
    )
    op.create_table(
        "outages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("utility", sa.String(length=10), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("place", sa.Text(), nullable=False),
        sa.Column("location_text", sa.Text(), nullable=False),
        sa.Column("outage_type", sa.Text(), nullable=True),
        sa.Column("voltage_level", sa.String(length=20), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_run_id", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_run_id", sa.BigInteger(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("utility IN ('power', 'water')", name=op.f("ck_outages_utility")),
        sa.CheckConstraint("ends_at >= starts_at", name=op.f("ck_outages_ends_after_start")),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"],
            ["fetch_runs.id"],
            name=op.f("fk_outages_first_seen_run_id_fetch_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["fetch_runs.id"],
            name=op.f("fk_outages_last_seen_run_id_fetch_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outages")),
        sa.UniqueConstraint("source", "content_hash", name=op.f("uq_outages_source_content_hash")),
    )
    op.create_index(op.f("ix_outages_starts_at"), "outages", ["starts_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_outages_starts_at"), table_name="outages")
    op.drop_table("outages")
    op.drop_table("fetch_runs")
