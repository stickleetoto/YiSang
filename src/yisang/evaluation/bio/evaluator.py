from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from yisang.memory.provider import MemoryProvider

from .scenarios import MemoryValidationScenario


@dataclass(frozen=True)
class ScenarioResult:
    provider_id: str
    scenario_id: str
    kind: str
    passed: bool
    required_hits: int
    required_total: int
    forbidden_hits: int
    current_state_resolved: bool
    memory_count: int
    context_chars: int


@dataclass(frozen=True)
class ProviderSummary:
    provider_id: str
    scenario_count: int
    passed_count: int
    pass_rate: float
    stale_or_forbidden_hits: int
    total_context_chars: int


@dataclass(frozen=True)
class MemoryProviderABReport:
    results: tuple[ScenarioResult, ...]
    summaries: tuple[ProviderSummary, ...]


class MemoryProviderABEvaluator:
    """Neutral A/B harness. It reports provider measurements without ranking."""

    def run(
        self,
        providers: Iterable[MemoryProvider],
        scenarios: Iterable[MemoryValidationScenario],
        *,
        limit: int = 8,
        char_budget: int = 2400,
    ) -> MemoryProviderABReport:
        provider_items = tuple(providers)
        scenario_items = tuple(scenarios)
        if len({provider.provider_id for provider in provider_items}) != len(
            provider_items
        ):
            raise ValueError("provider ids must be unique for A/B evaluation")

        results: list[ScenarioResult] = []
        for provider in provider_items:
            for scenario in scenario_items:
                context = provider.get_context(
                    scenario.query,
                    limit=limit,
                    char_budget=char_budget,
                )
                corpus = "\n".join(
                    [context.text, *(memory.content for memory in context.memories)]
                ).casefold()
                required_hits = sum(
                    item.casefold() in corpus
                    for item in scenario.required_substrings
                )
                forbidden_hits = sum(
                    item.casefold() in corpus
                    for item in scenario.forbidden_substrings
                )
                current_state_resolved = True
                if scenario.topic_key is not None:
                    state = provider.get_current_state(scenario.topic_key)
                    current_state_resolved = state.current_memory_id is not None
                passed = (
                    required_hits == len(scenario.required_substrings)
                    and forbidden_hits == 0
                    and current_state_resolved
                )
                results.append(
                    ScenarioResult(
                        provider_id=provider.provider_id,
                        scenario_id=scenario.scenario_id,
                        kind=scenario.kind,
                        passed=passed,
                        required_hits=required_hits,
                        required_total=len(scenario.required_substrings),
                        forbidden_hits=forbidden_hits,
                        current_state_resolved=current_state_resolved,
                        memory_count=len(context.memories),
                        context_chars=len(context.text),
                    )
                )

        summaries: list[ProviderSummary] = []
        for provider in provider_items:
            selected = [
                result
                for result in results
                if result.provider_id == provider.provider_id
            ]
            passed_count = sum(result.passed for result in selected)
            summaries.append(
                ProviderSummary(
                    provider_id=provider.provider_id,
                    scenario_count=len(selected),
                    passed_count=passed_count,
                    pass_rate=(
                        passed_count / len(selected) if selected else 0.0
                    ),
                    stale_or_forbidden_hits=sum(
                        result.forbidden_hits for result in selected
                    ),
                    total_context_chars=sum(
                        result.context_chars for result in selected
                    ),
                )
            )

        return MemoryProviderABReport(
            results=tuple(results),
            summaries=tuple(summaries),
        )
