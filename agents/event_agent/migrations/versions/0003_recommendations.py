import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table(
        "recommendations",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("event.events.id")),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_published", JSONB()),
        sa.Column("delivery_status", sa.Text(), nullable=False, server_default="pending"),
        schema="event",
    )


def downgrade():
    op.drop_table("recommendations", schema="event")
