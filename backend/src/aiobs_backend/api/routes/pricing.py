"""Pricing table (admin): CRUD over provider/model prices."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import CostRecord, Pricing
from ..deps import get_admin_key, get_db

router = APIRouter(tags=["pricing"], dependencies=[Depends(get_admin_key)])


class PricingIn(BaseModel):
    provider: str
    model: str
    model_match: str = Field(default="exact", pattern="^(exact|prefix|default)$")
    input_price_per_1m: float = Field(ge=0)
    output_price_per_1m: float = Field(ge=0)
    cache_read_price_per_1m: float | None = None
    cache_write_price_per_1m: float | None = None
    reasoning_price_per_1m: float | None = None
    currency: str = "USD"
    effective_from: datetime | None = None


@router.get("/pricing")
def list_pricing(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(
        select(Pricing).order_by(Pricing.provider, Pricing.model)
    ).scalars().all()
    items = [
        {
            "id": p.id,
            "provider": p.provider,
            "model": p.model,
            "model_match": p.model_match,
            "input_price_per_1m": float(p.input_price_per_1m),
            "output_price_per_1m": float(p.output_price_per_1m),
            "cache_read_price_per_1m": float(p.cache_read_price_per_1m) if p.cache_read_price_per_1m is not None else None,
            "cache_write_price_per_1m": float(p.cache_write_price_per_1m) if p.cache_write_price_per_1m is not None else None,
            "reasoning_price_per_1m": float(p.reasoning_price_per_1m) if p.reasoning_price_per_1m is not None else None,
            "currency": p.currency,
            "effective_from": p.effective_from.isoformat() if p.effective_from else None,
        }
        for p in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/pricing")
def create_pricing(body: PricingIn, session: Session = Depends(get_db)) -> dict:
    pricing = Pricing(
        provider=body.provider.lower(),
        model=body.model,
        model_match=body.model_match,
        input_price_per_1m=body.input_price_per_1m,
        output_price_per_1m=body.output_price_per_1m,
        cache_read_price_per_1m=body.cache_read_price_per_1m,
        cache_write_price_per_1m=body.cache_write_price_per_1m,
        reasoning_price_per_1m=body.reasoning_price_per_1m,
        currency=body.currency,
        effective_from=body.effective_from or datetime.now(timezone.utc),
    )
    session.add(pricing)
    session.flush()
    session.commit()
    return {"id": pricing.id, "effective_from": pricing.effective_from.isoformat()}


@router.delete("/pricing/{pricing_id}")
def delete_pricing(pricing_id: str, session: Session = Depends(get_db)) -> dict:
    pricing = session.execute(
        select(Pricing).where(Pricing.id == pricing_id)
    ).scalar_one_or_none()
    if pricing is None:
        raise HTTPException(status_code=404, detail="pricing not found")
    # Price history is immutable once it has priced real traffic (F30): the
    # resolved rates are also snapshotted on each cost record.
    referenced = session.execute(
        select(CostRecord.id).where(CostRecord.price_version == pricing_id).limit(1)
    ).first()
    if referenced is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "pricing row is referenced by cost records; add a newer "
                "effective-dated price instead of deleting history"
            ),
        )
    session.delete(pricing)
    session.commit()
    return {"deleted": pricing_id}