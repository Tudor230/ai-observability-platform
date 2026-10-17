"""Margin: revenue, manual cost, AI cost, coverage and break-even (ADR-0013).

Revenue and manual cost accrue per day from the *version* active that day
(greatest ``effective_from <= day``), so a mid-window price change shows as a
step instead of rewriting history. Totals are conservative: every AI cost
counts, including projects and days with no active rate, and coverage is
reported beside the totals so a partial rate book is visible rather than
reading as a loss.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Execution, Project, ProjectRate
from ..deps import AccessScope, get_db, require_access
from ..queries import default_range, parse_dt
from ..serialize import money

router = APIRouter(tags=["margin"])

# Calendar-neutral proration: a month is 365/12 days, a year is 365.
YEAR_DAYS = 365.0
MONTH_DAYS = 365.0 / 12.0


def _daily_amount(amount: float, period: str) -> float:
    return amount / (YEAR_DAYS if period == "year" else MONTH_DAYS)


def _window_days(start_dt, end_dt) -> list[date]:
    """Calendar days in ``[start, end)`` — the same window executions use."""
    first = start_dt.date()
    last = (end_dt - timedelta(microseconds=1)).date()
    days = []
    day = first
    while day <= last:
        days.append(day)
        day += timedelta(days=1)
    return days


def _active_version(versions: list[ProjectRate], day: date) -> ProjectRate | None:
    active = None
    for version in versions:
        if version.effective_from <= day:
            active = version
        else:
            break
    return active


@router.get("/margin")
def get_margin(
    session: Session = Depends(get_db),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=3650),
    project_id: str | None = Query(default=None),
    access: AccessScope = Depends(require_access("exec")),
) -> dict:
    end_dt = parse_dt(end, end_of_day=True) or default_range(days)[1]
    start_dt = parse_dt(start) or (end_dt - timedelta(days=days))
    window = _window_days(start_dt, end_dt)

    # Rate versions per project (project-scoped callers narrow with `project_id`).
    rate_stmt = (
        select(ProjectRate, Project.project_id, Project.name)
        .join(Project, Project.id == ProjectRate.project_id)
        .order_by(Project.project_id, ProjectRate.effective_from)
    )
    if project_id:
        rate_stmt = rate_stmt.where(Project.project_id == project_id)
    versions: dict[str, list[ProjectRate]] = {}
    project_meta: dict[str, tuple[str, str | None]] = {}
    for rate, project_ext, project_name in session.execute(rate_stmt).all():
        versions.setdefault(project_ext, []).append(rate)
        project_meta[project_ext] = (project_ext, project_name)

    # AI cost per project per day: the same source as the totals, so coverage
    # and margin can never disagree.
    day_col = func.date(Execution.started_at)
    cost_stmt = (
        select(
            Project.project_id,
            Project.name,
            Project.internal,
            day_col.label("day"),
            func.count().label("executions"),
            func.coalesce(func.sum(Execution.total_cost), 0).label("cost"),
        )
        .join(Project, Project.id == Execution.project_id)
        .where(Execution.started_at >= start_dt, Execution.started_at < end_dt)
        .group_by(Project.project_id, Project.name, Project.internal, day_col)
    )
    if project_id:
        cost_stmt = cost_stmt.where(Project.project_id == project_id)

    cost_by_day: dict[str, dict[date, float]] = {}
    executions_by_project: dict[str, int] = {}
    internal_projects: set[str] = set()
    for project_ext, project_name, internal, day, executions, cost in session.execute(
        cost_stmt
    ).all():
        project_meta.setdefault(project_ext, (project_ext, project_name))
        cost_by_day.setdefault(project_ext, {})[day] = float(cost or 0)
        executions_by_project[project_ext] = (
            executions_by_project.get(project_ext, 0) + executions
        )
        if internal:
            internal_projects.add(project_ext)

    # The flag also has to cover projects that arrive through their rate rows:
    # an internal project with a version must ignore it rather than book revenue.
    # (Projects with neither traffic nor rates stay out of the report entirely.)
    internal_stmt = select(Project.project_id).where(Project.internal.is_(True))
    if project_id:
        internal_stmt = internal_stmt.where(Project.project_id == project_id)
    for (project_ext,) in session.execute(internal_stmt).all():
        internal_projects.add(project_ext)

    series: dict[date, dict] = {
        day: {"revenue": 0.0, "manual_cost": 0.0, "ai_cost": 0.0, "internal_cost": 0.0}
        for day in window
    }

    items = []
    totals = {
        "revenue": 0.0,
        "manual_cost": 0.0,
        "ai_cost": 0.0,
        "internal_cost": 0.0,
        "executions": 0,
        "covered_cost": 0.0,
    }
    for project_ext, (_, project_name) in project_meta.items():
        internal = project_ext in internal_projects
        # An internal project needs no revenue: its versions (if any) are
        # ignored, and its cost is reported as internal spend, not as a loss.
        project_versions = [] if internal else versions.get(project_ext, [])
        day_costs = cost_by_day.get(project_ext, {})
        revenue = 0.0
        manual = 0.0
        covered_days = 0
        covered_cost = 0.0
        for day in window:
            active = _active_version(project_versions, day)
            day_cost = day_costs.get(day, 0.0)
            bucket = series[day]
            if internal:
                bucket["internal_cost"] += day_cost
                continue
            if active is not None:
                day_revenue = _daily_amount(float(active.revenue_amount or 0), active.revenue_period)
                day_manual = _daily_amount(
                    float(active.manual_cost_amount or 0), active.manual_cost_period
                )
                revenue += day_revenue
                manual += day_manual
                covered_days += 1
                covered_cost += day_cost
            else:
                day_revenue = day_manual = 0.0
            bucket["revenue"] += day_revenue
            bucket["manual_cost"] += day_manual
            bucket["ai_cost"] += day_cost

        ai_cost = sum(day_costs.values())
        executions = executions_by_project.get(project_ext, 0)
        margin = (revenue - manual - ai_cost) if covered_days and not internal else None
        contribution = revenue - manual
        cost_per_execution = (ai_cost / executions) if executions else None
        break_even_scale = (
            (contribution / ai_cost) if covered_days and ai_cost > 0 else None
        )
        break_even_executions = (
            (contribution / cost_per_execution)
            if contribution > 0 and cost_per_execution
            else None
        )
        current_rate = _active_version(project_versions, window[-1]) if window else None
        items.append(
            {
                "project_id": project_ext,
                "name": project_name,
                "rate": (
                    {
                        "id": current_rate.id,
                        "effective_from": current_rate.effective_from.isoformat(),
                        "revenue_amount": money(current_rate.revenue_amount),
                        "revenue_period": current_rate.revenue_period,
                        "manual_cost_amount": money(current_rate.manual_cost_amount),
                        "manual_cost_period": current_rate.manual_cost_period,
                    }
                    if current_rate is not None
                    else None
                ),
                "internal": internal,
                "covered_days": covered_days,
                "window_days": len(window),
                "revenue": money(revenue),
                "manual_cost": money(manual),
                "ai_cost": money(ai_cost),
                "margin": money(margin) if margin is not None else None,
                "margin_pct": (
                    round(margin / revenue, 4)
                    if margin is not None and revenue > 0
                    else None
                ),
                "executions": executions,
                "cost_per_execution": (
                    money(cost_per_execution) if cost_per_execution is not None else None
                ),
                "break_even_scale": (
                    round(break_even_scale, 4) if break_even_scale is not None else None
                ),
                "break_even_executions": (
                    round(break_even_executions, 2)
                    if break_even_executions is not None
                    else None
                ),
            }
        )
        if internal:
            totals["internal_cost"] += ai_cost
        else:
            totals["revenue"] += revenue
            totals["manual_cost"] += manual
            totals["ai_cost"] += ai_cost
            totals["executions"] += executions
            totals["covered_cost"] += covered_cost

    # Worst margin first; projects without a rate follow, by AI cost.
    def _sort_key(item: dict) -> tuple[int, float]:
        if item["internal"]:
            return (2, -float(item["ai_cost"] or 0))
        margin = item["margin"]
        if margin is None:
            return (1, -float(item["ai_cost"] or 0))
        return (0, float(margin))

    items.sort(key=_sort_key)

    margin_total = totals["revenue"] - totals["manual_cost"] - totals["ai_cost"]
    coverage = (
        min(1.0, totals["covered_cost"] / totals["ai_cost"])
        if totals["ai_cost"] > 0
        else 0.0
    )
    return {
        "items": items,
        "total": len(items),
        "series": [
            {
                "day": day.isoformat(),
                "revenue": money(series[day]["revenue"]),
                "manual_cost": money(series[day]["manual_cost"]),
                "ai_cost": money(series[day]["ai_cost"]),
                "internal_cost": money(series[day]["internal_cost"]),
                "margin": money(
                    series[day]["revenue"] - series[day]["manual_cost"] - series[day]["ai_cost"]
                ),
            }
            for day in window
        ],
        "totals": {
            "revenue": money(totals["revenue"]),
            "manual_cost": money(totals["manual_cost"]),
            "ai_cost": money(totals["ai_cost"]),
            "margin": money(margin_total),
            "margin_pct": (
                round(margin_total / totals["revenue"], 4)
                if totals["revenue"] > 0
                else None
            ),
            "executions": totals["executions"],
            "projects": sum(1 for i in items if not i["internal"]),
            "projects_rated": sum(1 for i in items if i["covered_days"]),
            "internal_projects": sum(1 for i in items if i["internal"]),
            "coverage_pct": round(coverage, 4),
            "covered_cost": money(totals["covered_cost"]),
            "internal_cost": money(totals["internal_cost"]),
            "break_even_scale": (
                round((totals["revenue"] - totals["manual_cost"]) / totals["ai_cost"], 4)
                if totals["ai_cost"] > 0
                else None
            ),
        },
        "window": {
            "start": window[0].isoformat() if window else None,
            "end": window[-1].isoformat() if window else None,
            "days": len(window),
        },
    }
