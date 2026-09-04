import uuid
from typing import Optional,List,Tuple
from app.shared.exceptions import DuplicateEntityError

from app.partner.interfaces import (
    IPartnerRepository, Partner, PartnerStatus, PartnerType,EntityNotFoundError,
    InvalidStatusTransitionError
)
from datetime import datetime
class PartnerService:
        def __init__(self, partner_repo: IPartnerRepository):
            self.partner_repo=partner_repo
        
        # app/partner/services.py

        async def register_partner(self, user_id: uuid.UUID, data: dict) -> Partner:
            # 1. Check if the user already has a partner record
            existing_partner = await self.partner_repo.get_by_user_id(user_id)
            
            if existing_partner:
                # 2. If they were REJECTED, allow them to update their details and re-apply
                if existing_partner.status == PartnerStatus.REJECTED:
                    # Update fields
                    existing_partner.business_name = data.get('business_name')
                    existing_partner.partner_type = PartnerType(data.get('partner_type'))
                    existing_partner.contact_name = data.get('contact_name')
                    existing_partner.contact_phone = data.get('contact_phone')
                    existing_partner.city = data.get('city')
                    existing_partner.gst_number = data.get('gst_number')
                    existing_partner.pan_number = data.get('pan_number')
                    
                    # Reset status to PENDING so admin sees it again
                    existing_partner.status = PartnerStatus.PENDING_APPROVAL
                    existing_partner.rejection_reason = None
                    
                    return await self.partner_repo.update(existing_partner)
                
                # 3. If they are already Approved or Pending, raise the conflict error
                raise DuplicateEntityError("A partner account already exists for this user.")

            # 4. If no record exists, create a new one
            partner = Partner(
                id=uuid.uuid4(),
                user_id=user_id,
                status=PartnerStatus.PENDING_APPROVAL,
                commission_rate=10.0,
                **data
            )
            return await self.partner_repo.create(partner)
        async def get_partner_by_user_id(self,user_id:uuid.UUID)->Partner:
            partner=await self.partner_repo.get_by_user_id(user_id)
            if not partner:
                raise EntityNotFoundError('Partner profile not found')
            return partner
        
        async def list_partners(self,status:Optional[str],partner_type:Optional[str],page:int,limit:int)->Tuple[List[Partner],int]:
            p_status=PartnerStatus(status) if status else None
            p_type=PartnerType(partner_type) if partner_type else None
            return await self.partner_repo.list_by_filters(p_status,p_type,page,limit)
        def _is_valid_transition(self,from_status:PartnerStatus,to_status:PartnerStatus)-> bool:
            valid_transactions={
                PartnerStatus.PENDING_APPROVAL:[PartnerStatus.APPROVED,PartnerStatus.REJECTED],
                PartnerStatus.APPROVED:[PartnerStatus.SUSPENDED],
                PartnerStatus.SUSPENDED:[PartnerStatus.APPROVED],
                PartnerStatus.REJECTED:[PartnerStatus.PENDING_APPROVAL]
            }
            allowed=valid_transactions.get(from_status,[])
            return to_status in allowed

        async def update_partner_status(self,partner_id:uuid.UUID,new_status:PartnerStatus,admin_id:uuid.UUID,rejection_reason:Optional[str]=None)->Partner:
            partner=await self.partner_repo.get_by_id(partner_id)
            if not partner:
                raise EntityNotFoundError('Partner not found')
            if not self._is_valid_transition(partner.status,new_status):
                raise InvalidStatusTransitionError(partner.status,new_status)
            partner.status=new_status
            if new_status==PartnerStatus.APPROVED:
                partner.approved_at=datetime.utcnow()
                partner.approved_by=admin_id
            if new_status==PartnerStatus.REJECTED:
                partner.rejection_reason=rejection_reason
            return await self.partner_repo.update(partner)            
            