from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Theatre Chain Schemas
# ---------------------------------------------------------------------------

class TheatreChainCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=50)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


class TheatreChainUpdate(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


class TheatreChainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Theatre Profile & Config Schemas
# ---------------------------------------------------------------------------

class TheatrePaymentConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[uuid.UUID] = None
    venue_id: uuid.UUID
    customer_payment_model: str = "THEATRE_DIRECT"
    payment_provider: str = "THEATRE_GATEWAY"
    commission_model: str = "INVOICE_POST_PAY"
    rate_type: str = "PER_TICKET"
    rate_value: float = 30.0
    fixed_fee_paise: int = 3000
    calculation_base: str = "GROSS_TICKET"
    invoice_cycle: str = "DAILY"
    due_days: int = 1
    currency: str = "INR"
    reconciliation_source: str = "API_WEBHOOK"
    refund_treatment: str = "DEDUCT_COMMISSION"
    contract_ref: Optional[str] = None
    effective_from: Optional[datetime] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TheatrePaymentConfigUpdate(BaseModel):
    customer_payment_model: Optional[str] = "THEATRE_DIRECT"
    payment_provider: Optional[str] = "THEATRE_GATEWAY"
    commission_model: Optional[str] = "INVOICE_POST_PAY"
    rate_type: Optional[str] = "PER_TICKET"
    rate_value: Optional[float] = 30.0
    fixed_fee_paise: Optional[int] = 3000
    calculation_base: Optional[str] = "GROSS_TICKET"
    invoice_cycle: Optional[str] = "DAILY"
    due_days: Optional[int] = 1
    currency: Optional[str] = "INR"
    reconciliation_source: Optional[str] = "API_WEBHOOK"
    refund_treatment: Optional[str] = "DEDUCT_COMMISSION"
    contract_ref: Optional[str] = None
    change_reason: Optional[str] = "Admin update"


class TheatreConfigHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venue_id: uuid.UUID
    changed_by: Optional[uuid.UUID] = None
    changed_by_name: Optional[str] = None
    change_reason: Optional[str] = None
    previous_config_json: str
    new_config_json: str
    created_at: datetime


class TheatreListItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    city: str
    address: Optional[str] = None
    chain_name: Optional[str] = None
    chain_code: Optional[str] = None
    operational_status: str = "ACTIVE"
    customer_payment_model: str = "THEATRE_DIRECT"
    commission_model: str = "INVOICE_POST_PAY"
    commission_rate_display: str = "₹30.00/tix"
    invoice_cycle: str = "DAILY"
    last_sync_status: str = "HEALTHY"


class TheatreStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(ACTIVE|SUSPENDED|DEACTIVATED)$")
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Booking & Ticket Reconciliation Schemas
# ---------------------------------------------------------------------------

class AdminBookingDetailResponse(BaseModel):
    id: uuid.UUID
    ref_code: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    booking_type: str = "MOVIE"
    movie_or_event_title: Optional[str] = None
    venue_id: Optional[uuid.UUID] = None
    venue_name: Optional[str] = None
    showtime_at: Optional[datetime] = None
    seats: List[str] = []
    quantity: int = 1
    
    # Financial Disaggregation
    ticket_paise: int = 0
    fnb_paise: int = 0
    convenience_fee_paise: int = 0
    total_paise: int = 0
    eligible_commission_base_paise: int = 0
    commission_earned_paise: int = 0
    
    # Separated Statuses
    booking_status: str
    payment_status: str
    refund_status: str
    commission_invoice_status: str
    commission_collection_status: str
    
    # Integrations
    provider_booking_id: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Commission Ledger & Invoicing Schemas
# ---------------------------------------------------------------------------

class CommissionLedgerItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    booking_ref: Optional[str] = None
    venue_id: uuid.UUID
    venue_name: Optional[str] = None
    gross_ticket_paise: int
    eligible_base_paise: int
    rate_type: str
    rate_value: float
    commission_paise: int
    tax_paise: int
    cgst_paise: int = 0
    sgst_paise: int = 0
    status: str
    invoice_id: Optional[uuid.UUID] = None
    invoice_number: Optional[str] = None
    created_at: datetime


class GenerateInvoiceRequest(BaseModel):
    venue_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    due_days: Optional[int] = 1
    notes: Optional[str] = None


class InvoiceStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(APPROVED|ISSUED|DISPUTED|VOIDED)$")
    notes: Optional[str] = None


class RecordPaymentRequest(BaseModel):
    payment_method: str = Field(default="NEFT", pattern="^(NEFT|RTGS|UPI|RAZORPAY_LINK|OTHER)$")
    payment_ref: str = Field(..., min_length=3)
    amount_paise: int = Field(..., gt=0)
    notes: Optional[str] = None


class CommissionInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    venue_id: uuid.UUID
    venue_name: Optional[str] = None
    period_start: datetime
    period_end: datetime
    booking_count: int
    ticket_count: int
    gross_sales_paise: int
    commission_paise: int
    adjustments_paise: int
    tax_paise: int
    cgst_paise: int = 0
    sgst_paise: int = 0
    total_paise: int
    paid_paise: int
    balance_paise: int
    status: str
    issue_date: Optional[datetime] = None
    due_date: datetime
    notes: Optional[str] = None
    created_at: datetime


class CommissionCollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: Optional[str] = None
    venue_id: uuid.UUID
    payment_method: str
    payment_ref: str
    amount_paise: int
    status: str
    collected_at: datetime
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Reconciliation Exceptions Schemas
# ---------------------------------------------------------------------------

class ReconciliationExceptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exception_type: str
    booking_id: Optional[uuid.UUID] = None
    booking_ref: Optional[str] = None
    venue_id: Optional[uuid.UUID] = None
    venue_name: Optional[str] = None
    external_ref: Optional[str] = None
    severity: str
    status: str
    discrepancy_details: str
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime


class ResolveExceptionRequest(BaseModel):
    status: str = Field(..., pattern="^(RESOLVED|INVESTIGATING|WRITTEN_OFF)$")
    resolution_notes: str = Field(..., min_length=3)


# ---------------------------------------------------------------------------
# Comprehensive Admin Platform Stats
# ---------------------------------------------------------------------------

class AdminComprehensiveStats(BaseModel):
    total_bookings: int = 0
    total_tickets: int = 0
    gross_booking_paise: int = 0
    commission_earned_paise: int = 0
    commission_invoiced_paise: int = 0
    commission_collected_paise: int = 0
    commission_outstanding_paise: int = 0
    overdue_invoices_count: int = 0
    total_refunds_paise: int = 0
    active_theatres_count: int = 0
    open_exceptions_count: int = 0

