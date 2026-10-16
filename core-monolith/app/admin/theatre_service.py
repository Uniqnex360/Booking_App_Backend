import json
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, insert, func, desc
from app.movie.models import Venue
from app.admin.models import (
    TheatreChainModel,
    TheatrePaymentConfigModel,
    TheatreConfigHistoryModel,
    AdminAuditLogModel
)
from app.admin.schemas import (
    TheatreChainCreate,
    TheatreChainUpdate,
    TheatrePaymentConfigUpdate,
    TheatreStatusUpdateRequest
)
from app.shared.exceptions import EntityNotFoundError, ConflictError
from app.shared.timeutil import utcnow


class TheatreAdminService:
    @staticmethod
    async def list_chains(db: AsyncSession) -> List[TheatreChainModel]:
        res = await db.execute(select(TheatreChainModel).order_by(TheatreChainModel.name.asc()))
        return list(res.scalars().all())

    @staticmethod
    async def create_chain(db: AsyncSession, data: TheatreChainCreate) -> TheatreChainModel:
        existing = await db.execute(select(TheatreChainModel).where(TheatreChainModel.code == data.code.upper()))
        if existing.scalar_one_or_none():
            raise ConflictError(f"Chain with code '{data.code}' already exists")

        chain = TheatreChainModel(
            name=data.name,
            code=data.code.upper(),
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            notes=data.notes
        )
        db.add(chain)
        await db.commit()
        await db.refresh(chain)
        return chain

    @staticmethod
    async def list_theatres(
        db: AsyncSession,
        city: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        # Fetch all venues
        q = select(Venue)
        if city:
            q = q.where(Venue.city.ilike(f"%{city}%"))
        if search:
            q = q.where(Venue.name.ilike(f"%{search}%"))
        q = q.order_by(Venue.name.asc()).limit(limit).offset(offset)
        res = await db.execute(q)
        venues = list(res.scalars().all())

        if not venues:
            return []

        venue_ids = [v.id for v in venues]

        # Fetch active payment configs for these venues
        cfg_res = await db.execute(
            select(TheatrePaymentConfigModel).where(TheatrePaymentConfigModel.venue_id.in_(venue_ids))
        )
        configs = {cfg.venue_id: cfg for cfg in cfg_res.scalars().all()}

        # Fetch chains
        chains_res = await db.execute(select(TheatreChainModel))
        chains_map = {c.name.lower(): c for c in chains_res.scalars().all()}

        results = []
        for v in venues:
            cfg = configs.get(v.id)
            # Match chain by name convention if exists (e.g. "PVR" or "AGS")
            chain_obj = None
            for c_code, c in chains_map.items():
                if c.name.lower() in v.name.lower() or c.code.lower() in v.name.lower():
                    chain_obj = c
                    break

            rate_display = f"{float(cfg.rate_value):.1f}%" if cfg else "5.0%"
            results.append({
                "id": v.id,
                "name": v.name,
                "city": v.city,
                "address": v.address,
                "chain_name": chain_obj.name if chain_obj else None,
                "chain_code": chain_obj.code if chain_obj else None,
                "operational_status": "ACTIVE",
                "customer_payment_model": cfg.customer_payment_model if cfg else "THEATRE_DIRECT",
                "commission_model": cfg.commission_model if cfg else "INVOICE_POST_PAY",
                "commission_rate_display": rate_display,
                "invoice_cycle": cfg.invoice_cycle if cfg else "DAILY",
                "last_sync_status": "HEALTHY",
            })
        return results

    @staticmethod
    async def get_theatre_config(db: AsyncSession, venue_id: uuid.UUID) -> TheatrePaymentConfigModel:
        # Check venue exists
        v_res = await db.execute(select(Venue).where(Venue.id == venue_id))
        venue = v_res.scalar_one_or_none()
        if not venue:
            raise EntityNotFoundError(f"Venue with id '{venue_id}' not found")

        cfg_res = await db.execute(
            select(TheatrePaymentConfigModel).where(TheatrePaymentConfigModel.venue_id == venue_id)
        )
        cfg = cfg_res.scalar_one_or_none()
        if not cfg:
            # Create default configuration (Model A: Theatre Direct + Daily invoice)
            cfg = TheatrePaymentConfigModel(
                venue_id=venue_id,
                customer_payment_model="THEATRE_DIRECT",
                payment_provider="THEATRE_GATEWAY",
                commission_model="INVOICE_POST_PAY",
                rate_type="PERCENTAGE",
                rate_value=5.0000,
                calculation_base="GROSS_TICKET",
                invoice_cycle="DAILY",
                due_days=1,
                currency="INR",
                reconciliation_source="API_WEBHOOK",
                refund_treatment="DEDUCT_COMMISSION",
                effective_from=utcnow(),
                is_active=True
            )
            db.add(cfg)
            await db.commit()
            await db.refresh(cfg)
        return cfg

    @staticmethod
    async def update_theatre_config(
        db: AsyncSession,
        venue_id: uuid.UUID,
        data: TheatrePaymentConfigUpdate,
        admin_user: Any = None
    ) -> TheatrePaymentConfigModel:
        cfg = await TheatreAdminService.get_theatre_config(db, venue_id)
        
        # Save previous snapshot for immutable audit history
        prev_snapshot = {
            "customer_payment_model": cfg.customer_payment_model,
            "payment_provider": cfg.payment_provider,
            "commission_model": cfg.commission_model,
            "rate_type": cfg.rate_type,
            "rate_value": float(cfg.rate_value),
            "fixed_fee_paise": cfg.fixed_fee_paise,
            "calculation_base": cfg.calculation_base,
            "invoice_cycle": cfg.invoice_cycle,
            "due_days": cfg.due_days,
            "currency": cfg.currency,
            "reconciliation_source": cfg.reconciliation_source,
            "refund_treatment": cfg.refund_treatment,
            "contract_ref": cfg.contract_ref,
        }

        # Apply updates
        if data.customer_payment_model:
            cfg.customer_payment_model = data.customer_payment_model
        if data.payment_provider:
            cfg.payment_provider = data.payment_provider
        if data.commission_model:
            cfg.commission_model = data.commission_model
        if data.rate_type:
            cfg.rate_type = data.rate_type
        if data.rate_value is not None:
            cfg.rate_value = data.rate_value
        if data.fixed_fee_paise is not None:
            cfg.fixed_fee_paise = data.fixed_fee_paise
        if data.calculation_base:
            cfg.calculation_base = data.calculation_base
        if data.invoice_cycle:
            cfg.invoice_cycle = data.invoice_cycle
        if data.due_days is not None:
            cfg.due_days = data.due_days
        if data.currency:
            cfg.currency = data.currency
        if data.reconciliation_source:
            cfg.reconciliation_source = data.reconciliation_source
        if data.refund_treatment:
            cfg.refund_treatment = data.refund_treatment
        if data.contract_ref is not None:
            cfg.contract_ref = data.contract_ref

        cfg.updated_at = utcnow()

        new_snapshot = {
            "customer_payment_model": cfg.customer_payment_model,
            "payment_provider": cfg.payment_provider,
            "commission_model": cfg.commission_model,
            "rate_type": cfg.rate_type,
            "rate_value": float(cfg.rate_value),
            "fixed_fee_paise": cfg.fixed_fee_paise,
            "calculation_base": cfg.calculation_base,
            "invoice_cycle": cfg.invoice_cycle,
            "due_days": cfg.due_days,
            "currency": cfg.currency,
            "reconciliation_source": cfg.reconciliation_source,
            "refund_treatment": cfg.refund_treatment,
            "contract_ref": cfg.contract_ref,
        }

        # Record history audit
        history = TheatreConfigHistoryModel(
            venue_id=venue_id,
            changed_by=getattr(admin_user, "id", None),
            changed_by_name=getattr(admin_user, "full_name", "Admin"),
            change_reason=data.change_reason or "Configuration update",
            previous_config_json=json.dumps(prev_snapshot),
            new_config_json=json.dumps(new_snapshot),
            created_at=utcnow()
        )
        db.add(history)

        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def get_config_history(db: AsyncSession, venue_id: uuid.UUID) -> List[TheatreConfigHistoryModel]:
        res = await db.execute(
            select(TheatreConfigHistoryModel)
            .where(TheatreConfigHistoryModel.venue_id == venue_id)
            .order_by(TheatreConfigHistoryModel.created_at.desc())
        )
        return list(res.scalars().all())

