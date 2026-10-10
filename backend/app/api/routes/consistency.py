from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import DbSession
from app.db.models import (
    AgentDecision,
    Listing,
    ListingEdit,
    ListingSnapshot,
    OurListing,
    ProductMarketMatch,
    Search,
    SearchListing,
)

router = APIRouter(prefix="/consistency", tags=["consistency"])


class ConsistencyOut(BaseModel):
    searches_without_account: int
    active_our_listings_without_seller: int
    listings_without_search: int
    snapshots_without_source: int
    matches_without_sku: int
    edits_without_owner: int
    proposed_decisions_without_sources: int


@router.get("", response_model=ConsistencyOut)
async def consistency(session: DbSession) -> ConsistencyOut:
    searches_without_account = await session.scalar(
        select(func.count()).select_from(Search).where(Search.account_id.is_(None))
    )
    active_our_without_seller = await session.scalar(
        select(func.count())
        .select_from(OurListing)
        .where(OurListing.is_active, OurListing.account_id.is_(None))
    )
    listings_without_search = await session.scalar(
        select(func.count())
        .select_from(Listing)
        .where(~Listing.id.in_(select(SearchListing.listing_id)))
    )
    snapshots_without_source = await session.scalar(
        select(func.count())
        .select_from(ListingSnapshot)
        .where(
            or_(
                ~ListingSnapshot.search_id.in_(select(Search.id)),
                ~ListingSnapshot.listing_id.in_(select(Listing.id)),
            )
        )
    )
    matches_without_sku = await session.scalar(
        select(func.count())
        .select_from(ProductMarketMatch)
        .where(~ProductMarketMatch.our_sku_id.in_(select(OurListing.sku)))
    )
    edits_without_owner = await session.scalar(
        select(func.count())
        .select_from(ListingEdit)
        .join(OurListing, OurListing.sku == ListingEdit.sku)
        .where(OurListing.account_id.is_(None))
    )
    decisions_without_sources = await session.scalar(
        select(func.count())
        .select_from(AgentDecision)
        .where(
            AgentDecision.status == "proposed",
            ~AgentDecision.payload.has_key("sources"),  # noqa: W601 — PostgreSQL JSONB operator
        )
    )
    return ConsistencyOut(
        searches_without_account=int(searches_without_account or 0),
        active_our_listings_without_seller=int(active_our_without_seller or 0),
        listings_without_search=int(listings_without_search or 0),
        snapshots_without_source=int(snapshots_without_source or 0),
        matches_without_sku=int(matches_without_sku or 0),
        edits_without_owner=int(edits_without_owner or 0),
        proposed_decisions_without_sources=int(decisions_without_sources or 0),
    )
