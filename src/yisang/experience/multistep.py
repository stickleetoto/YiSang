from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable

from .executor import DeterministicReplayExecutor, ReplayExecutionSpec
from .models import ExperienceEpisode, ReplayCaseResult, ReplayReport
from .replay import ReplayPlan
from .trace_port import ActionTracePort


class OrderedReplayError(ValueError):
    pass


@dataclass(frozen=True)
class OrderedReplaySequence:
    test_id: str
    steps: tuple[ReplayExecutionSpec, ...]

    def __post_init__(self) -> None:
        if not self.test_id.strip():
            raise ValueError("test_id must be non-empty")
        if len(self.steps) < 2:
            raise ValueError("ordered replay requires at least two steps")
        step_ids = tuple(step.test_id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("ordered replay step ids must be unique")


class OrderedReplayManifestCompiler:
    """Compile an exact ordered ActionTrace sequence for each ReplayPlan case.

    This compiler is deliberately strict: every historical action trace for the
    source request must match the tool sequence encoded in procedure_steps, and
    every matched trace must carry a verified replay template.
    """

    def compile(
        self,
        plan: ReplayPlan,
        episodes: Iterable[ExperienceEpisode],
        traces: ActionTracePort,
    ) -> tuple[OrderedReplaySequence, ...]:
        episode_items = tuple(episodes)
        episode_map = {item.episode_id: item for item in episode_items}
        if len(episode_map) != len(episode_items):
            raise OrderedReplayError("duplicate source episode ids")

        sequences: list[OrderedReplaySequence] = []
        for case in plan.cases:
            episode = episode_map.get(case.source_episode_id)
            if episode is None:
                raise OrderedReplayError(
                    f"missing source episode: {case.source_episode_id}"
                )
            if not episode.request_id:
                raise OrderedReplayError(
                    f"source episode lacks request_id: {episode.episode_id}"
                )

            expected_tools = tuple(
                step.removeprefix("tool:")
                for step in case.expected_procedure_steps
                if step.startswith("tool:")
            )
            if len(expected_tools) < 2:
                raise OrderedReplayError(
                    f"ordered replay requires at least two tool steps: {case.test_id}"
                )

            history = traces.for_request(episode.request_id)
            actual_tools = tuple(trace.tool_id for trace in history)
            if actual_tools != expected_tools:
                raise OrderedReplayError(
                    f"trace tool order mismatch for {case.test_id}: "
                    f"expected={expected_tools}, actual={actual_tools}"
                )

            specs: list[ReplayExecutionSpec] = []
            for index, trace in enumerate(history, 1):
                if not trace.replayable or trace.replay_template is None:
                    reason = (
                        trace.manifest_rejection_reason
                        or "missing verified replay template"
                    )
                    raise OrderedReplayError(
                        f"step {index} is not replayable for {case.test_id}: "
                        f"{reason}"
                    )
                specs.append(
                    trace.replay_template.to_spec(
                        f"{case.test_id}:step:{index}:{trace.tool_id}"
                    )
                )

            sequences.append(
                OrderedReplaySequence(
                    test_id=case.test_id,
                    steps=tuple(specs),
                )
            )
        return tuple(sequences)


class DeterministicOrderedReplayExecutor:
    """Run every step of a replay case in one isolated shared workspace."""

    def __init__(
        self,
        *,
        allowed_executables: Iterable[str],
        workspace_root: str | Path | None = None,
        max_timeout_seconds: float = 60.0,
    ) -> None:
        self._executor = DeterministicReplayExecutor(
            allowed_executables=allowed_executables,
            workspace_root=workspace_root,
            max_timeout_seconds=max_timeout_seconds,
        )
        self.workspace_root = (
            Path(workspace_root) if workspace_root is not None else None
        )

    def execute(
        self,
        plan: ReplayPlan,
        sequences: Iterable[OrderedReplaySequence],
    ) -> ReplayReport:
        by_id: dict[str, OrderedReplaySequence] = {}
        for sequence in sequences:
            if sequence.test_id in by_id:
                raise OrderedReplayError(
                    f"duplicate ordered replay sequence: {sequence.test_id}"
                )
            by_id[sequence.test_id] = sequence

        expected = tuple(case.test_id for case in plan.cases)
        missing = tuple(test_id for test_id in expected if test_id not in by_id)
        extra = tuple(sorted(set(by_id) - set(expected)))
        if missing:
            raise OrderedReplayError(
                "missing ordered replay sequences: " + ", ".join(missing)
            )
        if extra:
            raise OrderedReplayError(
                "unexpected ordered replay sequences: " + ", ".join(extra)
            )

        if self.workspace_root is not None:
            self.workspace_root.mkdir(parents=True, exist_ok=True)

        results = tuple(
            self._execute_sequence(by_id[test_id])
            for test_id in expected
        )
        return ReplayReport(candidate_id=plan.candidate_id, results=results)

    def _execute_sequence(
        self,
        sequence: OrderedReplaySequence,
    ) -> ReplayCaseResult:
        with TemporaryDirectory(
            prefix="yisang-ordered-replay-",
            dir=(
                str(self.workspace_root)
                if self.workspace_root is not None
                else None
            ),
        ) as temp_dir:
            workspace = Path(temp_dir)
            evidence_refs: list[str] = []
            executed_steps = 0

            for index, step in enumerate(sequence.steps, 1):
                result = self._executor._execute_case_in_workspace(
                    step.test_id,
                    step,
                    workspace,
                )
                executed_steps += 1
                evidence_refs.extend(result.evidence_refs)
                if not result.passed:
                    return ReplayCaseResult(
                        test_id=sequence.test_id,
                        passed=False,
                        evidence_refs=tuple(evidence_refs),
                        detail=(
                            f"ordered replay failed at step {index}/"
                            f"{len(sequence.steps)} ({step.test_id}): "
                            f"{result.detail}; executed_steps={executed_steps}"
                        ),
                    )

            return ReplayCaseResult(
                test_id=sequence.test_id,
                passed=True,
                evidence_refs=tuple(evidence_refs),
                detail=(
                    f"ordered replay passed; executed_steps={executed_steps}"
                ),
            )
