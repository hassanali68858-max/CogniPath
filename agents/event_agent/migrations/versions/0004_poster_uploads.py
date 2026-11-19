import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table(
        "poster_uploads",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("share_events", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="event",
    )
    op.execute(
        "INSERT INTO event.sources (key, name, url, adapter, enabled) "
        "VALUES ('poster', 'Shared board uploads', '', 'poster', false) ON CONFLICT (key) DO NOTHING"
    )


def downgrade():
    op.drop_table("poster_uploads", schema="event")
