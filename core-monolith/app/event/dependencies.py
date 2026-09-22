from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.event.repository import SQLAlchemyEventRepository
from app.event.services import EventService
from app.partner.dependencies import get_partner_repository  

def get_event_repo(db: AsyncSession = Depends(get_db)):
    return SQLAlchemyEventRepository(db)

def get_event_service(
    repo = Depends(get_event_repo),
    partner_repo = Depends(get_partner_repository),
):
    return EventService(repo, partner_repo)