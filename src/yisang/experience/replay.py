from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import ExperienceEpisode, LessonCandidate, ReplayCaseResult, ReplayReport


@dataclass(frozen=True)
class ReplayPlanCase:
    test_id: str
    source_episode_id: str
    trigger_conditions: tuple[str, ...]
    expected_outcome: str
    expected_procedure_steps: tuple[str, ...]
    required_evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReplayPlan:
    candidate_id: str
    cases: tuple[ReplayPlanCase, ...]
    strategy: str = "source_episode_replay_v1"


class ReplayPlanError(ValueError):
    pass


class ReplayPlanBuilder:
    def build(
        self,
        candidate: LessonCandidate,
        episodes: tuple[ExperienceEpisode, ...] | list[ExperienceEpisode],
    ) -> ReplayPlan:
        by_id = {episode.episode_id: episode for episode in episodes}
        if len(by_id) != len(episodes):
            raise ReplayPlanError("duplicate episode ids are not allowed")
        missing = tuple(
            episode_id
            for episode_id in candidate.source_episode_ids
            if episode_id not in by_id
        )
        if missing:
            raise ReplayPlanError(f"missing source episodes: {', '.join(missing)}")
        if len(candidate.validation_tests) != len(candidate.source_episode_ids):
            raise ReplayPlanError(
                "validation test count must match source episode count"
            )

        cases: list[ReplayPlanCase] = []
        for test_id, episode_id in zip(
            candidate.validation_tests,
            candidate.source_episode_ids,
            strict=True,
        ):
            episode = by_id[episode_id]
            evidence_refs = tuple(
                evidence.evidence_ref
                for evidence in episode.evidence
                if evidence.is_promotable
            )
            if not evidence_refs:
                raise ReplayPlanError(
                    f"source episode lacks promotable evidence: {episode_id}"
                )
            cases.append(
                ReplayPlanCase(
                    test_id=test_id,
                    source_episode_id=episode_id,
                    trigger_conditions=episode.trigger_conditions,
                    expected_outcome=episode.outcome,
                    expected_procedure_steps=episode.procedure_steps,
                    required_evidence_refs=evidence_refs,
                )
            )
        return ReplayPlan(candidate_id=candidate.candidate_id, cases=tuple(cases))

    def report(
        self,
        plan: ReplayPlan,
        results: Mapping[str, bool],
        *,
        evidence_refs: Mapping[str, tuple[str, ...]] | None = None,
    ) -> ReplayReport:
        expected = tuple(case.test_id for case in plan.cases)
        missing = tuple(test_id for test_id in expected if test_id not in results)
        extra = tuple(sorted(set(results) - set(expected)))
        if missing:
            raise ReplayPlanError(f"missing replay results: {', '.join(missing)}")
        if extra:
            raise ReplayPlanError(f"unexpected replay results: {', '.join(extra)}")
        refs = evidence_refs or {}
        return ReplayReport(
            candidate_id=plan.candidate_id,
            results=tuple(
                ReplayCaseResult(
                    test_id=test_id,
                    passed=bool(results[test_id]),
                    evidence_refs=tuple(refs.get(test_id, ())),
                )
                for test_id in expected
            ),
        )
