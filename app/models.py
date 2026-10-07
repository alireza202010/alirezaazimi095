from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.catalog import CATEGORIES, LINK_TYPES, PRODUCTS, PUBLISHER_TYPES


class Goal(str, Enum):
    ranking = "ranking"
    branding = "branding"
    traffic = "traffic"
    local = "local"


class Risk(str, Enum):
    conservative = "conservative"
    balanced = "balanced"
    aggressive = "aggressive"


class Publisher(BaseModel):
    """One purchasable offer on a publisher site (one row of the inventory CSV)."""

    id: str
    name: str
    domain: str
    type: str
    categories: list[str]
    product: str
    price: int = Field(gt=0, description="Price in toman")
    authority: int = Field(ge=0, le=100)
    monthly_traffic: int = Field(ge=0)
    outbound_per_month: int = Field(ge=0, description="Sponsored posts published per month")
    index_rate: float = Field(ge=0, le=1)
    link_type: str
    permanent: bool

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in PUBLISHER_TYPES:
            raise ValueError(f"unknown publisher type: {v}")
        return v

    @field_validator("product")
    @classmethod
    def _product(cls, v: str) -> str:
        if v not in PRODUCTS:
            raise ValueError(f"unknown product: {v}")
        return v

    @field_validator("link_type")
    @classmethod
    def _link_type(cls, v: str) -> str:
        if v not in LINK_TYPES:
            raise ValueError(f"unknown link type: {v}")
        return v

    @field_validator("categories")
    @classmethod
    def _categories(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown categories: {bad}")
        if not v:
            raise ValueError("at least one category is required")
        return v


class KeywordTarget(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)


class PlanRequest(BaseModel):
    site_url: str = Field(min_length=3, max_length=300)
    brand_name: str | None = Field(default=None, max_length=100)
    budget: int = Field(gt=0, le=100_000_000_000, description="Total budget in toman")
    months: int = Field(ge=1, le=12)
    category: str
    keywords: list[KeywordTarget] = Field(min_length=1, max_length=20)
    goal: Goal = Goal.ranking
    risk: Risk = Risk.balanced
    allowed_types: list[str] | None = None
    permanent_only: bool = False
    dofollow_only: bool = False

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"unknown category: {v}")
        return v

    @field_validator("allowed_types")
    @classmethod
    def _allowed(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        bad = [t for t in v if t not in PUBLISHER_TYPES]
        if bad:
            raise ValueError(f"unknown publisher types: {bad}")
        return v or None


class PlanItem(BaseModel):
    month: int
    month_label: str
    publisher_id: str
    publisher_name: str
    domain: str
    type: str
    type_label: str
    product: str
    product_label: str
    price: int
    link_type: str
    permanent: bool
    authority: int
    monthly_traffic: int
    quality: float
    relevance: float
    spam_risk: float
    keyword: str
    target_url: str
    anchor_type: str
    anchor_type_label: str
    anchor_text: str
    brief_title: str
    reasons: list[str]
    cautions: list[str]


class MonthSummary(BaseModel):
    month: int
    label: str
    count: int
    cost: int


class Scenario(BaseModel):
    key: str
    title: str
    description: str
    budget: int
    total_cost: int
    remaining: int
    item_count: int
    avg_quality: float
    items: list[PlanItem]
    type_breakdown: dict[str, int]
    anchor_breakdown: dict[str, int]
    monthly: list[MonthSummary]
    warnings: list[str]


class PlanResponse(BaseModel):
    total_offers: int
    eligible_offers: int
    excluded: dict[str, int]
    scenarios: list[Scenario]
    notes: list[str]
