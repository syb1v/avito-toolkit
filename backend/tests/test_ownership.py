import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.db.models import AvitoAccount, OurListing
from app.services.ownership import edit_owner_matches, require_seller


@pytest.mark.asyncio
async def test_searcher_cannot_own_price_edit() -> None:
    owner = uuid.uuid4()
    session = AsyncMock()
    session.get.return_value = AvitoAccount(id=owner, role="searcher")
    with pytest.raises(HTTPException) as error:
        await require_seller(session, OurListing(sku="one", account_id=owner))
    assert error.value.status_code == 409


def test_edit_owner_must_be_explicit_and_equal() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    assert edit_owner_matches(first, first)
    assert not edit_owner_matches(first, second)
    assert not edit_owner_matches(None, None)
