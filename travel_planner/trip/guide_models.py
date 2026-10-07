from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CATEGORIES: dict[str, str] = {
    "thrill": "هیجان و ماجراجویی",
    "history": "تاریخی و فرهنگی",
    "pilgrimage": "زیارت و فضای معنوی",
    "nature": "طبیعت و هوای تازه",
    "fun": "تفریح و سرگرمی خانوادگی",
    "shopping": "خرید و بازارگردی",
    "food": "غذا و رستوران",
    "relaxation": "آرامش و حال خوب",
    "museum": "موزه‌گردی",
    "night": "گشت شبانه",
}

GROUPS: dict[str, str] = {
    "solo": "تنها",
    "couple": "زوج",
    "friends": "با دوستان",
    "family_kids": "خانواده با بچه",
    "family_elderly": "همراه سالمند",
}

BUDGETS: dict[str, str] = {
    "economy": "فقط جاهای رایگان یا ارزان",
    "moderate": "متوسط",
    "premium": "محدودیتی ندارم",
}

SEASONS: dict[str, str] = {"spring": "بهار", "summer": "تابستان", "autumn": "پاییز", "winter": "زمستان"}

PACES: dict[str, str] = {"relaxed": "آرام و بی‌عجله", "balanced": "متعادل", "packed": "فشرده، همه‌جا را ببینم"}

PRICES: dict[str, str] = {"free": "رایگان", "low": "ارزان", "mid": "متوسط", "high": "گران"}
PRICE_RANK = {"free": 0, "low": 1, "mid": 2, "high": 3}
MAX_PRICE = {"economy": 1, "moderate": 2, "premium": 3}

TIMES: dict[str, str] = {
    "morning": "صبح", "afternoon": "بعدازظهر", "evening": "عصر و غروب", "night": "شب", "any": "هر زمان",
}
TIME_ORDER = {"morning": 0, "any": 1, "afternoon": 2, "evening": 3, "night": 4}


class Place(BaseModel):
    id: str
    name: str
    categories: list[str] = Field(min_length=1)
    price: Literal["free", "low", "mid", "high"]
    hours: float = Field(gt=0, le=12)
    best_time: Literal["morning", "afternoon", "evening", "night", "any"]
    area: str
    trip: Literal["city", "half_day", "full_day"] = "city"
    kids: bool = True
    elderly: bool = True
    indoor: bool = False
    popularity: int = Field(ge=1, le=3)
    description: str
    tip: str | None = None
    seasons: list[str]

    @field_validator("categories")
    @classmethod
    def _cats(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown categories: {bad}")
        return v

    @field_validator("seasons")
    @classmethod
    def _seasons(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in SEASONS]
        if bad or not v:
            raise ValueError(f"invalid seasons: {v}")
        return v


class City(BaseModel):
    id: str
    name: str
    aliases: list[str]
    intro: str
    foods: list[str]
    tips: list[str]
    hot_seasons: list[str] = Field(default_factory=list)
    cold_seasons: list[str] = Field(default_factory=list)
    places: list[Place] = Field(min_length=1)

    @property
    def categories(self) -> list[str]:
        present = {c for p in self.places for c in p.categories}
        return [c for c in CATEGORIES if c in present]


class CitySummary(BaseModel):
    id: str
    name: str
    intro: str
    categories: list[str]
    place_count: int


class GuideRequest(BaseModel):
    city: str
    days: int = Field(ge=1, le=7)
    group: str = "couple"
    interests: list[str] = Field(default_factory=list)
    budget: str = "moderate"
    season: str = "spring"
    pace: str = "balanced"

    @field_validator("group")
    @classmethod
    def _group(cls, v: str) -> str:
        if v not in GROUPS:
            raise ValueError(f"unknown group: {v}")
        return v

    @field_validator("interests")
    @classmethod
    def _interests(cls, v: list[str]) -> list[str]:
        bad = [i for i in v if i not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown interests: {bad}")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _choices(self) -> "GuideRequest":
        for value, options, name in ((self.budget, BUDGETS, "budget"), (self.season, SEASONS, "season"),
                                     (self.pace, PACES, "pace")):
            if value not in options:
                raise ValueError(f"unknown {name}: {value}")
        return self


class PlaceSuggestion(BaseModel):
    id: str
    name: str
    pitch: str
    description: str
    categories: list[str]
    category_labels: list[str]
    price: str
    price_label: str
    hours: float
    best_time_label: str
    area: str
    trip: str
    kids: bool
    indoor: bool
    score: float
    tips: list[str]


class InterestSection(BaseModel):
    interest: str
    label: str
    headline: str
    places: list[PlaceSuggestion]


class GuideDay(BaseModel):
    day: int
    title: str
    hours: float
    places: list[PlaceSuggestion]


class GuideResponse(BaseModel):
    city: str
    city_name: str
    intro: str
    sections: list[InterestSection]
    must_see: list[PlaceSuggestion]
    itinerary: list[GuideDay]
    left_out: list[str]
    foods: list[str]
    tips: list[str]
    excluded: dict[str, list[str]]
