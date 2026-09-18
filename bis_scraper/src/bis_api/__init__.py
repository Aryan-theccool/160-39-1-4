"""HTTP API over the BIS retrieval engine (Part 5).

    uvicorn bis_api.main:app --host 0.0.0.0 --port 8000

Endpoints
---------
``GET  /api/v1/health``              component status, corpus size, issues
``GET  /api/v1/search``              retrieval only, no LLM -- the fast path
``POST /api/v1/recommend``           grounded answer with verified citations
``POST /api/v1/recommend/pdf``       same, from an uploaded specification sheet
``POST /api/v1/compliance/check``    QCO compliance verdict
``GET  /api/v1/compliance/report``   printable HTML gap report
``GET  /api/v1/standards``           browse, with facets
``GET  /api/v1/standards/{is}``      one standard, including supersession
``POST /api/v1/feedback``            record whether an answer helped

``GET /`` serves a small console so the API can be exercised without the
Next.js frontend.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import Settings, settings_from_env
from .main import create_app
from .services import AppServices, ServiceUnavailable

__all__ = [
    "__version__", "create_app", "AppServices", "ServiceUnavailable",
    "Settings", "settings_from_env",
]
