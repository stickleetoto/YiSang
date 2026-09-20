from __future__ import annotations

from datetime import datetime
from typing import Any

from yisang.memory.models import MemoryRecord


_BIO_KIND_MAP = {
    "profile": "semantic",
    "project": "semantic",
    "decision": "semantic",
    "summary": "semantic",
    "failure": "episodic",
    "success": "episodic",
    "prompt": "episodic",
    "handoff": "episodic",
    "log": "episodic",
}

_ACTIVE_STATUSES = frozenset({"current", "active"})
_SUPERSEDED_STATUSES = frozenset({"superseded"})


def bio_memory_to_yisang(
    payload: dict[str, Any],
    *,
    score: float | None = None,
) -> MemoryRecord:
    if not isinstance(payload, dict):
        raise ValueError("BIO memory payload must be an object")
    raw_id = payload.get("id")
    if raw_id is None:
        raise ValueError("BIO memory payload requires id")
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("BIO memory payload requires content")

    status = str(payload.get("status") or "active").strip().casefold()
    if status in _ACTIVE_STATUSES:
        validation_state = "committed"
        invalidated = False
    elif status in _SUPERSEDED_STATUSES:
        validation_state = "superseded"
        invalidated = True
    else:
        validation_state = "invalidated"
        invalidated = True

    memory_type = str(
        payload.get("memory_type") or payload.get("type") or "project"
    ).strip().casefold()
    try:
        importance_rank = max(1, min(5, int(payload.get("importance", 3))))
    except (TypeError, ValueError):
        importance_rank = 3
    confidence = _bounded_float(payload.get("confidence"), default=1.0)
    created_at = _timestamp(payload.get("created_at"))
    updated_at = _timestamp(payload.get("updated_at")) or created_at
    valid_from = _timestamp(payload.get("valid_from")) or created_at
    valid_until = _optional_timestamp(payload.get("valid_until"))
    source = str(payload.get("source") or "bio").strip() or "bio"
    memory_id = f"bio:{raw_id}"

    return MemoryRecord(
        memory_id=memory_id,
        kind=_BIO_KIND_MAP.get(memory_type, "semantic"),
        content=content,
        source=f"bio:{source}",
        confidence=confidence,
        metadata={
            "provider": "bio",
            "bio_memory_id": raw_id,
            "bio_title": payload.get("title"),
            "bio_memory_type": memory_type,
            "bio_status": status,
            "bio_project": payload.get("project"),
            "bio_namespace": payload.get("namespace"),
            "bio_continuity_key": payload.get("continuity_key"),
            "bio_quality_score": payload.get("quality_score"),
            "bio_stability_score": payload.get("stability_score"),
            "bio_decay_score": payload.get("decay_score"),
            "bio_score": score,
        },
        source_id=str(raw_id),
        source_type="bio_memory",
        evidence_refs=(f"bio-memory:{raw_id}",),
        trust_class="unknown",
        importance=(importance_rank - 1) / 4.0,
        writer="bio",
        validation_state=validation_state,
        created_at=created_at,
        updated_at=updated_at,
        valid_from=valid_from,
        valid_until=valid_until,
        superseded_by_id=(
            f"bio:{payload['superseded_by']}"
            if payload.get("superseded_by") is not None
            else None
        ),
        last_used_at=_optional_timestamp(payload.get("last_used_at")),
        success_count=_nonnegative_int(payload.get("success_count")),
        failure_count=_nonnegative_int(payload.get("failure_count")),
        invalidated=invalidated,
    )


def map_search_payload(payload: dict[str, Any]) -> list[MemoryRecord]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("BIO search results must be an array")
    mapped: list[MemoryRecord] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        memory = item.get("memory")
        if not isinstance(memory, dict):
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        mapped.append(bio_memory_to_yisang(memory, score=score))
    return mapped


def map_context_memories(payload: dict[str, Any]) -> tuple[MemoryRecord, ...]:
    memories = payload.get("memories", [])
    if not isinstance(memories, list):
        raise ValueError("BIO context memories must be an array")
    result: list[MemoryRecord] = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        result.append(bio_memory_to_yisang(item, score=score))
    return tuple(result)


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _timestamp(value: Any) -> float:
    return _optional_timestamp(value) or 0.0


def _optional_timestamp(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
