from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from trip.catalog import INTERESTS, TRANSPORT_MODES, TRAVELER_TYPES, VISA_TYPES

MAX_NIGHTS = 30


class Comfort(str, Enum):
    auto = "auto"
    economy = "economy"
    standard = "standard"
    luxury = "luxury"


class Scope(str, Enum):
    both = "both"
    domestic = "domestic"
    international = "international"


class TierPrices(BaseModel):
    economy: float = Field(ge=0)
    standard: float = Field(ge=0)
    luxury: float = Field(ge=0)


class Attraction(BaseModel):
    name: str
    tag: str

    @field_validator("tag")
    @classmethod
    def _tag(cls, v: str) -> str:
        if v not in INTERESTS:
            raise ValueError(f"unknown tag: {v}")
        return v


class Destination(BaseModel):
    id: str
    name: str
    country: str
    scope: Scope
    summary: str
    tags: dict[str, float]
    good_for: list[str]
    season: list[int] = Field(min_length=12, max_length=12, description="1-5 score per Gregorian month")
    min_days: int = Field(ge=1)
    max_days: int = Field(ge=1)
    lodging_usd: TierPrices = Field(description="Per room per night")
    daily_usd: TierPrices = Field(description="Per person per day: food, local transport, activities")
    transport_usd: float = Field(ge=0, description="Round trip per adult from Tehran")
    transport_mode: str
    travel_hours: float = Field(ge=0)
    visa: str
    visa_cost_usd: float = Field(ge=0)
    attractions: list[Attraction] = Field(min_length=1)
    tips: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: dict[str, float]) -> dict[str, float]:
        bad = [k for k in v if k not in INTERESTS]
        if bad:
            raise ValueError(f"unknown tags: {bad}")
        if any(not 0 <= w <= 1 for w in v.values()):
            raise ValueError("tag weights must be between 0 and 1")
        return v

    @field_validator("good_for")
    @classmethod
    def _good_for(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in TRAVELER_TYPES]
        if bad:
            raise ValueError(f"unknown traveler types: {bad}")
        return v

    @field_validator("season")
    @classmethod
    def _season(cls, v: list[int]) -> list[int]:
        if any(not 1 <= s <= 5 for s in v):
            raise ValueError("season scores must be 1-5")
        return v

    @field_validator("visa")
    @classmethod
    def _visa(cls, v: str) -> str:
        if v not in VISA_TYPES:
            raise ValueError(f"unknown visa type: {v}")
        return v

    @field_validator("transport_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in TRANSPORT_MODES:
            raise ValueError(f"unknown transport mode: {v}")
        return v

    @model_validator(mode="after")
    def _days(self) -> "Destination":
        if self.max_days < self.min_days:
            raise ValueError("max_days must be >= min_days")
        return self


class TripRequest(BaseModel):
    budget: int = Field(gt=0, le=1_000_000_000_000, description="Total budget in toman")
    start_date: date
    end_date: date
    adults: int = Field(ge=1, le=20)
    children: int = Field(default=0, ge=0, le=10)
    traveler_type: str = "couple"
    interests: list[str] = Field(default_factory=list)
    scope: Scope = Scope.both
    comfort: Comfort = Comfort.auto
    visa_free_only: bool = False
    max_travel_hours: float | None = Field(default=None, gt=0)
    usd_rate: int = Field(gt=0, le=100_000_000, description="Toman per US dollar")
    limit: int = Field(default=12, ge=1, le=50)

    @field_validator("traveler_type")
    @classmethod
    def _traveler(cls, v: str) -> str:
        if v not in TRAVELER_TYPES:
            raise ValueError(f"unknown traveler type: {v}")
        return v

    @field_validator("interests")
    @classmethod
    def _interests(cls, v: list[str]) -> list[str]:
        bad = [i for i in v if i not in INTERESTS]
        if bad:
            raise ValueError(f"unknown interests: {bad}")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _dates(self) -> "TripRequest":
        nights = (self.end_date - self.start_date).days
        if nights < 1:
            raise ValueError("end_date must be after start_date")
        if nights > MAX_NIGHTS:
            raise ValueError(f"trips longer than {MAX_NIGHTS} nights are not supported")
        return self

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def days(self) -> int:
        return self.nights + 1


class CostBreakdown(BaseModel):
    transport: int
    lodging: int
    daily: int
    visa: int
    contingency: int
    total: int
    per_person: int
    rooms: int


class DayPlan(BaseModel):
    day: int
    date_label: str
    title: str
    activities: list[str]


class Recommendation(BaseModel):
    id: str
    name: str
    country: str
    scope: str
    summary: str
    score: float
    comfort: str
    comfort_label: str
    over_budget: bool
    cost: CostBreakdown
    visa: str
    visa_label: str
    transport_label: str
    travel_hours: float
    season_score: float
    season_label: str
    reasons: list[str]
    warnings: list[str]
    attractions: list[str]
    itinerary: list[DayPlan]
    tips: list[str]


class TripResponse(BaseModel):
    nights: int
    days: int
    travelers: int
    nowruz: bool
    considered: int
    excluded: dict[str, int]
    recommendations: list[Recommendation]
    cheapest_excluded: list[dict]
    notes: list[str]
