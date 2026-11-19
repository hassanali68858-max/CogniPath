import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"


def upgrade():
    op.add_column("events", sa.Column("knowledge", JSONB()), schema="event")


def downgrade():
    op.drop_column("events", "knowledge", schema="event")
