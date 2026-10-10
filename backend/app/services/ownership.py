import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AvitoAccount, OurListing


async def require_seller(session: AsyncSession, listing: OurListing) -> AvitoAccount:
    account = (
        await session.get(AvitoAccount, listing.account_id)
        if listing.account_id is not None
        else None
    )
    if account is None or account.role != "seller":
        raise HTTPException(status_code=409, detail="SKU не привязан к аккаунту-продавцу")
    return account


def edit_owner_matches(listing_owner: uuid.UUID | None, edit_owner: uuid.UUID | None) -> bool:
    return listing_owner is not None and listing_owner == edit_owner
