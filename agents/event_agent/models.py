from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class EventCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(min_length=1)
    external_id: str | None = None
    title: str = Field(min_length=1)
    organizer: str | None = None
    description: str | None = None
    topics: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    language_inferred: bool = False
    online: bool | None = None
    url: HttpUrl | None = None
    venue: str | None = None
    city: str | None = None
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    time_note: str | None = None
    cancelled: bool = False

    @model_validator(mode="after")
    def check_times(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    attendance: str = Field(default="any", pattern="^(any|online|in_person)$")
    require_language: bool = True
    require_attendance: bool = False
    nightly_matching: bool = False
    auto_publish: bool = False


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_keys: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=2_147_483_647)


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal["RESET_EVENT_DATA"]


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_ids: list[str] | None = None


class CatalogEntry(BaseModel):
    id: str
    event: EventCandidate


class EventCatalog(BaseModel):
    total: int
    limit: int
    offset: int
    events: list[CatalogEntry]
