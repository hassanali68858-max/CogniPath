import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.add_column("ingestion_runs", sa.Column("limit", sa.Integer()), schema="event")


def downgrade():
    op.drop_column("ingestion_runs", "limit", schema="event")
