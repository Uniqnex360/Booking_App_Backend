import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, insert, func, desc, and_
from app.booking.models import BookingModel
from app.movie.models import Venue, Showtime
from app.admin.models import (
    TheatrePaymentConfigModel,
    CommissionLedgerModel,
    CommissionInvoiceModel,
    CommissionInvoiceItemModel,
    CommissionCollectionModel
)
from app.admin.theatre_service import TheatreAdminService
from app.shared.exceptions import EntityNotFoundError, ConflictError, BadRequestError
from app.shared.timeutil import utcnow


class CommissionAdminService:
    @staticmethod
    async def record_booking_commission(
        db: AsyncSession,
        booking: BookingModel
    ) -> Optional[CommissionLedgerModel]:
        """Calculates and records a transaction-level commission ledger entry on confirmed booking."""
        if not booking:
            return None

        # Check if already recorded (idempotency)
        existing = await db.execute(
            select(CommissionLedgerModel).where(CommissionLedgerModel.booking_id == booking.id)
        )
        if existing.scalar_one_or_none():
            return None

        # Resolve venue_id from booking's showtime
        venue_id = None
        if booking.showtime_id:
            st_res = await db.execute(
                select(Showtime).where(Showtime.id == booking.showtime_id)
            )
            st = st_res.scalar_one_or_none()
            if st:
                # Resolve screen -> venue_id
                from app.movie.models import Screen
                sc_res = await db.execute(select(Screen).where(Screen.id == st.screen_id))
                screen = sc_res.scalar_one_or_none()
                if screen:
                    venue_id = screen.venue_id

        # If not movie showtime or venue not found, fallback to first available venue
        if not venue_id:
            v_res = await db.execute(select(Venue.id).limit(1))
            venue_id = v_res.scalar_one_or_none()

        if not venue_id:
            return None

        # Get venue configuration
        cfg = await TheatreAdminService.get_theatre_config(db, venue_id)

        # Disaggregate amounts
        ticket_paise = booking.ticket_paise
        if ticket_paise is None or ticket_paise <= 0:
            ticket_paise = max(0, booking.total_paise - (booking.fnb_paise or 0) - (booking.convenience_fee_paise or 0))

        # Determine calculation base
        base_mode = (cfg.calculation_base or "GROSS_TICKET").upper()
        if base_mode == "NET_OF_TAX":
            # Assuming 18% GST included in ticket
            eligible_base = int(round(ticket_paise / 1.18))
        elif base_mode == "TICKET_PLUS_FEES":
            eligible_base = ticket_paise + (booking.convenience_fee_paise or 0)
        else:
            eligible_base = ticket_paise

        # Determine ticket quantity for per-ticket calculations
        ticket_count = booking.quantity if (booking.quantity and booking.quantity > 0) else 0
        if ticket_count == 0:
            raw_seats = getattr(booking, "seat_codes_json", None) or getattr(booking, "seat_refs_json", None)
            if raw_seats:
                try:
                    import json
                    seats = json.loads(raw_seats)
                    ticket_count = len(seats) if isinstance(seats, list) else 1
                except Exception:
                    ticket_count = 1
        if ticket_count <= 0:
            ticket_count = 1

        # Calculate commission
        rate_val = float(cfg.rate_value or 30.0)
        rate_type = (cfg.rate_type or "PER_TICKET").upper()
        fixed_paise = cfg.fixed_fee_paise or 0

        if rate_type in ("PER_TICKET", "FIXED_PER_TICKET"):
            per_ticket_paise = fixed_paise if fixed_paise > 0 else int(round(rate_val * 100))
            commission_paise = ticket_count * per_ticket_paise
        elif rate_type == "FIXED_FEE":
            commission_paise = fixed_paise if fixed_paise > 0 else int(round(rate_val * 100))
        elif rate_type == "HYBRID":
            per_ticket_paise = fixed_paise if fixed_paise > 0 else 0
            commission_paise = int(round(eligible_base * (rate_val / 100.0))) + (ticket_count * per_ticket_paise)
        else: # PERCENTAGE
            commission_paise = int(round(eligible_base * (rate_val / 100.0)))

        # 18% GST on Vybhz commission invoice
        tax_paise = int(round(commission_paise * 0.18))

        ledger_entry = CommissionLedgerModel(
            booking_id=booking.id,
            venue_id=venue_id,
            gross_ticket_paise=ticket_paise,
            eligible_base_paise=eligible_base,
            rate_type=rate_type,
            rate_value=rate_val,
            commission_paise=commission_paise,
            tax_paise=tax_paise,
            status="UNINVOICED",
            created_at=utcnow()
        )
        db.add(ledger_entry)
        await db.commit()
        await db.refresh(ledger_entry)
        return ledger_entry

    @staticmethod
    async def list_ledger_entries(
        db: AsyncSession,
        venue_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        q = (
            select(CommissionLedgerModel, Venue.name.label("venue_name"), BookingModel.ref_code.label("booking_ref"), CommissionInvoiceModel.invoice_number)
            .join(Venue, CommissionLedgerModel.venue_id == Venue.id, isouter=True)
            .join(BookingModel, CommissionLedgerModel.booking_id == BookingModel.id, isouter=True)
            .join(CommissionInvoiceModel, CommissionLedgerModel.invoice_id == CommissionInvoiceModel.id, isouter=True)
        )
        if venue_id:
            q = q.where(CommissionLedgerModel.venue_id == venue_id)
        if status:
            q = q.where(CommissionLedgerModel.status == status.upper())

        q = q.order_by(CommissionLedgerModel.created_at.desc()).limit(limit).offset(offset)
        res = await db.execute(q)
        rows = res.all()

        results = []
        for ledger, v_name, b_ref, inv_num in rows:
            t_paise = ledger.tax_paise or 0
            cgst = t_paise // 2
            sgst = t_paise - cgst
            results.append({
                "id": ledger.id,
                "booking_id": ledger.booking_id,
                "booking_ref": b_ref,
                "venue_id": ledger.venue_id,
                "venue_name": v_name,
                "gross_ticket_paise": ledger.gross_ticket_paise,
                "eligible_base_paise": ledger.eligible_base_paise,
                "rate_type": ledger.rate_type,
                "rate_value": float(ledger.rate_value),
                "commission_paise": ledger.commission_paise,
                "tax_paise": t_paise,
                "cgst_paise": cgst,
                "sgst_paise": sgst,
                "status": ledger.status,
                "invoice_id": ledger.invoice_id,
                "invoice_number": inv_num,
                "created_at": ledger.created_at,
            })
        return results

    @staticmethod
    async def generate_invoice(
        db: AsyncSession,
        venue_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        due_days: int = 1,
        notes: Optional[str] = None,
        admin_user: Any = None
    ) -> CommissionInvoiceModel:
        # Find all UNINVOICED ledger entries in period
        q = select(CommissionLedgerModel).where(
            and_(
                CommissionLedgerModel.venue_id == venue_id,
                CommissionLedgerModel.status == "UNINVOICED",
                CommissionLedgerModel.created_at >= period_start,
                CommissionLedgerModel.created_at <= period_end
            )
        )
        res = await db.execute(q)
        entries = list(res.scalars().all())

        if not entries:
            raise BadRequestError(f"No uninvoiced commission transactions found for this venue in the specified period.")

        total_gross = sum(e.gross_ticket_paise for e in entries)
        total_commission = sum(e.commission_paise for e in entries)
        total_tax = sum(e.tax_paise for e in entries)
        total_amount = total_commission + total_tax
        booking_count = len(entries)

        # Unique sequential invoice number
        inv_code = secrets.token_hex(2).upper()
        inv_num = f"INV-{period_start.strftime('%Y%m')}-{inv_code}"

        due_date = utcnow() + timedelta(days=due_days)

        invoice = CommissionInvoiceModel(
            invoice_number=inv_num,
            venue_id=venue_id,
            period_start=period_start,
            period_end=period_end,
            booking_count=booking_count,
            ticket_count=booking_count,
            gross_sales_paise=total_gross,
            commission_paise=total_commission,
            tax_paise=total_tax,
            total_paise=total_amount,
            paid_paise=0,
            balance_paise=total_amount,
            status="DRAFT",
            due_date=due_date,
            created_by=getattr(admin_user, "id", None),
            notes=notes
        )
        db.add(invoice)
        await db.flush()

        # Add invoice line items & update ledger entries
        for e in entries:
            item = CommissionInvoiceItemModel(
                invoice_id=invoice.id,
                ledger_id=e.id,
                description=f"Booking ticket sales commission ({float(e.rate_value)}%)",
                item_type="COMMISSION",
                amount_paise=e.commission_paise,
                created_at=utcnow()
            )
            db.add(item)
            e.status = "INVOICED"
            e.invoice_id = invoice.id

        await db.commit()
        await db.refresh(invoice)
        return invoice

    @staticmethod
    async def list_invoices(
        db: AsyncSession,
        venue_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        q = (
            select(CommissionInvoiceModel, Venue.name.label("venue_name"))
            .join(Venue, CommissionInvoiceModel.venue_id == Venue.id, isouter=True)
        )
        if venue_id:
            q = q.where(CommissionInvoiceModel.venue_id == venue_id)
        if status:
            q = q.where(CommissionInvoiceModel.status == status.upper())

        q = q.order_by(CommissionInvoiceModel.created_at.desc()).limit(limit).offset(offset)
        res = await db.execute(q)
        rows = res.all()

        results = []
        now = utcnow()
        for inv, v_name in rows:
            # Check if overdue
            current_status = inv.status
            if current_status in ("ISSUED", "PARTIALLY_PAID") and inv.due_date < now:
                current_status = "OVERDUE"

            t_paise = inv.tax_paise or 0
            cgst = t_paise // 2
            sgst = t_paise - cgst

            results.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "venue_id": inv.venue_id,
                "venue_name": v_name,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "booking_count": inv.booking_count,
                "ticket_count": inv.ticket_count,
                "gross_sales_paise": inv.gross_sales_paise,
                "commission_paise": inv.commission_paise,
                "adjustments_paise": inv.adjustments_paise,
                "tax_paise": t_paise,
                "cgst_paise": cgst,
                "sgst_paise": sgst,
                "total_paise": inv.total_paise,
                "paid_paise": inv.paid_paise,
                "balance_paise": inv.balance_paise,
                "status": current_status,
                "issue_date": inv.issue_date,
                "due_date": inv.due_date,
                "notes": inv.notes,
                "created_at": inv.created_at,
            })
        return results

    @staticmethod
    async def update_invoice_status(
        db: AsyncSession,
        invoice_id: uuid.UUID,
        new_status: str,
        notes: Optional[str] = None,
        admin_user: Any = None
    ) -> CommissionInvoiceModel:
        res = await db.execute(
            select(CommissionInvoiceModel).where(CommissionInvoiceModel.id == invoice_id)
        )
        inv = res.scalar_one_or_none()
        if not inv:
            raise EntityNotFoundError(f"Invoice '{invoice_id}' not found")

        inv.status = new_status.upper()
        if inv.status == "ISSUED" and not inv.issue_date:
            inv.issue_date = utcnow()
            inv.approved_by = getattr(admin_user, "id", None)
        if notes:
            inv.notes = f"{inv.notes or ''}\n[{utcnow().isoformat()}] {notes}".strip()

        inv.updated_at = utcnow()
        await db.commit()
        await db.refresh(inv)
        return inv

    @staticmethod
    async def record_collection_payment(
        db: AsyncSession,
        invoice_id: uuid.UUID,
        amount_paise: int,
        payment_method: str,
        payment_ref: str,
        notes: Optional[str] = None,
        admin_user: Any = None
    ) -> CommissionCollectionModel:
        res = await db.execute(
            select(CommissionInvoiceModel).where(CommissionInvoiceModel.id == invoice_id)
        )
        inv = res.scalar_one_or_none()
        if not inv:
            raise EntityNotFoundError(f"Invoice '{invoice_id}' not found")

        # Record collection receipt
        collection = CommissionCollectionModel(
            invoice_id=invoice_id,
            venue_id=inv.venue_id,
            payment_method=payment_method,
            payment_ref=payment_ref,
            amount_paise=amount_paise,
            status="CONFIRMED",
            collected_at=utcnow(),
            recorded_by=getattr(admin_user, "id", None),
            notes=notes
        )
        db.add(collection)

        # Update invoice balance
        inv.paid_paise += amount_paise
        inv.balance_paise = max(0, inv.total_paise - inv.paid_paise)
        if inv.balance_paise == 0:
            inv.status = "PAID"
        elif inv.paid_paise > 0:
            inv.status = "PARTIALLY_PAID"

        inv.updated_at = utcnow()
        await db.commit()
        await db.refresh(collection)
        return collection

