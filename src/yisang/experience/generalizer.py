from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Iterable

from .models import ExperienceEpisode, ExperienceEvidence, LessonCandidate


class ExperienceGeneralizationError(ValueError):
    pass


class ExperienceGeneralizer:
    """Conservative deterministic generalizer for repeated runtime episodes."""

    def __init__(self, *, min_repeats: int = 3) -> None:
        if min_repeats < 2:
            raise ValueError("min_repeats must be >= 2")
        self.min_repeats = min_repeats

    def generalize(
        self,
        episodes: Iterable[ExperienceEpisode],
        *,
        kind: str = "procedure",
        target: str = "ego_procedure",
        title: str | None = None,
        scope: str = "general",
        risk_class: str = "normal",
        version: str = "1",
    ) -> LessonCandidate:
        items = tuple(episodes)
        if len(items) < self.min_repeats:
            raise ExperienceGeneralizationError(
                f"at least {self.min_repeats} repeated episodes are required"
            )
        ids = tuple(item.episode_id for item in items)
        if len(set(ids)) != len(ids):
            raise ExperienceGeneralizationError("duplicate episode ids are not allowed")

        expected_outcome = "failure" if kind == "warning" else "success"
        if any(item.outcome != expected_outcome for item in items):
            raise ExperienceGeneralizationError(
                f"{kind} generalization requires only {expected_outcome} episodes"
            )

        promotable_by_episode = tuple(
            tuple(e for e in item.evidence if e.is_promotable) for item in items
        )
        if any(not evidence for evidence in promotable_by_episode):
            raise ExperienceGeneralizationError(
                "every source episode must carry promotable evidence"
            )

        shared_triggers = _shared_values(
            tuple(item.trigger_conditions for item in items)
        )
        if not shared_triggers:
            raise ExperienceGeneralizationError(
                "source episodes must share at least one trigger condition"
            )

        if kind == "procedure":
            first_steps = items[0].procedure_steps
            if not first_steps:
                raise ExperienceGeneralizationError(
                    "procedure generalization requires procedure steps"
                )
            if any(item.procedure_steps != first_steps for item in items[1:]):
                raise ExperienceGeneralizationError(
                    "procedure steps differ across source episodes"
                )
            proposed_content = _procedure_content(shared_triggers, first_steps)
        elif kind == "knowledge":
            first_summary = _normalize_text(items[0].summary)
            if any(
                _normalize_text(item.summary) != first_summary for item in items[1:]
            ):
                raise ExperienceGeneralizationError(
                    "knowledge summaries differ across source episodes"
                )
            proposed_content = items[0].summary.strip()
        elif kind == "warning":
            proposed_content = (
                "Repeated failure observed when "
                + "; ".join(shared_triggers)
                + ". Treat this trigger as a durable warning until a validated "
                + "workaround supersedes it."
            )
        else:
            raise ExperienceGeneralizationError(
                f"unsupported candidate kind: {kind}"
            )

        source_evidence = _dedupe_evidence(
            evidence
            for group in promotable_by_episode
            for evidence in group
        )
        candidate_id = _candidate_id(
            kind=kind,
            target=target,
            episode_ids=ids,
            triggers=shared_triggers,
            proposed_content=proposed_content,
        )
        validation_tests = tuple(
            f"replay:{candidate_id}:{index + 1}"
            for index in range(len(items))
        )
        return LessonCandidate(
            candidate_id=candidate_id,
            kind=kind,
            target=target,
            title=title or _default_title(kind, shared_triggers),
            proposed_content=proposed_content,
            source_episode_ids=ids,
            source_evidence=source_evidence,
            trigger_conditions=shared_triggers,
            validation_tests=validation_tests,
            success_count=sum(item.outcome == "success" for item in items),
            failure_count=sum(item.outcome == "failure" for item in items),
            scope=scope,
            risk_class=risk_class,
            version=version,
            metadata={
                "generalizer": "deterministic-v1",
                "repeat_count": len(items),
                "source_outcome": expected_outcome,
            },
        )


def _shared_values(groups: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    if not groups:
        return ()
    normalized_sets = [
        {_normalize_text(value) for value in group if _normalize_text(value)}
        for group in groups
    ]
    shared = set.intersection(*normalized_sets)
    result: list[str] = []
    seen: set[str] = set()
    for value in groups[0]:
        normalized = _normalize_text(value)
        if normalized in shared and normalized not in seen:
            result.append(value.strip())
            seen.add(normalized)
    return tuple(result)


def _dedupe_evidence(
    evidence: Iterable[ExperienceEvidence],
) -> tuple[ExperienceEvidence, ...]:
    result: list[ExperienceEvidence] = []
    seen: set[str] = set()
    for item in evidence:
        if item.evidence_ref in seen:
            continue
        seen.add(item.evidence_ref)
        result.append(item)
    return tuple(result)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _procedure_content(
    triggers: tuple[str, ...],
    steps: tuple[str, ...],
) -> str:
    lines = [f"When {'; '.join(triggers)}:"]
    lines.extend(f"{index}. {step}" for index, step in enumerate(steps, 1))
    return "\n".join(lines)


def _default_title(kind: str, triggers: tuple[str, ...]) -> str:
    label = {
        "procedure": "Validated procedure",
        "knowledge": "Validated knowledge",
        "warning": "Repeated failure warning",
    }[kind]
    return f"{label}: {triggers[0]}"


def _candidate_id(
    *,
    kind: str,
    target: str,
    episode_ids: tuple[str, ...],
    triggers: tuple[str, ...],
    proposed_content: str,
) -> str:
    payload = json.dumps(
        {
            "kind": kind,
            "target": target,
            "episode_ids": sorted(episode_ids),
            "triggers": list(triggers),
            "content": proposed_content,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"candidate-{digest}"
