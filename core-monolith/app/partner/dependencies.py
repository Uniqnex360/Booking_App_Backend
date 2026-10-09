from app.partner.interfaces import IPartnerRepository
from app.partner.repository import SQLAlchemyPartnerRepository
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain
from app.core.database import get_db
from app.partner.interfaces import IPartnerRepository
from app.partner.services import PartnerService
from app.partner.interfaces import Partner
from app.partner.exceptions import PartnerNotApprovedHTTP
from app.partner.interfaces import PartnerStatus
from app.shared.exceptions import EntityNotFoundError
def get_partner_repository(db:AsyncSession=Depends(get_db))->IPartnerRepository:
    return SQLAlchemyPartnerRepository(db)
def get_partner_service(repo:IPartnerRepository=Depends(get_partner_repository))->PartnerService:
    return PartnerService(repo)
async def required_approved_partner(current_user:AuthUserDomain=Depends(get_current_user),partner_service:PartnerService=Depends(get_partner_service))->Partner:
    try:
        partner=await partner_service.get_partner_by_user_id(current_user.id)
        if partner.status!=PartnerStatus.APPROVED:
            raise PartnerNotApprovedHTTP()
        return partner
    except EntityNotFoundError:
        raise PartnerNotApprovedHTTP()
    