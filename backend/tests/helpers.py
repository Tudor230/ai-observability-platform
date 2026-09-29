"""Test helpers: build OTLP protobuf payloads and seed a test backend."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status

from aiobs_backend.models import (
    Department,
    Membership,
    Project,
    ProjectKey,
    Team,
    User,
)
from aiobs_backend.security import (
    generate_api_key,
    hash_api_key,
    hash_password,
    key_hint,
)

STATUS_OK = Status.STATUS_CODE_OK
STATUS_ERROR = Status.STATUS_CODE_ERROR


def kv(key: str, value) -> KeyValue:
    av = AnyValue()
    if isinstance(value, bool):
        av.bool_value = value
    elif isinstance(value, int):
        av.int_value = value
    elif isinstance(value, float):
        av.double_value = value
    else:
        av.string_value = str(value)
    return KeyValue(key=key, value=av)


def _dt_nanos(dt: datetime | None) -> int:
    if dt is None:
        return 0
    return int(dt.timestamp() * 1_000_000_000)


def build_span(
    *,
    name: str,
    oi_kind: str,
    span_id: int,
    trace_id: int,
    parent_span_id: int | None = None,
    status: int = STATUS_OK,
    status_message: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    attrs: dict | None = None,
) -> Span:
    now = datetime.now(timezone.utc)
    start = start or now
    end = end or now
    span = Span(
        trace_id=trace_id.to_bytes(16, "big"),
        span_id=span_id.to_bytes(8, "big"),
        parent_span_id=(parent_span_id or 0).to_bytes(8, "big") if parent_span_id else b"",
        name=name,
        start_time_unix_nano=_dt_nanos(start),
        end_time_unix_nano=_dt_nanos(end),
        kind=Span.SPAN_KIND_INTERNAL,
    )
    base = {"openinference.span.kind": oi_kind}
    if attrs:
        base.update(attrs)
    span.attributes.extend([kv(k, v) for k, v in base.items()])
    span.status.CopyFrom(Status(code=status, message=status_message or ""))
    return span


def build_request(spans: list[Span], resource_attrs: dict | None = None) -> bytes:
    rs = ResourceSpans()
    if resource_attrs:
        rs.resource.CopyFrom(
            Resource(attributes=[kv(k, v) for k, v in resource_attrs.items()])
        )
    ss = ScopeSpans()
    ss.spans.extend(spans)
    rs.scope_spans.append(ss)
    request = ExportTraceServiceRequest(resource_spans=[rs])
    return request.SerializeToString()


def seed_department(session, name: str = "Test Department") -> Department:
    existing = session.query(Department).filter_by(name=name).one_or_none()
    if existing is not None:
        return existing
    department = Department(name=name)
    session.add(department)
    session.flush()
    return department


def seed_team(
    session, *, name: str = "Test", department: Department | None = None
) -> Team:
    department = department or seed_department(session)
    team = Team(name=name, department_id=department.id)
    session.add(team)
    session.flush()
    return team


def seed_project(
    session,
    *,
    project_id="proj-1",
    api_key="test-key",
    name="Test Project",
    team: Team | None = None,
) -> Project:
    team = team or seed_team(session)
    project = Project(team_id=team.id, project_id=project_id, name=name)
    session.add(project)
    session.flush()
    session.add(
        ProjectKey(
            project_id=project.id,
            key_hash=hash_api_key(api_key),
            key_hint=key_hint(api_key),
            label="test",
        )
    )
    session.flush()
    return project


def seed_user(
    session,
    email: str,
    *,
    password: str = "test-pass-123",
    role: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> tuple[User, str]:
    """Create a user with an API key and (optionally) one approved membership."""
    key = generate_api_key()
    user = User(
        email=email,
        password_hash=hash_password(password),
        api_key_hash=hash_api_key(key),
    )
    session.add(user)
    session.flush()
    if role:
        session.add(
            Membership(
                user_id=user.id,
                role=role,
                scope_type=scope_type or "global",
                scope_id=scope_id,
                status="approved",
            )
        )
        session.flush()
    return user, key


def build_app(session_factory) -> FastAPI:
    from aiobs_backend.api.deps import get_db
    from aiobs_backend.main import create_app

    app = create_app()

    def _get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    return app