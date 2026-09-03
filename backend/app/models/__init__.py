"""SQLAlchemy models.

Every model is imported here so that Alembic's autogenerate sees the complete
metadata from a single import. Empty at M0: the tables arrive with M1.
"""

from app.models.base import Base

__all__ = ["Base"]
