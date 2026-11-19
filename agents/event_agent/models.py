from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class EventCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(min_length=1)
    external_id: str | None = None
    title: str = Field(min_length=1)
    organizer: str | None = None
    topics: list[str] = Field(default_factory=list)
    url: HttpUrl | None = None
    venue: str | None = None
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None

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
    nightly_matching: bool = False
    auto_publish: bool = False
