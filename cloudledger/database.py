"""SQLAlchemy engine, session factory, and table definitions.

Five tables only: raw_billing_lines, invoices, resources, change_events, variance_report.
"""

from contextlib import contextmanager
from sqlalchemy import (
    create_engine, Column, Integer, String, Date, DateTime, Numeric,
    Boolean, Text, JSON, UniqueConstraint, Index, func,
)
from sqlalchemy.orm import sessionmaker, declarative_base

from cloudledger.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


@contextmanager
def get_db():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class RawBillingLine(Base):
    """One row per charge line from FOCUS 1.2 CSV exports."""
    __tablename__ = "raw_billing_lines"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(String(50))
    billing_period_start = Column(Date)
    billing_period_end = Column(Date)
    charge_period_start = Column(DateTime)
    charge_period_end = Column(DateTime)
    service_name = Column(String(100))
    service_category = Column(String(50))
    resource_id = Column(String(200))
    resource_name = Column(String(200))
    region = Column(String(50))
    availability_zone = Column(String(50))
    charge_type = Column(String(50))
    description = Column(Text)
    quantity = Column(Numeric(18, 6))
    unit = Column(String(50))
    unit_price = Column(Numeric(18, 10))
    billed_cost = Column(Numeric(18, 6))
    list_cost = Column(Numeric(18, 6))
    effective_cost = Column(Numeric(18, 6))
    tags = Column(JSON)
    provider = Column(String(20), default="AWS")
    loaded_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_raw_billing_period", "billing_period_start"),
        Index("ix_raw_resource_id", "resource_id"),
        Index("ix_raw_invoice_id", "invoice_id"),
    )


class Invoice(Base):
    """One row per invoice with aggregated totals."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(String(50), unique=True, nullable=False)
    billing_period_start = Column(Date, nullable=False)
    billing_period_end = Column(Date, nullable=False)
    provider = Column(String(20), default="AWS")
    total_billed_cost = Column(Numeric(18, 2))
    total_line_items = Column(Integer)
    attributed_cost = Column(Numeric(18, 2))
    unattributed_cost = Column(Numeric(18, 2))
    attribution_coverage_pct = Column(Numeric(5, 2))
    status = Column(String(20), default="provisional")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class Resource(Base):
    """One row per unique resource per billing period."""
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    resource_id = Column(String(200), nullable=False)
    resource_name = Column(String(200))
    service_name = Column(String(100))
    service_category = Column(String(50))
    region = Column(String(50))
    provider = Column(String(20), default="AWS")
    team = Column(String(100))
    cost_center = Column(String(100))
    in_terraform_state = Column(Boolean, default=False)
    terraform_module = Column(String(200))
    iac_source = Column(String(50))
    environment = Column(String(20))
    billing_period_start = Column(Date)
    total_cost = Column(Numeric(18, 2))

    __table_args__ = (
        UniqueConstraint("resource_id", "billing_period_start"),
        Index("ix_resource_billing_period", "billing_period_start"),
        Index("ix_resource_resource_id", "resource_id"),
        Index("ix_resource_in_terraform", "in_terraform_state"),
    )


class ChangeEvent(Base):
    """Infrastructure changes (PR merges, terraform applies)."""
    __tablename__ = "change_events"

    id = Column(Integer, primary_key=True)
    resource_id = Column(String(200))
    event_type = Column(String(50))
    event_date = Column(Date)
    pr_number = Column(String(50))
    pr_title = Column(Text)
    pr_author = Column(String(100))
    commit_sha = Column(String(64))
    terraform_module = Column(String(200))
    description = Column(Text)
    estimated_cost_delta = Column(Numeric(18, 2))
    created_at = Column(DateTime, server_default=func.now())


class VarianceReport(Base):
    """Month-over-month cost variance with reason codes."""
    __tablename__ = "variance_report"

    id = Column(Integer, primary_key=True)
    resource_id = Column(String(200))
    resource_name = Column(String(200))
    service_name = Column(String(100))
    team = Column(String(100))
    cost_center = Column(String(100))
    prior_period_start = Column(Date)
    current_period_start = Column(Date)
    prior_cost = Column(Numeric(18, 2), default=0)
    current_cost = Column(Numeric(18, 2), default=0)
    delta_dollars = Column(Numeric(18, 2))
    delta_pct = Column(Numeric(8, 2))
    reason_code = Column(String(50))
    confidence_score = Column(Numeric(3, 2))
    evidence = Column(Text)
    evidence_chain = Column(JSON)
    pr_number = Column(String(50))
    pr_author = Column(String(100))
    iac_source = Column(String(50))
    in_terraform_state = Column(Boolean, default=False)
    reviewed = Column(Boolean, default=False)
    excluded = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("resource_id", "prior_period_start", "current_period_start"),
        Index("ix_variance_reason_code", "reason_code"),
    )


class LogicalResource(Base):
    """Groups related billing line items under a logical resource (e.g. EKS cluster + nodes)."""
    __tablename__ = "logical_resources"

    id = Column(Integer, primary_key=True)
    logical_resource_id = Column(String(200), nullable=False)
    logical_resource_name = Column(String(200))
    resource_type = Column(String(50))
    child_resource_id = Column(String(200), nullable=False)
    relationship = Column(String(50))
    billing_period_start = Column(Date)

    __table_args__ = (
        Index("ix_logical_resource_period", "billing_period_start"),
        Index("ix_logical_resource_id", "logical_resource_id"),
    )


def create_all_tables():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)
