-- CloudLedger PostgreSQL Schema
-- Supports AWS FOCUS 1.2 billing ingestion → variance analysis pipeline

BEGIN;

-- 1. Raw landing table: one row per FOCUS 1.2 billing line item
--    Loaded as-is from CSV; no transforms applied at ingestion time.
CREATE TABLE IF NOT EXISTS raw_focus_export (
    id                  BIGSERIAL PRIMARY KEY,
    billing_period      DATE         NOT NULL,
    service_name        TEXT         NOT NULL,
    service_category    TEXT,
    resource_id         TEXT,
    resource_name       TEXT,
    account_id          TEXT         NOT NULL,
    account_name        TEXT,
    region              TEXT,
    availability_zone   TEXT,
    charge_type         TEXT,          -- Usage, Tax, Credit, etc.
    charge_description  TEXT,
    pricing_unit        TEXT,
    usage_quantity      NUMERIC(20,6),
    billed_cost         NUMERIC(20,6) NOT NULL,
    effective_cost      NUMERIC(20,6),
    list_cost           NUMERIC(20,6),
    pricing_category    TEXT,          -- OnDemand, Spot, Committed, etc.
    commitment_discount TEXT,
    tags                JSONB,
    ingested_at         TIMESTAMPTZ  DEFAULT NOW(),
    source_file         TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_billing_period ON raw_focus_export (billing_period);
CREATE INDEX IF NOT EXISTS idx_raw_account_id     ON raw_focus_export (account_id);
CREATE INDEX IF NOT EXISTS idx_raw_service_name   ON raw_focus_export (service_name);
CREATE INDEX IF NOT EXISTS idx_raw_resource_id    ON raw_focus_export (resource_id);

-- 2. Dimension: services
CREATE TABLE IF NOT EXISTS dim_service (
    service_key      SERIAL PRIMARY KEY,
    service_name     TEXT NOT NULL UNIQUE,
    service_category TEXT
);

-- 3. Dimension: resources
CREATE TABLE IF NOT EXISTS dim_resource (
    resource_key  SERIAL PRIMARY KEY,
    resource_id   TEXT NOT NULL UNIQUE,
    resource_name TEXT,
    service_key   INT REFERENCES dim_service(service_key),
    account_key   INT,  -- FK added after dim_account is created
    region        TEXT,
    first_seen    DATE,
    last_seen     DATE
);

-- 4. Dimension: accounts
CREATE TABLE IF NOT EXISTS dim_account (
    account_key  SERIAL PRIMARY KEY,
    account_id   TEXT NOT NULL UNIQUE,
    account_name TEXT
);

ALTER TABLE dim_resource
    ADD CONSTRAINT fk_resource_account
    FOREIGN KEY (account_key) REFERENCES dim_account(account_key);

-- 5. Terraform expected state: parsed from terraform show -json
CREATE TABLE IF NOT EXISTS terraform_resources (
    id              SERIAL PRIMARY KEY,
    tf_address      TEXT NOT NULL,       -- e.g. module.vpc.aws_subnet.private[0]
    resource_type   TEXT NOT NULL,       -- e.g. aws_instance
    resource_id     TEXT,                -- AWS resource ID from state
    account_id      TEXT,
    region          TEXT,
    monthly_cost_expected NUMERIC(20,6), -- from Infracost or manual tag
    tags            JSONB,
    loaded_at       TIMESTAMPTZ DEFAULT NOW(),
    state_file      TEXT
);

CREATE INDEX IF NOT EXISTS idx_tf_resource_id ON terraform_resources (resource_id);

-- 6. Variance report: one row per resource per billing period
CREATE TABLE IF NOT EXISTS variance_report (
    id              BIGSERIAL PRIMARY KEY,
    billing_period  DATE       NOT NULL,
    resource_id     TEXT,
    service_name    TEXT       NOT NULL,
    account_id      TEXT       NOT NULL,
    prior_cost      NUMERIC(20,6),  -- previous period billed cost
    current_cost    NUMERIC(20,6),  -- this period billed cost
    expected_cost   NUMERIC(20,6),  -- from terraform_resources or baseline
    variance_abs    NUMERIC(20,6),  -- current - prior
    variance_pct    NUMERIC(10,4),  -- (current - prior) / prior * 100
    reason_code     TEXT CHECK (reason_code IN ('planned', 'drift', 'usage_growth')),
    reason_detail   TEXT,
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_variance_period ON variance_report (billing_period);
CREATE INDEX IF NOT EXISTS idx_variance_reason ON variance_report (reason_code);

COMMIT;
