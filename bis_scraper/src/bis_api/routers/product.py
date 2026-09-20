"""``/api/v1/product/recommend`` -- product to standards recommendation."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ConfigDict

from bis_rag.products import recommend_for_product

from ..deps import get_services, require_api_key
from ..services import AppServices

router = APIRouter(prefix="/api/v1", tags=["product"])


class ProductRecommendationOut(BaseModel):
    """Product recommendation response."""
    model_config = ConfigDict(extra="allow")
    
    product: dict
    primary: list[dict]
    related: list[dict]
    mandatory: dict
    checklist: list[dict]
    coverage: dict
    took_ms: float


@router.post(
    "/product/recommend",
    response_model=ProductRecommendationOut,
    dependencies=[Depends(require_api_key)],
    summary="Recommend standards for a product",
)
async def product_recommend_post(
    description: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(8, ge=1, le=20),
    services: AppServices = Depends(get_services),
) -> ProductRecommendationOut:
    """
    Recommend applicable Indian Standards for a product.
    
    - `description`: What you make (e.g., "50 kg bags of 43 grade OPC cement")
    - `limit`: Max primary results (capped at 5 internally)
    - Returns: Primary standards, related standards (test methods, codes), 
               mandatory flags, and evidence for each recommendation
    """
    if not description.strip():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail="description cannot be empty"
        )
    
    data = services.require_data()
    search = services.require_search()
    
    recommendation = recommend_for_product(data, search, description, limit=limit)
    
    return ProductRecommendationOut(
        product={
            "raw": recommendation.product.raw,
            "normalized": recommendation.product.normalized,
            "sector": recommendation.product.sector,
            "aliases_matched": [
                {"alias": a[0], "designations": a[1]}
                for a in recommendation.product.aliases_matched
            ],
        },
        primary=[
            {
                "designation": r.designation,
                "title": r.title,
                "role": r.role,
                "is_current": r.is_current,
                "is_mandatory": r.is_mandatory,
                "score": round(r.score, 3),
                "why": r.why,
            }
            for r in recommendation.primary
        ],
        related=[
            {
                "designation": r.designation,
                "title": r.title,
                "role": r.role,
                "is_current": r.is_current,
                "is_mandatory": r.is_mandatory,
                "score": round(r.score, 3),
                "why": r.why,
            }
            for r in recommendation.related
        ],
        mandatory={k: v for k, v in recommendation.mandatory.items()},
        checklist=recommendation.checklist,
        coverage=recommendation.coverage,
        took_ms=round(recommendation.took_ms, 2),
    )


@router.get(
    "/product/recommend",
    response_model=ProductRecommendationOut,
    dependencies=[Depends(require_api_key)],
    summary="Recommend standards for a product (GET)",
)
async def product_recommend_get(
    description: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(8, ge=1, le=20),
    services: AppServices = Depends(get_services),
) -> ProductRecommendationOut:
    """GET variant of /product/recommend for browser testing."""
    return await product_recommend_post(description, limit, services)
