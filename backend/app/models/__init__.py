"""SQLAlchemy models.

Every model is imported here so that Alembic's autogenerate sees the complete
metadata from a single import.
"""

from app.models.base import Base
from app.models.listing import Listing, PriceHistory
from app.models.review import Review
from app.models.scrape_run import ScrapeRun

__all__ = ["Base", "Listing", "PriceHistory", "Review", "ScrapeRun"]
