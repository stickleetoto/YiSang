import json

from yisang.context.compiler import ContextCompiler
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.eval.continuity import (
    ContinuityProbe,
    build_continuity_report,
    evaluate_v05_closeout,
    load_continuity_report,
    run_continuity_case,
    write_continuity_report,
    _percentile,
)
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier


def _runtime(*, active_engine, populated):
    memory = InMemoryMemoryPort()
    egos = EgoRegistry()

    if populated:
        memory.commit(
            MemoryProposal(
                content="continuity probe remembers alpha",
                source_engine="seed",
                confidence=0.95,
                evidence=["continuity:seed"],
                trust_class="verified",
                writer="governor",
            )
        )
        egos.register(
            EgoManifest(
                ego_id="ego.debug",
                name="Debug",
                provides=("debug",),
                keywords=("debug", "continuity"),
            )
        )
        state = AgentState(
            active_engine=active_engine,
            active_project="YiSang",
            current_goal="prove engine independence",
            tags={"phase": "v0.5"},
        )
    else:
        state = AgentState(active_engine=active_engine)

    engines = EngineRouter()
    engines.register(EchoEngine("engine-a", "A"))
    engines.register(EchoEngine("engine-b", "B"))
    engines.register(EchoEngine("engine-c", "C"))

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=state,
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )


def test_continuity_case_restores_and_probes_replacement_engine():
    source = _runtime(active_engine="engine-a", populated=True)
    memory_id = source.memory.all()[0].memory_id
    target = _runtime(active_engine="engine-a", populated=False)

    result = run_continuity_case(
        case_id="a-to-b",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
        probe=ContinuityProbe(
            request_text="continuity debug alpha",
            expected_memory_ids=(memory_id,),
            expected_ego_ids=("ego.debug",),
        ),
    )

    assert result.passed is True
    assert result.source_engine == "engine-a"
    assert result.target_engine == "engine-b"
    assert result.source_engine_used is True
    assert result.target_engine_used is True
    assert result.source_expected_memory_retrieved is True
    assert result.source_expected_ego_selected is True
    assert result.continuity_fingerprint_preserved is True
    assert result.expected_memory_retrieved is True
    assert result.expected_ego_selected is True
    assert result.restore_latency_ms >= 0
    assert result.probe_latency_ms >= 0


def test_continuity_report_can_compare_multiple_replacement_engines(tmp_path):
    source = _runtime(active_engine="engine-a", populated=True)
    memory_id = source.memory.all()[0].memory_id
    probe = ContinuityProbe(
        request_text="continuity debug alpha",
        expected_memory_ids=(memory_id,),
        expected_ego_ids=("ego.debug",),
    )

    results = []
    for engine_id in ("engine-b", "engine-c"):
        target = _runtime(active_engine="engine-a", populated=False)
        results.append(
            run_continuity_case(
                case_id=f"a-to-{engine_id}",
                source_runtime=source,
                target_runtime=target,
                target_engine=engine_id,
                memory_factory=InMemoryMemoryPort,
                policy_version="policy-v1",
                runtime_version="0.5-prep",
                probe=probe,
            )
        )

    report = build_continuity_report(results)
    path = write_continuity_report(
        report,
        tmp_path / "continuity-report.json",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert report.all_passed is True
    assert report.pass_rate == 1.0
    assert payload["case_count"] == 2
    assert payload["all_passed"] is True
    assert payload["summary"]["mean_restore_latency_ms"] >= 0
    assert payload["summary"]["p95_probe_latency_ms"] >= 0
    assert {case["target_engine"] for case in payload["cases"]} == {
        "engine-b",
        "engine-c",
    }


def test_continuity_case_fails_when_probe_expectation_is_missing():
    source = _runtime(active_engine="engine-a", populated=True)
    target = _runtime(active_engine="engine-a", populated=False)

    result = run_continuity_case(
        case_id="missing-expectation",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
        probe=ContinuityProbe(
            request_text="continuity debug alpha",
            expected_memory_ids=("mem-does-not-exist",),
        ),
    )

    assert result.passed is False
    assert result.expected_memory_retrieved is False
    assert result.continuity_fingerprint_preserved is True


def test_v05_closeout_requires_distinct_real_engine_family_evidence():
    source = _runtime(active_engine="engine-a", populated=True)
    memory_id = source.memory.all()[0].memory_id
    target = _runtime(active_engine="engine-a", populated=False)
    result = run_continuity_case(
        case_id="closeout",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
        probe=ContinuityProbe(
            request_text="continuity debug alpha",
            expected_memory_ids=(memory_id,),
            expected_ego_ids=("ego.debug",),
        ),
    )

    report = build_continuity_report(
        [result, result, result],
        metadata={
            "source_model": "model-a",
            "target_model": "model-b",
            "source_family": "llama",
            "target_family": "qwen",
        },
    )
    check = evaluate_v05_closeout(report)

    assert check.ready is True
    assert check.errors == ()


def test_v05_closeout_rejects_same_family_or_missing_repeats():
    source = _runtime(active_engine="engine-a", populated=True)
    memory_id = source.memory.all()[0].memory_id
    target = _runtime(active_engine="engine-a", populated=False)
    result = run_continuity_case(
        case_id="closeout-short",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
        probe=ContinuityProbe(
            request_text="continuity debug alpha",
            expected_memory_ids=(memory_id,),
            expected_ego_ids=("ego.debug",),
        ),
    )

    report = build_continuity_report(
        [result],
        metadata={
            "source_model": "model-a",
            "target_model": "model-b",
            "source_family": "llama",
            "target_family": "llama",
        },
    )
    check = evaluate_v05_closeout(report)

    assert check.ready is False
    assert any("at least 3" in error for error in check.errors)
    assert any("families must differ" in error for error in check.errors)


def test_saved_continuity_report_round_trip_preserves_closeout_metadata(tmp_path):
    source = _runtime(active_engine="engine-a", populated=True)
    memory_id = source.memory.all()[0].memory_id
    target = _runtime(active_engine="engine-a", populated=False)
    result = run_continuity_case(
        case_id="saved-report",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
        probe=ContinuityProbe(
            request_text="continuity debug alpha",
            expected_memory_ids=(memory_id,),
            expected_ego_ids=("ego.debug",),
        ),
    )
    report = build_continuity_report(
        [result, result, result],
        metadata={
            "source_model": "llama-model",
            "target_model": "qwen-model",
            "source_family": "llama",
            "target_family": "qwen",
            "repeats": 3,
        },
    )
    path = write_continuity_report(
        report,
        tmp_path / "continuity-report.json",
    )

    loaded = load_continuity_report(path)
    check = evaluate_v05_closeout(loaded)

    assert loaded.metadata["source_family"] == "llama"
    assert loaded.metadata["target_family"] == "qwen"
    assert len(loaded.cases) == 3
    assert check.ready is True


def test_saved_continuity_report_rejects_missing_case_field(tmp_path):
    path = tmp_path / "bad-report.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata": {},
                "cases": [{"case_id": "broken"}],
            }
        ),
        encoding="utf-8",
    )

    import pytest

    with pytest.raises(ValueError, match="missing field"):
        load_continuity_report(path)



def test_continuity_percentile_uses_nearest_rank_for_small_samples():
    assert _percentile([1.0, 2.0, 100.0], 0.95) == 100.0
    assert _percentile([1.0, 2.0, 100.0], 0.0) == 1.0
