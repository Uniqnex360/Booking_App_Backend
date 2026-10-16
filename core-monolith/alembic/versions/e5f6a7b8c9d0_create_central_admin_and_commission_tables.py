"""create central admin and commission tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-16 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # 1. theatre_chains
    op.execute("""
        CREATE TABLE IF NOT EXISTS theatre_chains (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(50) NOT NULL UNIQUE,
            contact_email VARCHAR(255),
            contact_phone VARCHAR(50),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_theatre_chains_code ON theatre_chains(code)")

    # 2. theatre_payment_configs
    op.execute("""
        CREATE TABLE IF NOT EXISTS theatre_payment_configs (
            id UUID PRIMARY KEY,
            venue_id UUID NOT NULL UNIQUE REFERENCES venues(id) ON DELETE CASCADE,
            customer_payment_model VARCHAR(50) NOT NULL DEFAULT 'THEATRE_DIRECT',
            payment_provider VARCHAR(100) NOT NULL DEFAULT 'THEATRE_GATEWAY',
            commission_model VARCHAR(50) NOT NULL DEFAULT 'INVOICE_POST_PAY',
            rate_type VARCHAR(50) NOT NULL DEFAULT 'PER_TICKET',
            rate_value NUMERIC(10, 4) NOT NULL DEFAULT 30.0000,
            fixed_fee_paise INTEGER NOT NULL DEFAULT 3000,
            calculation_base VARCHAR(50) NOT NULL DEFAULT 'GROSS_TICKET',
            invoice_cycle VARCHAR(50) NOT NULL DEFAULT 'DAILY',
            due_days INTEGER NOT NULL DEFAULT 1,
            currency VARCHAR(10) NOT NULL DEFAULT 'INR',
            reconciliation_source VARCHAR(50) NOT NULL DEFAULT 'API_WEBHOOK',
            refund_treatment VARCHAR(50) NOT NULL DEFAULT 'DEDUCT_COMMISSION',
            contract_ref VARCHAR(100),
            effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_theatre_payment_configs_venue_id ON theatre_payment_configs(venue_id)")

    # 3. theatre_config_history
    op.execute("""
        CREATE TABLE IF NOT EXISTS theatre_config_history (
            id UUID PRIMARY KEY,
            venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
            changed_by UUID,
            changed_by_name VARCHAR(255),
            change_reason TEXT,
            previous_config_json TEXT NOT NULL,
            new_config_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_theatre_config_history_venue_id ON theatre_config_history(venue_id)")

    # 4. commission_invoices
    op.execute("""
        CREATE TABLE IF NOT EXISTS commission_invoices (
            id UUID PRIMARY KEY,
            invoice_number VARCHAR(100) NOT NULL UNIQUE,
            venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            booking_count INTEGER NOT NULL DEFAULT 0,
            ticket_count INTEGER NOT NULL DEFAULT 0,
            gross_sales_paise INTEGER NOT NULL DEFAULT 0,
            commission_paise INTEGER NOT NULL DEFAULT 0,
            adjustments_paise INTEGER NOT NULL DEFAULT 0,
            tax_paise INTEGER NOT NULL DEFAULT 0,
            total_paise INTEGER NOT NULL DEFAULT 0,
            paid_paise INTEGER NOT NULL DEFAULT 0,
            balance_paise INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
            issue_date TIMESTAMPTZ,
            due_date TIMESTAMPTZ NOT NULL,
            created_by UUID,
            approved_by UUID,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_invoices_invoice_number ON commission_invoices(invoice_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_invoices_venue_id ON commission_invoices(venue_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_invoices_status ON commission_invoices(status)")

    # 5. commission_ledgers
    op.execute("""
        CREATE TABLE IF NOT EXISTS commission_ledgers (
            id UUID PRIMARY KEY,
            booking_id UUID NOT NULL UNIQUE REFERENCES bookings(id) ON DELETE CASCADE,
            venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
            gross_ticket_paise INTEGER NOT NULL,
            eligible_base_paise INTEGER NOT NULL,
            rate_type VARCHAR(50) NOT NULL DEFAULT 'PER_TICKET',
            rate_value NUMERIC(10, 4) NOT NULL,
            commission_paise INTEGER NOT NULL,
            tax_paise INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(50) NOT NULL DEFAULT 'UNINVOICED',
            invoice_id UUID REFERENCES commission_invoices(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_ledgers_booking_id ON commission_ledgers(booking_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_ledgers_venue_id ON commission_ledgers(venue_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_ledgers_status ON commission_ledgers(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_ledgers_invoice_id ON commission_ledgers(invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_ledgers_created_at ON commission_ledgers(created_at)")

    # 6. commission_invoice_items
    op.execute("""
        CREATE TABLE IF NOT EXISTS commission_invoice_items (
            id UUID PRIMARY KEY,
            invoice_id UUID NOT NULL REFERENCES commission_invoices(id) ON DELETE CASCADE,
            ledger_id UUID REFERENCES commission_ledgers(id) ON DELETE SET NULL,
            description VARCHAR(255) NOT NULL,
            item_type VARCHAR(50) NOT NULL DEFAULT 'COMMISSION',
            amount_paise INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_invoice_items_invoice_id ON commission_invoice_items(invoice_id)")

    # 7. commission_collections
    op.execute("""
        CREATE TABLE IF NOT EXISTS commission_collections (
            id UUID PRIMARY KEY,
            invoice_id UUID NOT NULL REFERENCES commission_invoices(id) ON DELETE CASCADE,
            venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
            payment_method VARCHAR(50) NOT NULL DEFAULT 'NEFT',
            payment_ref VARCHAR(100) NOT NULL,
            amount_paise INTEGER NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'CONFIRMED',
            collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_by UUID,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_collections_invoice_id ON commission_collections(invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_collections_venue_id ON commission_collections(venue_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_collections_payment_ref ON commission_collections(payment_ref)")

    # 8. reconciliation_exceptions
    op.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_exceptions (
            id UUID PRIMARY KEY,
            exception_type VARCHAR(100) NOT NULL,
            booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
            venue_id UUID REFERENCES venues(id) ON DELETE SET NULL,
            external_ref VARCHAR(100),
            severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
            status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
            discrepancy_details TEXT NOT NULL,
            resolution_notes TEXT,
            assigned_to UUID,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_reconciliation_exceptions_exception_type ON reconciliation_exceptions(exception_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reconciliation_exceptions_booking_id ON reconciliation_exceptions(booking_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reconciliation_exceptions_venue_id ON reconciliation_exceptions(venue_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reconciliation_exceptions_external_ref ON reconciliation_exceptions(external_ref)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reconciliation_exceptions_status ON reconciliation_exceptions(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reconciliation_exceptions_created_at ON reconciliation_exceptions(created_at)")

    # 9. admin_audit_logs
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_logs (
            id UUID PRIMARY KEY,
            user_id UUID,
            user_name VARCHAR(255),
            user_role VARCHAR(50),
            action VARCHAR(100) NOT NULL,
            target_type VARCHAR(100) NOT NULL,
            target_id VARCHAR(100),
            details_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_user_id ON admin_audit_logs(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_action ON admin_audit_logs(action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_created_at ON admin_audit_logs(created_at)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS admin_audit_logs")
    op.execute("DROP TABLE IF EXISTS reconciliation_exceptions")
    op.execute("DROP TABLE IF EXISTS commission_collections")
    op.execute("DROP TABLE IF EXISTS commission_invoice_items")
    op.execute("DROP TABLE IF EXISTS commission_ledgers")
    op.execute("DROP TABLE IF EXISTS commission_invoices")
    op.execute("DROP TABLE IF EXISTS theatre_config_history")
    op.execute("DROP TABLE IF EXISTS theatre_payment_configs")
    op.execute("DROP TABLE IF EXISTS theatre_chains")
