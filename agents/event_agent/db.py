from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Column, MetaData, Table, Text, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from .models import Preferences

AGENT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=AGENT_DIR / ".env", extra="ignore")

    event_database_url: str
    event_user_tokens: dict[str, SecretStr] = Field(default_factory=dict)
    llm_api_key: SecretStr | None = None

    @field_validator("event_user_tokens")
    @classmethod
    def distinct_tokens(cls, tokens: dict[str, SecretStr]) -> dict[str, SecretStr]:
        values = [token.get_secret_value() for token in tokens.values()]
        if "" in values or len(values) != len(set(values)):
            raise ValueError("each user must have a distinct nonempty token")
        return tokens


preferences = Table(
    "user_preferences",
    MetaData(schema="event"),
    Column("user_id", Text, primary_key=True),
    Column("preferences", JSONB, nullable=False),
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
