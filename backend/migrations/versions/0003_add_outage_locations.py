# geoalchemy2 adds the *_geospatial_* operations to alembic at runtime
# mypy: disable-error-code="attr-defined"
"""add outage locations

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_geospatial_table(
        "outage_locations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("outage_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column(
            "numbers", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("within", sa.Text(), nullable=True),
        sa.Column("matched_name", sa.Text(), nullable=True),
        sa.Column("match_method", sa.String(length=20), nullable=True),
        sa.Column("match_widened", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approximate", sa.Boolean(), nullable=False),
        sa.Column(
            "geom",
            Geometry(
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "kind IN ('street', 'settlement', 'neighborhood', 'municipality')",
            name=op.f("ck_outage_locations_kind"),
        ),
        sa.CheckConstraint(
            "match_method IN ('exact', 'abbreviation', 'fuzzy')",
            name=op.f("ck_outage_locations_match_method"),
        ),
        sa.ForeignKeyConstraint(
            ["outage_id"],
            ["outages.id"],
            name=op.f("fk_outage_locations_outage_id_outages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outage_locations")),
        sa.UniqueConstraint(
            "outage_id", "position", name=op.f("uq_outage_locations_outage_id_position")
        ),
    )
    op.create_geospatial_index(
        "idx_outage_locations_geom",
        "outage_locations",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.add_column("outages", sa.Column("located_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outages", sa.Column("locator_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("outages", "locator_version")
    op.drop_column("outages", "located_at")
    op.drop_geospatial_index(
        "idx_outage_locations_geom",
        table_name="outage_locations",
        postgresql_using="gist",
        column_name="geom",
    )
    op.drop_geospatial_table("outage_locations")
