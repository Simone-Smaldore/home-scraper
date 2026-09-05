"""listing, price_history, review, scrape_run

Revision ID: 0001_listings
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_listings"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price_eur", sa.Integer()),
        sa.Column("size_sqm", sa.Integer()),
        sa.Column("rooms", sa.Integer()),
        sa.Column("bathrooms", sa.Integer()),
        sa.Column("floor", sa.Integer()),
        sa.Column("floor_raw", sa.String(length=120)),
        sa.Column("is_last_floor", sa.Boolean()),
        sa.Column("elevator", sa.Boolean()),
        sa.Column("balcony", sa.Boolean()),
        sa.Column("garage", sa.String(length=32)),
        sa.Column("condition", sa.String(length=32)),
        sa.Column("energy_class", sa.String(length=32)),
        sa.Column("heating", sa.String(length=64)),
        sa.Column("is_auction", sa.Boolean(), nullable=False),
        sa.Column("zone", sa.String(length=64)),
        sa.Column("zone_raw", sa.String(length=120)),
        sa.Column("address", sa.Text()),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("is_private", sa.Boolean()),
        sa.Column("advertiser_name", sa.Text()),
        sa.Column("phone", sa.String(length=120)),
        sa.Column("images", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missed_runs", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("passes_hard_filter", sa.Boolean(), nullable=False),
        sa.Column("filter_rejections", sa.JSON(), nullable=False),
        sa.Column("filter_unknowns", sa.JSON(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source", "source_id", name="uq_listing_source_id"),
    )
    op.create_index(
        "ix_listing_dashboard", "listing", ["is_active", "passes_hard_filter", "first_seen_at"]
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "listing_id",
            sa.Integer(),
            sa.ForeignKey("listing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price_eur", sa.Integer()),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_history_listing_id", "price_history", ["listing_id"])

    op.create_table(
        "review",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "listing_id",
            sa.Integer(),
            sa.ForeignKey("listing.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "scrape_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("full", sa.Boolean(), nullable=False),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("new", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("price_changes", sa.Integer(), nullable=False),
        sa.Column("deactivated", sa.Integer(), nullable=False),
        sa.Column("evaluated", sa.Integer(), nullable=False),
        sa.Column("model_used", sa.String(length=64)),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_scrape_run_source", "scrape_run", ["source"])


def downgrade() -> None:
    op.drop_index("ix_scrape_run_source", table_name="scrape_run")
    op.drop_table("scrape_run")
    op.drop_table("review")
    op.drop_index("ix_price_history_listing_id", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("ix_listing_dashboard", table_name="listing")
    op.drop_table("listing")
