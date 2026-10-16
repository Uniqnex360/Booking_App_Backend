import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, insert, func, desc, or_
from app.booking.models import BookingModel
from app.payment.models import PaymentModel
from app.movie.models import Venue, Showtime, Screen, Movie
from app.admin.models import (
    ReconciliationExceptionModel,
    CommissionLedgerModel,
    CommissionInvoiceModel
)
from app.shared.exceptions import EntityNotFoundError
from app.shared.timeutil import utcnow


class ReconciliationAdminService:
    @staticmethod
    async def flag_exception(
        db: AsyncSession,
        exception_type: str,
        discrepancy_details: str,
        booking_id: Optional[uuid.UUID] = None,
        venue_id: Optional[uuid.UUID] = None,
        external_ref: Optional[str] = None,
        severity: str = "MEDIUM"
    ) -> ReconciliationExceptionModel:
        exc = ReconciliationExceptionModel(
            exception_type=exception_type,
            booking_id=booking_id,
            venue_id=venue_id,
            external_ref=external_ref,
            severity=severity.upper(),
            status="OPEN",
            discrepancy_details=discrepancy_details,
            created_at=utcnow()
        )
        db.add(exc)
        await db.commit()
        await db.refresh(exc)
        return exc

    @staticmethod
    async def list_exceptions(
        db: AsyncSession,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        q = (
            select(ReconciliationExceptionModel, Venue.name.label("venue_name"), BookingModel.ref_code.label("booking_ref"))
            .join(Venue, ReconciliationExceptionModel.venue_id == Venue.id, isouter=True)
            .join(BookingModel, ReconciliationExceptionModel.booking_id == BookingModel.id, isouter=True)
        )
        if status:
            q = q.where(ReconciliationExceptionModel.status == status.upper())
        if severity:
            q = q.where(ReconciliationExceptionModel.severity == severity.upper())

        q = q.order_by(ReconciliationExceptionModel.created_at.desc()).limit(limit).offset(offset)
        res = await db.execute(q)
        rows = res.all()

        results = []
        for exc, v_name, b_ref in rows:
            results.append({
                "id": exc.id,
                "exception_type": exc.exception_type,
                "booking_id": exc.booking_id,
                "booking_ref": b_ref,
                "venue_id": exc.venue_id,
                "venue_name": v_name,
                "external_ref": exc.external_ref,
                "severity": exc.severity,
                "status": exc.status,
                "discrepancy_details": exc.discrepancy_details,
                "resolution_notes": exc.resolution_notes,
                "resolved_at": exc.resolved_at,
                "created_at": exc.created_at,
            })
        return results

    @staticmethod
    async def resolve_exception(
        db: AsyncSession,
        exception_id: uuid.UUID,
        new_status: str,
        resolution_notes: str,
        admin_user: Any = None
    ) -> ReconciliationExceptionModel:
        res = await db.execute(
            select(ReconciliationExceptionModel).where(ReconciliationExceptionModel.id == exception_id)
        )
        exc = res.scalar_one_or_none()
        if not exc:
            raise EntityNotFoundError(f"Reconciliation exception '{exception_id}' not found")

        exc.status = new_status.upper()
        exc.resolution_notes = resolution_notes
        exc.assigned_to = getattr(admin_user, "id", None)
        if new_status.upper() == "RESOLVED":
            exc.resolved_at = utcnow()
        exc.updated_at = utcnow()

        await db.commit()
        await db.refresh(exc)
        return exc

    @staticmethod
    async def search_bookings_detailed(
        db: AsyncSession,
        query: Optional[str] = None,
        venue_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        # Join booking with payment, showtime, movie, venue, and commission ledger
        q = (
            select(
                BookingModel,
                PaymentModel.status.label("payment_status"),
                PaymentModel.refund_id,
                Showtime.starts_at.label("showtime_at"),
                Movie.title.label("movie_title"),
                Venue.id.label("venue_id"),
                Venue.name.label("venue_name"),
                CommissionLedgerModel.status.label("commission_ledger_status"),
                CommissionLedgerModel.commission_paise.label("commission_earned"),
                CommissionInvoiceModel.invoice_number,
                CommissionInvoiceModel.status.label("invoice_status")
            )
            .join(PaymentModel, BookingModel.id == PaymentModel.booking_id, isouter=True)
            .join(Showtime, BookingModel.showtime_id == Showtime.id, isouter=True)
            .join(Movie, Showtime.movie_id == Movie.id, isouter=True)
            .join(Screen, Showtime.screen_id == Screen.id, isouter=True)
            .join(Venue, Screen.venue_id == Venue.id, isouter=True)
            .join(CommissionLedgerModel, BookingModel.id == CommissionLedgerModel.booking_id, isouter=True)
            .join(CommissionInvoiceModel, CommissionLedgerModel.invoice_id == CommissionInvoiceModel.id, isouter=True)
        )

        if query:
            clean_q = query.strip()
            q = q.where(
                or_(
                    BookingModel.ref_code.ilike(f"%{clean_q}%"),
                    BookingModel.contact_email.ilike(f"%{clean_q}%"),
                    BookingModel.contact_phone.ilike(f"%{clean_q}%"),
                    BookingModel.provider_booking_id.ilike(f"%{clean_q}%")
                )
            )

        if venue_id:
            q = q.where(Venue.id == venue_id)

        if status:
            q = q.where(BookingModel.status == status.upper())

        q = q.order_by(BookingModel.created_at.desc()).limit(limit).offset(offset)
        res = await db.execute(q)
        rows = res.all()

        results = []
        for (b, p_status, ref_id, st_time, m_title, v_id, v_name, l_status, comm_earned, inv_num, inv_status) in rows:
            # Parse seats
            seats = []
            if b.seat_codes_json:
                try:
                    seats = json.loads(b.seat_codes_json)
                except Exception:
                    pass

            ticket_amt = b.ticket_paise or max(0, b.total_paise - (b.fnb_paise or 0) - (b.convenience_fee_paise or 0))
            comm_amt = comm_earned or int(ticket_amt * 0.05)
            comm_tax = int(round(comm_amt * 0.18))

            results.append({
                "id": b.id,
                "ref_code": b.ref_code or "AGS-CONFIRMED",
                "customer_email": b.contact_email,
                    "customer_phone": b.contact_phone,
                    "booking_type": b.booking_type or "MOVIE",
                    "movie_or_event_title": m_title or "Confirmed Show",
                    "venue_id": v_id,
                    "venue_name": v_name or "Partner Theatre",
                    "showtime_at": st_time or b.created_at,
                    "seats": seats,
                    "quantity": b.quantity or len(seats) or 1,
                    "ticket_paise": ticket_amt,
                    "fnb_paise": b.fnb_paise or 0,
                    "convenience_fee_paise": b.convenience_fee_paise or 0,
                    "total_paise": b.total_paise,
                    "eligible_commission_base_paise": ticket_amt,
                    "commission_earned_paise": comm_amt,
                    "commission_tax_paise": comm_tax,
                    "commission_cgst_paise": comm_tax // 2,
                    "commission_sgst_paise": comm_tax - (comm_tax // 2),
                    "booking_status": b.status or "CONFIRMED",
                    "payment_status": p_status or "CAPTURED",
                    "refund_status": "REFUNDED" if ref_id else "NONE",
                    "commission_invoice_status": inv_status or ("INVOICED" if inv_num else "UNINVOICED"),
                    "commission_collection_status": "COLLECTED" if inv_status == "PAID" else "PENDING",
                    "provider_booking_id": b.provider_booking_id,
                    "created_at": b.created_at
                })
        return results

    @staticmethod
    async def reconcile_provider_transactions(
        db: AsyncSession,
        venue_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Scans provider and cinema bookings for discrepancies between payments and provider confirmations.
        Flags any discovered issues in the Central Admin Reconciliation Exceptions queue.
        """
        # Fetch bookings with payments
        q = (
            select(
                BookingModel,
                PaymentModel,
                Screen.venue_id
            )
            .join(PaymentModel, BookingModel.id == PaymentModel.booking_id, isouter=True)
            .join(Showtime, BookingModel.showtime_id == Showtime.id, isouter=True)
            .join(Screen, Showtime.screen_id == Screen.id, isouter=True)
            .where(BookingModel.provider_id.isnot(None))
        )
        if venue_id:
            q = q.where(Screen.venue_id == venue_id)

        res = await db.execute(q)
        records = res.all()

        scanned_count = len(records)
        flagged_exceptions = []

        for b, pay, v_id in records:
            # 1. Payment Captured but Booking Not Confirmed
            if pay and pay.status == "CAPTURED" and b.status != "CONFIRMED":
                # Check if exception already exists
                existing = await db.execute(
                    select(ReconciliationExceptionModel).where(
                        ReconciliationExceptionModel.booking_id == b.id,
                        ReconciliationExceptionModel.exception_type == "PAYMENT_SUCCESS_BOOKING_FAILURE",
                        ReconciliationExceptionModel.status == "OPEN"
                    )
                )
                if not existing.scalar_one_or_none():
                    exc = await ReconciliationAdminService.flag_exception(
                        db=db,
                        exception_type="PAYMENT_SUCCESS_BOOKING_FAILURE",
                        discrepancy_details=(
                            f"Payment {pay.payment_id} captured (amount: {pay.amount_paise} paise) "
                            f"but provider booking {b.id} status is '{b.status}'."
                        ),
                        booking_id=b.id,
                        venue_id=v_id,
                        external_ref=pay.payment_id,
                        severity="HIGH"
                    )
                    flagged_exceptions.append(exc.id)

            # 2. Amount Mismatch between Payment and Booking
            elif pay and pay.status == "CAPTURED" and pay.amount_paise != b.total_paise:
                existing = await db.execute(
                    select(ReconciliationExceptionModel).where(
                        ReconciliationExceptionModel.booking_id == b.id,
                        ReconciliationExceptionModel.exception_type == "AMOUNT_MISMATCH",
                        ReconciliationExceptionModel.status == "OPEN"
                    )
                )
                if not existing.scalar_one_or_none():
                    exc = await ReconciliationAdminService.flag_exception(
                        db=db,
                        exception_type="AMOUNT_MISMATCH",
                        discrepancy_details=(
                            f"Payment amount ({pay.amount_paise} paise) differs from booking total "
                            f"({b.total_paise} paise) for booking {b.id}."
                        ),
                        booking_id=b.id,
                        venue_id=v_id,
                        external_ref=pay.payment_id,
                        severity="MEDIUM"
                    )
                    flagged_exceptions.append(exc.id)

            # 3. Confirmed without Provider Booking ID
            elif b.status == "CONFIRMED" and not b.provider_booking_id:
                existing = await db.execute(
                    select(ReconciliationExceptionModel).where(
                        ReconciliationExceptionModel.booking_id == b.id,
                        ReconciliationExceptionModel.exception_type == "MISSING_CONFIRMATION",
                        ReconciliationExceptionModel.status == "OPEN"
                    )
                )
                if not existing.scalar_one_or_none():
                    exc = await ReconciliationAdminService.flag_exception(
                        db=db,
                        exception_type="MISSING_CONFIRMATION",
                        discrepancy_details=(
                            f"Booking {b.id} is marked CONFIRMED but missing provider ticket confirmation reference."
                        ),
                        booking_id=b.id,
                        venue_id=v_id,
                        external_ref=b.ref_code,
                        severity="HIGH"
                    )
                    flagged_exceptions.append(exc.id)

        return {
            "scanned_bookings_count": scanned_count,
            "new_exceptions_flagged": len(flagged_exceptions),
            "exception_ids": [str(eid) for eid in flagged_exceptions]
        }
