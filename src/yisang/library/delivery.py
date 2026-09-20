from __future__ import annotations

import hashlib
import json
from typing import Any

from yisang.memory.lexical import lexical_terms

from .retrieval import LibrarySearchResult

_IMPLEMENTATION_TERMS = frozenset(
    {
        "implement",
        "implementation",
        "code",
        "coding",
        "function",
        "class",
        "configure",
        "구현",
        "코드",
        "설정",
    }
)
_PERFORMANCE_TERMS = frozenset(
    {
        "performance",
        "complexity",
        "latency",
        "throughput",
        "memory",
        "speed",
        "optimize",
        "optimization",
        "성능",
        "복잡도",
        "메모리",
        "속도",
        "지연",
        "최적화",
    }
)
_TRADEOFF_TERMS = frozenset(
    {
        "compare",
        "comparison",
        "tradeoff",
        "tradeoffs",
        "risk",
        "pitfall",
        "failure",
        "avoid",
        "caution",
        "비교",
        "장단점",
        "위험",
        "실패",
        "주의",
    }
)


def stable_knowledge_ref(book_id: str, entry_id: str) -> str:
    digest = hashlib.sha256(
        f"{book_id}\0{entry_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"k_{digest}"


def build_library_delivery(
    results: tuple[LibrarySearchResult, ...],
    *,
    request: str,
    max_chars: int = 4_000,
) -> tuple[dict[str, Any], ...]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not results:
        return ()

    request_terms = lexical_terms(request)
    implementation_intent = bool(request_terms & _IMPLEMENTATION_TERMS)
    performance_intent = bool(request_terms & _PERFORMANCE_TERMS)
    tradeoff_intent = bool(request_terms & _TRADEOFF_TERMS)

    primary_index = next(
        (
            index
            for index, result in enumerate(results)
            if result.fit != "avoid"
        ),
        0,
    )

    payloads: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        if index == primary_index:
            role = "primary"
        elif result.fit == "avoid":
            role = "guardrail"
        else:
            role = "complement"

        entry = result.entry
        item: dict[str, Any] = {
            "knowledge_ref": stable_knowledge_ref(
                result.book.book_id,
                entry.entry_id,
            ),
            "role": role,
            "book_id": result.book.book_id,
            "book": result.book.title,
            "topic": entry.title,
            "fit": result.fit,
            "knowledge": entry.summary,
            "trust_class": entry.trust_class,
            "validation_state": entry.validation_state,
            "source_refs": list(entry.source_refs),
        }

        if entry.use_when:
            item["use_when"] = list(entry.use_when[:3])
        if entry.structure:
            item["structure"] = list(entry.structure[:4])

        # Safety boundaries survive ordinary request-aware pruning.
        if entry.avoid_when:
            item["avoid_when"] = list(entry.avoid_when[:3])

        if implementation_intent and entry.implementation_hint:
            item["implementation_hint"] = entry.implementation_hint
        if performance_intent and entry.complexity:
            item["complexity"] = dict(entry.complexity)
        if tradeoff_intent:
            if entry.tradeoffs:
                item["tradeoffs"] = list(entry.tradeoffs[:3])
            if entry.pitfalls:
                item["pitfalls"] = list(entry.pitfalls[:3])

        payloads.append(item)

    return tuple(_fit_budget(payloads, max_chars=max_chars))


def delivery_chars(payload: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _fit_budget(
    payloads: list[dict[str, Any]],
    *,
    max_chars: int,
) -> list[dict[str, Any]]:
    result = [dict(item) for item in payloads]

    optional_fields = (
        "pitfalls",
        "tradeoffs",
        "complexity",
        "implementation_hint",
        "structure",
        "use_when",
    )

    while result and delivery_chars(result) > max_chars:
        removed = False
        for field in optional_fields:
            for item in reversed(result):
                if field in item:
                    item.pop(field)
                    removed = True
                    break
            if removed:
                break
        if removed:
            continue

        # Drop positive complements before a guardrail. A returned warning is
        # more important than a second similar recommendation.
        complement_index = next(
            (
                index
                for index in range(len(result) - 1, -1, -1)
                if result[index].get("role") == "complement"
            ),
            None,
        )
        if complement_index is not None:
            result.pop(complement_index)
            continue

        if len(result) > 1:
            removable = next(
                (
                    index
                    for index in range(len(result) - 1, -1, -1)
                    if result[index].get("role") != "primary"
                    and result[index].get("role") != "guardrail"
                ),
                None,
            )
            if removable is not None:
                result.pop(removable)
                continue

        # Preserve the primary and guardrail boundary as long as possible.
        longest_index = max(
            range(len(result)),
            key=lambda index: len(str(result[index].get("knowledge", ""))),
        )
        knowledge = str(result[longest_index].get("knowledge", ""))
        if len(knowledge) > 80:
            overflow = delivery_chars(result) - max_chars
            new_size = max(80, len(knowledge) - max(1, overflow))
            if new_size < len(knowledge):
                result[longest_index]["knowledge"] = (
                    knowledge[: max(0, new_size - 1)].rstrip() + "…"
                )
                continue
        break

    return result
