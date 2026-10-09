"""Alert rules: configurable thresholds scoped to org units (audit item 7).

Admin key/admin session and `exec` manage any rule; managers manage rules whose
scope they cover and may read global (built-in) rules. Built-ins seeded from the
old env thresholds can be disabled or edited but not deleted.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import AlertRule
from ..deps import AccessScope, get_db, require_access
from ..memberships import approved_memberships, covers_scope, scope_exists, scope_name

router = APIRouter(tags=["alert-rules"])

MetricName = Literal[
    "error_rate", "daily_tokens", "tool_calls_per_execution", "p95_latency", "cost_anomaly"
]
ScopeType = Literal["global", "department", "team", "project"]


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric: MetricName
    warning_threshold: float = Field(ge=0)
    critical_threshold: float = Field(gt=0)
    scope_type: ScopeType = "global"
    scope_id: str | None = Field(default=None, max_length=32)


class AlertRulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    warning_threshold: float | None = Field(default=None, ge=0)
    critical_threshold: float | None = Field(default=None, gt=0)
    enabled: bool | None = None


def _is_unrestricted(access: AccessScope) -> bool:
    """Admin key/session, or any global grant (exec): every rule is fair game."""
    return access.unrestricted or access.project_ids is None


def _memberships(session: Session, access: AccessScope):
    if access.user is None:
        return []
    return approved_memberships(session, access.user.id)


def _validate_scope(session: Session, body: AlertRuleIn) -> tuple[str, str | None]:
    if body.scope_type == "global":
        return "global", None
    if not body.scope_id:
        raise HTTPException(status_code=422, detail="scope_id is required")
    if not scope_exists(session, body.scope_type, body.scope_id):
        raise HTTPException(status_code=404, detail="unknown scope")
    return body.scope_type, body.scope_id


def _assert_covers(
    session: Session, access: AccessScope, scope_type: str, scope_id: str | None
) -> None:
    if _is_unrestricted(access):
        return
    if scope_type == "global":
        raise HTTPException(
            status_code=403, detail="global rules require an exec or admin"
        )
    if not covers_scope(session, _memberships(session, access), scope_type, scope_id or ""):
        raise HTTPException(status_code=403, detail="you do not manage this scope")


def _rule_dict(session: Session, rule: AlertRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "metric": rule.metric,
        "warning_threshold": float(rule.warning_threshold),
        "critical_threshold": float(rule.critical_threshold),
        "scope_type": rule.scope_type,
        "scope_id": rule.scope_id,
        "scope_name": scope_name(session, rule.scope_type, rule.scope_id),
        "enabled": rule.enabled,
        "builtin": rule.builtin,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _load_rule(session: Session, rule_id: str) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    return rule


@router.get("/alert-rules")
def list_alert_rules(
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    rules = (
        session.execute(select(AlertRule).order_by(AlertRule.created_at.desc()))
        .scalars()
        .all()
    )
    if not _is_unrestricted(access):
        memberships = _memberships(session, access)
        rules = [
            r
            for r in rules
            if r.scope_type == "global"
            or (
                r.scope_id
                and covers_scope(session, memberships, r.scope_type, r.scope_id)
            )
        ]
    items = [_rule_dict(session, r) for r in rules]
    return {"items": items, "total": len(items)}


@router.post("/alert-rules")
def create_alert_rule(
    body: AlertRuleIn,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    scope_type, scope_id = _validate_scope(session, body)
    _assert_covers(session, access, scope_type, scope_id)
    if body.critical_threshold < body.warning_threshold:
        raise HTTPException(
            status_code=422, detail="critical_threshold must be >= warning_threshold"
        )
    rule = AlertRule(
        name=body.name,
        metric=body.metric,
        warning_threshold=Decimal(str(body.warning_threshold)),
        critical_threshold=Decimal(str(body.critical_threshold)),
        scope_type=scope_type,
        scope_id=scope_id,
        created_by=access.user.id if access.user else None,
    )
    session.add(rule)
    session.flush()
    session.commit()
    return _rule_dict(session, rule)


@router.patch("/alert-rules/{rule_id}")
def update_alert_rule(
    rule_id: str,
    body: AlertRulePatch,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    rule = _load_rule(session, rule_id)
    _assert_covers(session, access, rule.scope_type, rule.scope_id)

    fields = body.model_dump(exclude_unset=True)
    warning = (
        body.warning_threshold
        if "warning_threshold" in fields and body.warning_threshold is not None
        else float(rule.warning_threshold)
    )
    critical = (
        body.critical_threshold
        if "critical_threshold" in fields and body.critical_threshold is not None
        else float(rule.critical_threshold)
    )
    if critical < warning:
        raise HTTPException(
            status_code=422, detail="critical_threshold must be >= warning_threshold"
        )
    if "name" in fields and body.name is not None:
        rule.name = body.name
    if "warning_threshold" in fields and body.warning_threshold is not None:
        rule.warning_threshold = Decimal(str(body.warning_threshold))
    if "critical_threshold" in fields and body.critical_threshold is not None:
        rule.critical_threshold = Decimal(str(body.critical_threshold))
    if "enabled" in fields and body.enabled is not None:
        rule.enabled = body.enabled
    session.flush()
    session.commit()
    return _rule_dict(session, rule)


@router.delete("/alert-rules/{rule_id}")
def delete_alert_rule(
    rule_id: str,
    session: Session = Depends(get_db),
    access: AccessScope = Depends(require_access("manager", "exec")),
) -> dict:
    rule = _load_rule(session, rule_id)
    _assert_covers(session, access, rule.scope_type, rule.scope_id)
    if rule.builtin:
        raise HTTPException(
            status_code=409, detail="system rule: disable it instead of deleting"
        )
    session.delete(rule)
    session.commit()
    return {"deleted": rule_id}
