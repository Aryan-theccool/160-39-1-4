"""FastAPI dependencies: shared services, and optional API-key auth.

The services live on ``app.state`` rather than in a module-level global so that
``create_app()`` can be called more than once in a process -- which is what the
tests do, once per fixture, against different data directories.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status

from .config import Settings
from .services import AppServices

__all__ = ["get_services", "get_settings", "require_api_key"]


def get_services(request: Request) -> AppServices:
    services = getattr(request.app.state, "services", None)
    if services is None:  # pragma: no cover - only if lifespan was skipped
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="services are not initialised",
        )
    return services


def get_settings(request: Request) -> Settings:
    return get_services(request).settings


async def require_api_key(request: Request,
                          x_api_key: str | None = Header(default=None)) -> None:
    """Enforce ``X-API-Key`` only when ``BIS_API_KEY`` is configured.

    Optional by design: the default deployment has no key so the frontend and
    Swagger UI work out of the box. When a key *is* set it is compared with
    :func:`secrets.compare_digest`, because a plain ``==`` on a secret leaks its
    length and prefix through timing.
    """
    settings: Settings = get_settings(request)
    expected = settings.api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key header",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
