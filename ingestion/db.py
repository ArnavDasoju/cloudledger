"""Shared database connection factory for CloudLedger."""

import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()


def get_engine():
    """Build a SQLAlchemy engine from environment variables."""
    url = (
        f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}"
        f"/{os.environ['POSTGRES_DB']}"
    )
    return create_engine(url, echo=False)
