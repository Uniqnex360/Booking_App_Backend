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

        async def get_revenue_report(
            self, partner_id: uuid.UUID, from_date: Optional[str] = None, to_date: Optional[str] = None
        ) -> dict:
            import logging
            from datetime import datetime as dt, timedelta
            from sqlalchemy import select, func, and_, or_
            from app.booking.models import BookingModel
            from app.event.models import EventORM
            from app.movie.models import Showtime

            logger = logging.getLogger(__name__)

            try:
                session = self.partner_repo.session

                # 1. Find all event IDs owned by this partner
                event_ids_stmt = select(EventORM.id).where(EventORM.partner_id == partner_id)
                event_ids = (await session.execute(event_ids_stmt)).scalars().all()

                # 2. Find all showtime IDs owned by this partner
                showtime_ids_stmt = select(Showtime.id).where(Showtime.partner_id == partner_id)
                showtime_ids = (await session.execute(showtime_ids_stmt)).scalars().all()

                # 3. Build booking query for CONFIRMED bookings
                booking_filters = [
                    BookingModel.status == "CONFIRMED",
                ]

                # Filter by partner's events and showtimes
                ownership_filter = []
                if event_ids:
                    ownership_filter.append(BookingModel.event_id.in_(event_ids))
                if showtime_ids:
                    ownership_filter.append(BookingModel.showtime_id.in_(showtime_ids))

                if ownership_filter:
                    booking_filters.append(or_(*ownership_filter))
                else:
                    return {
                        "total_revenue_paise": 0,
                        "total_bookings": 0,
                        "average_booking_paise": 0,
                        "by_event": [],
                        "period": {"from": from_date, "to": to_date},
                    }

                # Date filters with format validation
                if from_date:
                    try:
                        booking_filters.append(BookingModel.created_at >= dt.fromisoformat(from_date))
                    except ValueError as ve:
                        logger.warning("Invalid from_date format '%s': %s", from_date, ve)
                        raise ValueError(f"Invalid from_date format: {from_date}") from ve

                if to_date:
                    try:
                        end_dt = dt.fromisoformat(to_date) + timedelta(days=1)
                        booking_filters.append(BookingModel.created_at < end_dt)
                    except ValueError as ve:
                        logger.warning("Invalid to_date format '%s': %s", to_date, ve)
                        raise ValueError(f"Invalid to_date format: {to_date}") from ve

                # 4. Aggregate total revenue
                total_stmt = select(
                    func.coalesce(func.sum(BookingModel.total_paise), 0),
                    func.count(BookingModel.id),
                ).where(and_(*booking_filters))
                total_row = (await session.execute(total_stmt)).one()
                total_revenue = total_row[0] or 0
                total_bookings = total_row[1] or 0
                avg_booking = total_revenue // total_bookings if total_bookings > 0 else 0

                # 5. Revenue breakdown by event
                by_event = []
                if event_ids:
                    event_breakdown_stmt = (
                        select(
                            EventORM.id,
                            EventORM.title,
                            func.coalesce(func.sum(BookingModel.total_paise), 0),
                            func.count(BookingModel.id),
                        )
                        .join(BookingModel, BookingModel.event_id == EventORM.id)
                        .where(and_(*booking_filters))
                        .group_by(EventORM.id, EventORM.title)
                    )
                    event_rows = (await session.execute(event_breakdown_stmt)).all()
                    for row in event_rows:
                        by_event.append({
                            "event_id": str(row[0]),
                            "event_title": row[1],
                            "revenue_paise": row[2] or 0,
                            "bookings": row[3] or 0,
                        })

                return {
                    "total_revenue_paise": total_revenue,
                    "total_bookings": total_bookings,
                    "average_booking_paise": avg_booking,
                    "by_event": by_event,
                    "period": {"from": from_date, "to": to_date},
                }

            except Exception as e:
                logger.error("Failed to generate revenue report for partner_id %s: %s", partner_id, e, exc_info=True)
                raise
