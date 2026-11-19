import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"


def upgrade():
    source_table = op.create_table(
        "sources",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("adapter", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="event",
    )
    op.bulk_insert(source_table, [{
        "key": "keski-suomi",
        "name": "Keski-Suomi Events",
        "url": (
            "https://keskisuomievents.fi/api/v1/event?include=location%2Carea%2Ckeywords"
            "&page=1&page_size=100&super_event_type=none%2Cumbrella&start=today"
        ),
        "adapter": "linked_events",
        "enabled": True,
    }])
    op.create_table(
        "events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("fingerprint", sa.Text()),
        sa.Column("details", JSONB(), nullable=False),
        schema="event",
    )
    op.create_index("ix_event_events_fingerprint", "events", ["fingerprint"], schema="event")
    op.create_table(
        "source_events",
        sa.Column("source_key", sa.Text(), sa.ForeignKey("event.sources.key"), primary_key=True),
        sa.Column("external_key", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("event.events.id"), nullable=False),
        sa.Column("details", JSONB(), nullable=False),
        schema="event",
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_keys", JSONB(), nullable=False),
        sa.Column("results", JSONB(), nullable=False),
        schema="event",
    )


def downgrade():
    for table in ("ingestion_runs", "source_events", "events", "sources"):
        op.drop_table(table, schema="event")
