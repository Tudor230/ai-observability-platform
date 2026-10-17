"""Call signatures for loop detection (ADR-0014).

A *call signature* is an opaque equality token for one LLM/TOOL call: the
input material (tool name + arguments, model + full input messages) is
canonicalized and hashed with HMAC-SHA256 under a per-process random salt.
Equal signatures mean "these two calls sent the same input", which is the
evidence loop detection counts.

Privacy (ADR-0003 amendment):

* the salt lives only in this process and is never exported;
* only the truncated digest rides the span stream as ``sdk.call.sig``;
* the digest is run-scoped — it cannot be correlated across processes or
  executions, so it cannot be linked back to prompt content even by the
  platform operator;
* when no usable input is present the call gets **no** signature (detection
  skips it rather than guessing).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Mapping, Optional

from aiobs_contracts import (
    INPUT_VALUE,
    LLM_INPUT_MESSAGES,
    LLM_MODEL_NAME,
    LLM_PROMPTS,
    LLM_PROVIDER,
    LLM_SYSTEM,
    TOOL_NAME,
    TOOL_PARAMETERS,
)

_PROCESS_SALT = secrets.token_bytes(32)
_SIG_LEN = 16

_MESSAGE_PREFIXES = (f"{LLM_INPUT_MESSAGES}.", f"{LLM_PROMPTS}.")


def _canonical(value: Any) -> str:
    """Stable JSON text for a parsed attribute value."""
    try:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _normalize_payload(raw: Any) -> Optional[str]:
    """Canonical form of a JSON-ish attribute value (or plain string)."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return _canonical(raw)
    text = str(raw)
    if not text:
        return None
    try:
        return _canonical(json.loads(text))
    except (TypeError, ValueError):
        return text


def _message_material(attributes: Mapping[str, Any]) -> Optional[str]:
    """Flattened ``llm.input_messages.*`` / ``llm.prompts.*`` as fallback input."""
    items = [
        (key, str(attributes[key]))
        for key in sorted(attributes)
        if key.startswith(_MESSAGE_PREFIXES)
    ]
    return _canonical(items) if items else None


def _tool_material(attributes: Mapping[str, Any]) -> Optional[str]:
    name = attributes.get(TOOL_NAME)
    if not isinstance(name, str) or not name:
        return None
    args = _normalize_payload(attributes.get(TOOL_PARAMETERS))
    if args is None:
        args = _normalize_payload(attributes.get(INPUT_VALUE))
    if args is None:
        # No argument material at all: an unidentifiable call; skip.
        return None
    return _canonical({"tool": name, "args": args})


def _llm_material(attributes: Mapping[str, Any]) -> Optional[str]:
    model = None
    for key in (LLM_MODEL_NAME, LLM_PROVIDER, LLM_SYSTEM):
        value = attributes.get(key)
        if isinstance(value, str) and value:
            model = value
            break
    payload = _normalize_payload(attributes.get(INPUT_VALUE))
    if payload is None:
        payload = _message_material(attributes)
    if payload is None:
        # Model identity alone cannot prove two calls sent the same input.
        return None
    return _canonical({"model": model or "", "input": payload})


def call_signature(kind: str, attributes: Mapping[str, Any]) -> Optional[str]:
    """Salted signature for an LLM/TOOL call, or ``None`` without usable input."""
    if kind == "TOOL":
        material = _tool_material(attributes)
    elif kind == "LLM":
        material = _llm_material(attributes)
    else:
        return None
    if material is None:
        return None
    digest = hmac.new(_PROCESS_SALT, material.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:_SIG_LEN]
