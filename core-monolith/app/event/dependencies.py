from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.event.repository import SQLAlchemyEventRepository
from app.event.services import EventService

def get_event_repo(db: AsyncSession = Depends(get_db)):
    return SQLAlchemyEventRepository(db)

def get_event_service(repo = Depends(get_event_repo)):
    return EventService(repo)