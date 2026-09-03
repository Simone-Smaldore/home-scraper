"""Vercel entrypoint.

Vercel serves any module-level ASGI application named `app` found in a file
under /api. The FastAPI app itself lives in backend/, which is not on the path
of the serverless bundle, so we add it here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
