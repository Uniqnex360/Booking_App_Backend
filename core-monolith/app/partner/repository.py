import uuid
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.partner.interfaces import (
    IPartnerRepository,
    Partner,
    PartnerStatus,
    PartnerType,
)
from app.partner.models import PartnerORM
from app.shared.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    RepositoryError,
)


class SQLAlchemyPartnerRepository(IPartnerRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    def _to_domain(self, orm: PartnerORM) -> Partner:
        return Partner(
            id=orm.id,
            user_id=orm.user_id,
            business_name=orm.business_name,
            partner_type=PartnerType(orm.partner_type),
            contact_name=orm.contact_name,
            contact_phone=orm.contact_phone,
            city=orm.city,
            gst_number=orm.gst_number,
            pan_number=orm.pan_number,
            status=PartnerStatus(orm.status),
            commission_rate=orm.commission_rate,
            approved_at=orm.approved_at,
            approved_by=orm.approved_by,
            rejection_reason=orm.rejection_reason,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _domain_values(self, partner: Partner) -> Dict[str, Any]:
        return {
            "business_name": partner.business_name,
            "partner_type": partner.partner_type.value,
            "contact_name": partner.contact_name,
            "contact_phone": partner.contact_phone,
            "city": partner.city,
            "gst_number": partner.gst_number,
            "pan_number": partner.pan_number,
            "status": partner.status.value,
            "commission_rate": partner.commission_rate,
            "approved_at": partner.approved_at,
            "approved_by": partner.approved_by,
            "rejection_reason": partner.rejection_reason,
        }

    def _to_orm(self, partner: Partner) -> PartnerORM:
        return PartnerORM(
            id=partner.id,
            user_id=partner.user_id,
            **self._domain_values(partner),
        )

    def _fill_orm_from_domain(
        self,
        orm: PartnerORM,
        partner: Partner,
    ) -> None:
        for field_name, value in self._domain_values(partner).items():
            setattr(orm, field_name, value)

    async def get_by_id(self, partner_id: uuid.UUID) -> Optional[Partner]:
        try:
            orm = await self.db.get(PartnerORM, partner_id)
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            raise RepositoryError(
                f"Failed to fetch partner by id."
            ) from e

    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[Partner]:
        try:
            stmt = select(PartnerORM).where(
                PartnerORM.user_id == user_id
            )
            result = await self.db.execute(stmt)
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            raise RepositoryError(
                "Failed to fetch partner for user."
            ) from e

    async def list_by_filters(
        self,
        status: Optional[PartnerStatus],
        partner_type: Optional[PartnerType],
        page: int,
        limit: int,
    ) -> Tuple[List[Partner], int]:
        try:
            base_stmt = select(PartnerORM)
            if status is not None:
                base_stmt = base_stmt.where(
                    PartnerORM.status == status.value
                )
            if partner_type is not None:
                base_stmt = base_stmt.where(
                    PartnerORM.partner_type == partner_type.value
                )
            count_stmt = select(func.count()).select_from(
                base_stmt.subquery()
            )
            total = (await self.db.execute(count_stmt)).scalar_one()
            offset = (page - 1) * limit
            data_stmt = (
                base_stmt
                .order_by(PartnerORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await self.db.execute(data_stmt)
            partners = [
                self._to_domain(orm)
                for orm in result.scalars().all()
            ]
            return partners, total
        except SQLAlchemyError as e:
            raise RepositoryError(
                "Failed to list partners."
            ) from e

    async def create(self, partner: Partner) -> Partner:
        try:
            orm = self._to_orm(partner)
            self.db.add(orm)
            await self.db.commit()
            await self.db.refresh(orm)
            return self._to_domain(orm)
        except IntegrityError as e:
            await self.db.rollback()
            raise DuplicateEntityError(
                "A partner account already exists for this user."
            ) from e
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(
                "Failed to create partner."
            ) from e

    async def update(self, partner: Partner) -> Partner:
        try:
            orm = await self.db.get(PartnerORM, partner.id)
            if orm is None:
                raise EntityNotFoundError("Partner not found.")
            self._fill_orm_from_domain(orm, partner)
            await self.db.commit()
            await self.db.refresh(orm)
            return self._to_domain(orm)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(
                "Failed to update partner."
            ) from e
