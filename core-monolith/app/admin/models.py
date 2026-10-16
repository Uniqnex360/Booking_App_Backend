import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Numeric,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.shared.timeutil import utcnow


class TheatreChainModel(Base):
    __tablename__ = "theatre_chains"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=False)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TheatrePaymentConfigModel(Base):
    __tablename__ = "theatre_payment_configs"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), unique=True, nullable=False, index=True)
    
    # Model A (THEATRE_DIRECT), Model B (VYHBZ_COLLECTS_SETTLES), Model C (OTHER)
    customer_payment_model = Column(String(50), nullable=False, default="THEATRE_DIRECT", server_default="THEATRE_DIRECT")
    payment_provider = Column(String(100), nullable=False, default="THEATRE_GATEWAY", server_default="THEATRE_GATEWAY")
    
    # Commission collection model (INVOICE_POST_PAY, AUTOMATED_SPLIT, OTHER)
    commission_model = Column(String(50), nullable=False, default="INVOICE_POST_PAY", server_default="INVOICE_POST_PAY")
    rate_type = Column(String(50), nullable=False, default="PERCENTAGE", server_default="PERCENTAGE") # PERCENTAGE, FIXED_FEE, HYBRID
    rate_value = Column(Numeric(10, 4), nullable=False, default=5.0000, server_default="5.0000")
    fixed_fee_paise = Column(Integer, nullable=False, default=0, server_default="0")
    calculation_base = Column(String(50), nullable=False, default="GROSS_TICKET", server_default="GROSS_TICKET") # GROSS_TICKET, NET_OF_TAX, TICKET_PLUS_FEES
    
    # Invoicing cycle (Default: DAILY 23:59 cutoff, 1 day due)
    invoice_cycle = Column(String(50), nullable=False, default="DAILY", server_default="DAILY") # DAILY, WEEKLY, MONTHLY, BI_WEEKLY
    due_days = Column(Integer, nullable=False, default=1, server_default="1")
    currency = Column(String(10), nullable=False, default="INR", server_default="INR")
    
    # Reconciliation & Refunds
    reconciliation_source = Column(String(50), nullable=False, default="API_WEBHOOK", server_default="API_WEBHOOK")
    refund_treatment = Column(String(50), nullable=False, default="DEDUCT_COMMISSION", server_default="DEDUCT_COMMISSION")
    
    contract_ref = Column(String(100), nullable=True)
    effective_from = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TheatreConfigHistoryModel(Base):
    __tablename__ = "theatre_config_history"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), nullable=False, index=True)
    changed_by = Column(sa.Uuid, nullable=True)
    changed_by_name = Column(String(255), nullable=True)
    change_reason = Column(Text, nullable=True)
    previous_config_json = Column(Text, nullable=False)
    new_config_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CommissionLedgerModel(Base):
    __tablename__ = "commission_ledgers"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    booking_id = Column(sa.Uuid, ForeignKey("bookings.id"), unique=True, nullable=False, index=True)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), nullable=False, index=True)
    
    gross_ticket_paise = Column(Integer, nullable=False)
    eligible_base_paise = Column(Integer, nullable=False)
    rate_type = Column(String(50), nullable=False, default="PERCENTAGE")
    rate_value = Column(Numeric(10, 4), nullable=False)
    commission_paise = Column(Integer, nullable=False)
    tax_paise = Column(Integer, nullable=False, default=0, server_default="0")
    
    status = Column(String(50), nullable=False, default="UNINVOICED", index=True) # UNINVOICED, INVOICED, ADJUSTED, VOIDED
    invoice_id = Column(sa.Uuid, ForeignKey("commission_invoices.id"), nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CommissionInvoiceModel(Base):
    __tablename__ = "commission_invoices"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    invoice_number = Column(String(100), unique=True, nullable=False, index=True)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), nullable=False, index=True)
    
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    booking_count = Column(Integer, nullable=False, default=0)
    ticket_count = Column(Integer, nullable=False, default=0)
    gross_sales_paise = Column(Integer, nullable=False, default=0)
    commission_paise = Column(Integer, nullable=False, default=0)
    adjustments_paise = Column(Integer, nullable=False, default=0)
    tax_paise = Column(Integer, nullable=False, default=0)
    total_paise = Column(Integer, nullable=False, default=0)
    paid_paise = Column(Integer, nullable=False, default=0)
    balance_paise = Column(Integer, nullable=False, default=0)
    
    # States: DRAFT, APPROVED, ISSUED, PARTIALLY_PAID, PAID, OVERDUE, DISPUTED, VOIDED, CREDITED
    status = Column(String(50), nullable=False, default="DRAFT", index=True)
    
    issue_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(sa.Uuid, nullable=True)
    approved_by = Column(sa.Uuid, nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    items = relationship("CommissionInvoiceItemModel", back_populates="invoice", cascade="all, delete-orphan")


class CommissionInvoiceItemModel(Base):
    __tablename__ = "commission_invoice_items"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    invoice_id = Column(sa.Uuid, ForeignKey("commission_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    ledger_id = Column(sa.Uuid, ForeignKey("commission_ledgers.id"), nullable=True)
    description = Column(String(255), nullable=False)
    item_type = Column(String(50), nullable=False, default="COMMISSION") # COMMISSION, ADJUSTMENT, CREDIT_NOTE
    amount_paise = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    invoice = relationship("CommissionInvoiceModel", back_populates="items")


class CommissionCollectionModel(Base):
    __tablename__ = "commission_collections"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    invoice_id = Column(sa.Uuid, ForeignKey("commission_invoices.id"), nullable=False, index=True)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), nullable=False, index=True)
    payment_method = Column(String(50), nullable=False, default="NEFT") # NEFT, RTGS, UPI, RAZORPAY_LINK, OTHER
    payment_ref = Column(String(100), nullable=False, index=True)
    amount_paise = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="CONFIRMED") # CONFIRMED, REVERSED, PENDING
    collected_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    recorded_by = Column(sa.Uuid, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReconciliationExceptionModel(Base):
    __tablename__ = "reconciliation_exceptions"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    exception_type = Column(String(100), nullable=False, index=True) # BOOKING_PAYMENT_MISMATCH, MISSING_CONFIRMATION, AMOUNT_MISMATCH, DUPLICATE_WEBHOOK
    booking_id = Column(sa.Uuid, ForeignKey("bookings.id"), nullable=True, index=True)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), nullable=True, index=True)
    external_ref = Column(String(100), nullable=True, index=True)
    severity = Column(String(20), nullable=False, default="MEDIUM") # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(String(50), nullable=False, default="OPEN", index=True) # OPEN, INVESTIGATING, RESOLVED, WRITTEN_OFF
    discrepancy_details = Column(Text, nullable=False)
    resolution_notes = Column(Text, nullable=True)
    assigned_to = Column(sa.Uuid, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AdminAuditLogModel(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(sa.Uuid, nullable=True, index=True)
    user_name = Column(String(255), nullable=True)
    user_role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(100), nullable=False)
    target_id = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

