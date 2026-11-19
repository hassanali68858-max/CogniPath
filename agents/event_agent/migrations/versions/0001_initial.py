import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS event")
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("preferences", JSONB(), nullable=False),
        schema="event",
    )


def downgrade():
    op.drop_table("user_preferences", schema="event")
