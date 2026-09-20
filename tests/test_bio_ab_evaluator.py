from yisang.evaluation.bio import (
    MemoryProviderABEvaluator,
    MemoryValidationScenario,
)
from yisang.memory.models import MemoryProposal
from yisang.memory.provider import (
    MemoryProvider,
    ProviderContext,
    ProviderCurrentState,
    ProviderWriteResult,
)


class FixedProvider(MemoryProvider):
    def __init__(self, provider_id, text):
        self.provider_id = provider_id
        self.text = text

    def recall(self, query, *, limit=8):
        return []

    def remember(self, proposal):
        return ProviderWriteResult(self.provider_id, "pending")

    def get_current_state(self, topic_key):
        return ProviderCurrentState(
            self.provider_id,
            topic_key,
            f"{self.provider_id}:current",
            1.0,
        )

    def get_context(self, query, *, limit=8, char_budget=2400):
        return ProviderContext(
            self.provider_id,
            self.text[:char_budget],
            (),
        )


def test_ab_evaluator_reports_without_ranking():
    scenarios = (
        MemoryValidationScenario(
            "resume",
            "resume",
            "continue",
            required_substrings=("next task",),
        ),
    )
    report = MemoryProviderABEvaluator().run(
        (
            FixedProvider("a", "next task runtime"),
            FixedProvider("b", "next task runtime"),
        ),
        scenarios,
    )
    assert [summary.pass_rate for summary in report.summaries] == [1.0, 1.0]
    assert tuple(summary.provider_id for summary in report.summaries) == ("a", "b")


def test_ab_evaluator_counts_stale_or_forbidden_hits():
    scenario = MemoryValidationScenario(
        "stale",
        "stale",
        "storage",
        required_substrings=("SQLite",),
        forbidden_substrings=("JSON",),
    )
    report = MemoryProviderABEvaluator().run(
        (FixedProvider("a", "SQLite JSON"),),
        (scenario,),
    )
    assert report.results[0].passed is False
    assert report.results[0].forbidden_hits == 1
    assert report.summaries[0].stale_or_forbidden_hits == 1
