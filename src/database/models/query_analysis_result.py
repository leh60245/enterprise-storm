from typing import Literal

from pydantic import BaseModel, Field


class QueryAnalysisResult(BaseModel):
    intent: Literal["factoid", "analytical", "comparison", "general"] = Field(..., description="Query intent: 'factoid' (simple facts) or 'analytical' (trends, comparison, financial)")
    target_companies: list[str] = Field(default_factory=list, description="List of specific company names mentioned or implied. Max 5 companies. e.g., ['Samsung Electronics', 'SK Hynix']")
    is_competitor_query: bool = Field(
        False,
        description="True if the user asks about competitors, rankings, or industry peers."
    )
    time_period: str | None = Field(None, description="Time period mentioned (e.g., '2023', 'Q4', 'recent')")
    keywords: list[str] = Field(default_factory=list, description="Key search terms extracted for vector search")
