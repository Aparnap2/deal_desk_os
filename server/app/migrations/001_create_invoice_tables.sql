-- Invoice System Migration Script
-- Creates tables for invoice staging and accounting integration

-- Create invoice staging table
CREATE TABLE IF NOT EXISTS invoice_staging (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    deal_id VARCHAR(36) NOT NULL,
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',

    -- Customer details
    customer_name VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255),
    customer_address JSON,
    customer_tax_id VARCHAR(50),

    -- Financial details
    subtotal DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0 NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',

    -- Invoice metadata
    invoice_date TIMESTAMP WITH TIME ZONE NOT NULL,
    due_date TIMESTAMP WITH TIME ZONE NOT NULL,
    payment_terms_days INTEGER DEFAULT 30,
    description TEXT,

    -- Approval workflow
    submitted_for_approval_at TIMESTAMP WITH TIME ZONE,
    approved_at TIMESTAMP WITH TIME ZONE,
    approved_by VARCHAR(36),
    rejected_at TIMESTAMP WITH TIME ZONE,
    rejected_by VARCHAR(36),
    rejection_reason TEXT,

    -- ERP integration
    target_accounting_system VARCHAR(50) NOT NULL,
    erp_customer_id VARCHAR(100),
    erp_item_mapping JSON,

    -- Tracking and validation
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    validation_errors JSON,
    preview_data JSON,

    -- Metadata
    created_by VARCHAR(36),
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE,
    FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (rejected_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Create indexes for invoice staging
CREATE INDEX IF NOT EXISTS ix_invoice_staging_deal_status ON invoice_staging(deal_id, status);
CREATE INDEX IF NOT EXISTS ix_invoice_staging_invoice_number ON invoice_staging(invoice_number);
CREATE INDEX IF NOT EXISTS ix_invoice_staging_created_at ON invoice_staging(created_at);

-- Create invoice staging line items table
CREATE TABLE IF NOT EXISTS invoice_staging_line_items (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    staging_id VARCHAR(36) NOT NULL,
    line_number INTEGER NOT NULL,

    -- Item details
    description VARCHAR(500) NOT NULL,
    sku VARCHAR(100),
    quantity DECIMAL(12,4) NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    discount_percent DECIMAL(5,2) DEFAULT 0 NOT NULL,

    -- Calculated amounts
    line_total DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0 NOT NULL,
    tax_type VARCHAR(50),

    -- ERP mapping
    erp_item_id VARCHAR(100),
    erp_account_id VARCHAR(100),
    erp_tax_code VARCHAR(50),

    -- Metadata
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign key
    FOREIGN KEY (staging_id) REFERENCES invoice_staging(id) ON DELETE CASCADE
);

-- Create invoice staging tax calculations table
CREATE TABLE IF NOT EXISTS invoice_staging_taxes (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    staging_id VARCHAR(36) NOT NULL,

    -- Tax details
    tax_name VARCHAR(100) NOT NULL,
    tax_rate DECIMAL(8,4) NOT NULL,
    taxable_amount DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) NOT NULL,

    -- Tax jurisdiction
    tax_jurisdiction VARCHAR(100),
    tax_type VARCHAR(50) DEFAULT 'auto',

    -- ERP mapping
    erp_tax_code VARCHAR(50),
    erp_tax_account VARCHAR(100),

    -- Metadata
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign key
    FOREIGN KEY (staging_id) REFERENCES invoice_staging(id) ON DELETE CASCADE
);

-- Create final invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    staging_id VARCHAR(36),
    deal_id VARCHAR(36) NOT NULL,
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'posted',

    -- Financial details (copied from staging for audit)
    customer_name VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255),
    subtotal DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0 NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,

    -- Invoice metadata
    invoice_date TIMESTAMP WITH TIME ZONE NOT NULL,
    due_date TIMESTAMP WITH TIME ZONE NOT NULL,
    description TEXT,

    -- ERP integration details
    accounting_system VARCHAR(50) NOT NULL,
    erp_invoice_id VARCHAR(100),
    erp_customer_id VARCHAR(100),
    erp_url VARCHAR(500),

    -- Posting details
    posted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    posted_by VARCHAR(36),
    posting_response JSON,

    -- Payment tracking
    paid_amount DECIMAL(12,2) DEFAULT 0 NOT NULL,
    paid_at TIMESTAMP WITH TIME ZONE,
    payment_reference VARCHAR(100),

    -- Cancellation/void details
    voided_at TIMESTAMP WITH TIME ZONE,
    voided_by VARCHAR(36),
    void_reason TEXT,

    -- Audit trail
    staging_snapshot JSON,
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (staging_id) REFERENCES invoice_staging(id) ON DELETE SET NULL,
    FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE,
    FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (voided_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Create indexes for invoices
CREATE INDEX IF NOT EXISTS ix_invoice_deal_status ON invoices(deal_id, status);
CREATE INDEX IF NOT EXISTS ix_invoice_erp_id ON invoices(accounting_system, erp_invoice_id);
CREATE INDEX IF NOT EXISTS ix_invoice_posted_at ON invoices(posted_at);

-- Create invoice line items table
CREATE TABLE IF NOT EXISTS invoice_line_items (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    invoice_id VARCHAR(36) NOT NULL,
    staging_line_item_id VARCHAR(36),
    line_number INTEGER NOT NULL,

    -- Item details (copied from staging for audit)
    description VARCHAR(500) NOT NULL,
    sku VARCHAR(100),
    quantity DECIMAL(12,4) NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    discount_percent DECIMAL(5,2) DEFAULT 0 NOT NULL,

    -- Calculated amounts
    line_total DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0 NOT NULL,
    tax_type VARCHAR(50),

    -- ERP references
    erp_line_item_id VARCHAR(100),
    erp_item_id VARCHAR(100),

    -- Metadata
    staging_snapshot JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (staging_line_item_id) REFERENCES invoice_staging_line_items(id) ON DELETE SET NULL
);

-- Create invoice tax calculations table
CREATE TABLE IF NOT EXISTS invoice_taxes (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    invoice_id VARCHAR(36) NOT NULL,
    staging_tax_id VARCHAR(36),

    -- Tax details (copied from staging for audit)
    tax_name VARCHAR(100) NOT NULL,
    tax_rate DECIMAL(8,4) NOT NULL,
    taxable_amount DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) NOT NULL,

    -- Tax jurisdiction
    tax_jurisdiction VARCHAR(100),
    tax_type VARCHAR(50) DEFAULT 'auto',

    -- ERP references
    erp_tax_line_id VARCHAR(100),

    -- Metadata
    staging_snapshot JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (staging_tax_id) REFERENCES invoice_staging_taxes(id) ON DELETE SET NULL
);

-- Create accounting integrations table
CREATE TABLE IF NOT EXISTS accounting_integrations (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    name VARCHAR(100) NOT NULL,
    system_type VARCHAR(50) NOT NULL,

    -- Connection details
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    connection_config JSON NOT NULL,

    -- Default settings
    default_currency VARCHAR(3) DEFAULT 'USD',
    default_tax_codes JSON,
    default_account_mapping JSON,

    -- Validation
    last_tested_at TIMESTAMP WITH TIME ZONE,
    test_result BOOLEAN DEFAULT FALSE NOT NULL,
    error_message TEXT,

    -- Metadata
    created_by VARCHAR(36),
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign key
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Create indexes for accounting integrations
CREATE INDEX IF NOT EXISTS ix_accounting_integration_system_type ON accounting_integrations(system_type);
CREATE INDEX IF NOT EXISTS ix_accounting_integration_active ON accounting_integrations(is_active);

-- Update deals table to add invoice tracking fields
ALTER TABLE deals
ADD COLUMN IF NOT EXISTS invoice_generated_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS last_invoiced_at TIMESTAMP WITH TIME ZONE;

-- Update audit_logs table to support invoice references
ALTER TABLE audit_logs
ADD COLUMN IF NOT EXISTS invoice_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS staged_invoice_id VARCHAR(36);

-- Add foreign key constraints for audit logs
ALTER TABLE audit_logs
ADD CONSTRAINT IF NOT EXISTS fk_audit_logs_invoice
FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
ADD CONSTRAINT IF NOT EXISTS fk_audit_logs_staged_invoice
FOREIGN KEY (staged_invoice_id) REFERENCES invoice_staging(id) ON DELETE CASCADE;

-- Create indexes for audit logs invoice references
CREATE INDEX IF NOT EXISTS ix_audit_logs_invoice_id ON audit_logs(invoice_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_staged_invoice_id ON audit_logs(staged_invoice_id);

-- Insert initial accounting integration configurations (optional)
-- This would be done through the API, but here's an example
-- INSERT INTO accounting_integrations (name, system_type, connection_config, default_currency, created_by) VALUES
-- ('QuickBooks Online', 'quickbooks', '{"environment": "sandbox", "client_id": "", "client_secret": "", "refresh_token": "", "realm_id": ""}', 'USD', NULL),
-- ('NetSuite', 'netsuite', '{"account_id": "", "consumer_key": "", "consumer_secret": "", "token_id": "", "token_secret": "", "environment": "sandbox"}', 'USD', NULL),
-- ('SAP Business One', 'sap', '{"server_url": "", "company_db": "", "username": "", "password": ""}', 'USD', NULL);