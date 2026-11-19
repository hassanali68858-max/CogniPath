import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"


def upgrade():
    op.add_column("ingestion_runs", sa.Column("nightly_date", sa.Date()), schema="event")
    op.add_column("ingestion_runs", sa.Column("source_status", sa.Text()), schema="event")
    op.add_column("ingestion_runs", sa.Column("matching", JSONB()), schema="event")
    op.create_unique_constraint("uq_ingestion_nightly_date", "ingestion_runs", ["nightly_date"], schema="event")


def downgrade():
    op.drop_constraint("uq_ingestion_nightly_date", "ingestion_runs", schema="event", type_="unique")
    for column in ("matching", "source_status", "nightly_date"):
        op.drop_column("ingestion_runs", column, schema="event")
