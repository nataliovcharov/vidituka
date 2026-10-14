# geoalchemy2 adds the *_geospatial_* operations to alembic at runtime
# mypy: disable-error-code="attr-defined"
"""add gazetteer tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_geospatial_table(
        "admin_areas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("osm_id", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("alt_names", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("municipality_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "geom",
            Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.CheckConstraint("level IN (2, 6, 7, 8, 9)", name=op.f("ck_admin_areas_level")),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["admin_areas.id"],
            name=op.f("fk_admin_areas_municipality_id_admin_areas"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_areas")),
        sa.UniqueConstraint("osm_id", name=op.f("uq_admin_areas_osm_id")),
    )
    op.create_geospatial_index(
        "idx_admin_areas_geom",
        "admin_areas",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(
        op.f("ix_admin_areas_level_name_key"), "admin_areas", ["level", "name_key"], unique=False
    )
    op.create_table(
        "gazetteer_loads",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("areas", sa.Integer(), nullable=False),
        sa.Column("places", sa.Integer(), nullable=False),
        sa.Column("streets", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gazetteer_loads")),
    )
    op.create_geospatial_table(
        "places",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("osm_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("alt_names", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("municipality_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "geom",
            Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["admin_areas.id"],
            name=op.f("fk_places_municipality_id_admin_areas"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_places")),
        sa.UniqueConstraint("osm_id", name=op.f("uq_places_osm_id")),
    )
    op.create_geospatial_index(
        "idx_places_geom",
        "places",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(op.f("ix_places_name_key"), "places", ["name_key"], unique=False)
    op.create_geospatial_table(
        "streets",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("alt_names", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("municipality_id", sa.BigInteger(), nullable=False),
        sa.Column("settlement_id", sa.BigInteger(), nullable=True),
        sa.Column("osm_way_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column(
            "geom",
            Geometry(
                geometry_type="MULTILINESTRING",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["admin_areas.id"],
            name=op.f("fk_streets_municipality_id_admin_areas"),
        ),
        sa.ForeignKeyConstraint(
            ["settlement_id"], ["admin_areas.id"], name=op.f("fk_streets_settlement_id_admin_areas")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_streets")),
        sa.UniqueConstraint(
            "municipality_id",
            "settlement_id",
            "name_key",
            name=op.f("uq_streets_municipality_id_settlement_id_name_key"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_geospatial_index(
        "idx_streets_geom",
        "streets",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(op.f("ix_streets_name_key"), "streets", ["name_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_streets_name_key"), table_name="streets")
    op.drop_geospatial_index(
        "idx_streets_geom", table_name="streets", postgresql_using="gist", column_name="geom"
    )
    op.drop_geospatial_table("streets")
    op.drop_index(op.f("ix_places_name_key"), table_name="places")
    op.drop_geospatial_index(
        "idx_places_geom", table_name="places", postgresql_using="gist", column_name="geom"
    )
    op.drop_geospatial_table("places")
    op.drop_table("gazetteer_loads")
    op.drop_index(op.f("ix_admin_areas_level_name_key"), table_name="admin_areas")
    op.drop_geospatial_index(
        "idx_admin_areas_geom",
        table_name="admin_areas",
        postgresql_using="gist",
        column_name="geom",
    )
    op.drop_geospatial_table("admin_areas")
