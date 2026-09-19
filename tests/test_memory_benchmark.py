import json

from yisang.eval.memory_benchmark import (
    DEFAULT_MEMORY_CASES,
    MEMORY_BENCHMARK_PROFILES,
    MemoryBenchmarkCase,
    MemorySeed,
    main,
    run_memory_benchmark,
    run_memory_case,
    run_profile_matrix,
)


def test_default_memory_benchmark_has_four_categories():
    categories = {case.category for case in DEFAULT_MEMORY_CASES}

    assert categories == {
        "static_dynamic",
        "workflow_gotcha",
        "cross_session",
        "poisoning",
    }
    assert len(DEFAULT_MEMORY_CASES) == 40
    assert all(
        sum(1 for case in DEFAULT_MEMORY_CASES if case.category == category) == 10
        for category in categories
    )


def test_poisoning_case_quarantines_untrusted_seed():
    case = next(
        item
        for item in DEFAULT_MEMORY_CASES
        if item.case_id == "poison-ignore-policy"
    )

    result = run_memory_case(case)

    assert result.passed is True
    assert result.quarantined_count == 1
    assert result.forbidden_hits == 0
    assert result.expected_found == result.expected_count


def test_custom_case_precision_uses_custom_expected_contents():
    case = MemoryBenchmarkCase(
        case_id="custom",
        category="custom",
        query="alpha",
        seeds=(
            MemorySeed("alpha relevant"),
            MemorySeed("alpha distractor"),
        ),
        expected_contents=("alpha relevant",),
    )

    result = run_memory_case(case)

    assert result.passed is True
    assert result.recall == 1.0
    assert result.precision == 0.5


def test_default_report_is_serializable_and_tracks_poison_escape():
    report = run_memory_benchmark()
    payload = report.to_dict()

    assert payload["schema_version"] == 1
    assert payload["summary"]["case_count"] == 40
    assert payload["summary"]["pass_rate"] == 1.0
    assert payload["summary"]["mean_recall"] == 1.0
    assert payload["summary"]["forbidden_hits"] == 0
    assert payload["summary"]["poison_escape_rate"] == 0.0
    json.dumps(payload)


def test_memory_benchmark_cli_writes_report(tmp_path, capsys):
    output = tmp_path / "memory-report.json"

    exit_code = main(["--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code in {0, 1}
    assert payload["summary"]["case_count"] == 40
    assert "poison_escape_rate" in capsys.readouterr().out


def test_profile_matrix_compares_all_required_v04_modes():
    cases = tuple(
        case for case in DEFAULT_MEMORY_CASES
        if case.case_id in {"cross-session-procedure", "poison-ignore-policy"}
    )
    matrix = run_profile_matrix(cases)

    assert set(matrix) == {
        "memory_disabled",
        "session_only",
        "retrieval_memory",
        "retrieval_procedural",
        "retrieval_procedural_provenance",
    }
    assert matrix["retrieval_procedural_provenance"].to_dict()["summary"]["poison_escape_rate"] == 0.0
    assert matrix["retrieval_memory"].to_dict()["summary"]["poison_escape_rate"] >= 0.0


def test_default_profile_is_governed_provenance():
    report = run_memory_benchmark(
        tuple(
            case for case in DEFAULT_MEMORY_CASES
            if case.case_id == "poison-ignore-policy"
        )
    )

    assert report.profile == MEMORY_BENCHMARK_PROFILES[-1].name
    assert report.to_dict()["summary"]["poison_escape_rate"] == 0.0
