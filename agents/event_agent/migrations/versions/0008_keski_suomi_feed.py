import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"

FEED_URL = "https://keskisuomievents.fi/api/v1/event"
OLD_QUERY = "?include=location%2Carea%2Ckeywords&page=1&page_size=100&super_event_type=none%2Cumbrella&start=today"
NEW_QUERY = "?include=location%2Carea&page=1&page_size=500&super_event_type=none%2Cumbrella"


def upgrade():
    update_source(NEW_QUERY)


def downgrade():
    update_source(OLD_QUERY)


def update_source(query):
    op.get_bind().execute(
        sa.text("UPDATE event.sources SET url = :url WHERE key = 'keski-suomi'"),
        {"url": FEED_URL + query},
    )
