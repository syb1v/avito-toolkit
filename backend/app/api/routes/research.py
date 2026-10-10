from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.web_research import research_product_identity

router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=255)


class SourceOut(BaseModel):
    url: str
    title: str
    retrieved_at: str
    claims: list[str]


class ResearchOut(BaseModel):
    query: str
    status: str
    sources: list[SourceOut]


@router.post("/product", response_model=ResearchOut)
async def research_product(payload: ResearchRequest) -> ResearchOut:
    result = await research_product_identity(payload.query)
    return ResearchOut(
        query=result.query,
        status=result.status,
        sources=[
            SourceOut(
                url=source.url,
                title=source.title,
                retrieved_at=source.retrieved_at.isoformat(),
                claims=list(source.claims),
            )
            for source in result.sources
        ],
    )
