from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, Table, Text, create_engine, func, select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert

from .models import Preferences

AGENT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=AGENT_DIR / ".env", extra="ignore")

    event_database_url: str
    event_user_tokens: dict[str, SecretStr] = Field(default_factory=dict)
    llm_api_key: SecretStr | None = None
    event_vision_model: str = "gpt-4o-mini"
    collection_agent_model: str = "gpt-4o-mini"
    collection_agent_key: SecretStr | None = None
    collection_agent_base_url: str = "https://api.openai.com/v1"
    recommend_agent_model: str = "gpt-4o-mini"
    recommend_agent_key: SecretStr | None = None
    recommend_agent_base_url: str = "https://api.openai.com/v1"
    poster_agent_model: str | None = None
    poster_agent_key: SecretStr | None = None
    poster_agent_base_url: str = "https://api.openai.com/v1"
    event_operator_token: SecretStr | None = None
    event_planner_url: str = "http://127.0.0.1:8000"
    event_nightly_hour: int = Field(2, ge=0, le=23)
    event_nightly_minute: int = Field(0, ge=0, le=59)

    @field_validator("event_user_tokens")
    @classmethod
    def distinct_tokens(cls, tokens: dict[str, SecretStr]) -> dict[str, SecretStr]:
        values = [token.get_secret_value() for token in tokens.values()]
        if "" in values or len(values) != len(set(values)):
            raise ValueError("each user must have a distinct nonempty token")
        return tokens


metadata = MetaData(schema="event")
preferences = Table(
    "user_preferences",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("preferences", JSONB, nullable=False),
)

sources = Table(
    "sources", metadata,
    Column("key", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("adapter", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, server_default="true"),
)
events = Table(
    "events", metadata,
    Column("id", Text, primary_key=True),
    Column("fingerprint", Text, index=True),
    Column("details", JSONB, nullable=False),
    Column("knowledge", JSONB),
)
source_events = Table(
    "source_events", metadata,
    Column("source_key", ForeignKey(sources.c.key), primary_key=True),
    Column("external_key", Text, primary_key=True),
    Column("event_id", ForeignKey(events.c.id), nullable=False),
    Column("details", JSONB, nullable=False),
)
runs = Table(
    "ingestion_runs", metadata,
    Column("id", Text, primary_key=True),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("source_keys", JSONB, nullable=False),
    Column("results", JSONB, nullable=False),
    Column("nightly_date", Date, unique=True),
    Column("source_status", Text),
    Column("matching", JSONB),
    Column("limit", Integer),
)
recommendations = Table(
    "recommendations", metadata,
    Column("user_id", Text, primary_key=True),
    Column("id", Text, primary_key=True),
    Column("event_id", ForeignKey(events.c.id)),
    Column("result", JSONB, nullable=False),
    Column("current", Boolean, nullable=False),
    Column("scored_at", DateTime(timezone=True), nullable=False),
    Column("last_published", JSONB),
    Column("delivery_status", Text, nullable=False, server_default="pending"),
)
poster_uploads = Table(
    "poster_uploads", metadata,
    Column("id", Text, primary_key=True),
    Column("user_id", Text, nullable=False),
    Column("share_events", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def get_preferences(conn, user_id: str) -> Preferences | None:
    data = conn.execute(
        select(preferences.c.preferences).where(preferences.c.user_id == user_id)
    ).scalar_one_or_none()
    return Preferences.model_validate(data) if data is not None else None


def save_preferences(conn, user_id: str, values: Preferences) -> None:
    statement = insert(preferences).values(user_id=user_id, preferences=values.model_dump())
    conn.execute(statement.on_conflict_do_update(
        index_elements=[preferences.c.user_id],
        set_={"preferences": statement.excluded.preferences},
    ))


if __name__ == "__main__":
    config = Config()
    config.set_main_option("script_location", str(AGENT_DIR / "migrations"))
    with create_engine(Settings().event_database_url).begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
