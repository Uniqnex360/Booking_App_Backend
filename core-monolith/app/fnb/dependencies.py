from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.fnb.repository import SQLAlchemyFnbRepository
from app.fnb.services import FnbService


def get_fnb_service(session: AsyncSession = Depends(get_db)) -> FnbService:
    return FnbService(session=session, repo=SQLAlchemyFnbRepository(session=session))