from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]

__all__ = ["DbSession", "get_db"]
