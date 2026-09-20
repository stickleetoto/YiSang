import json

from yisang.eval.continuity import (
    ContinuityCaseResult,
    build_continuity_report,
    write_continuity_report,
)
from yisang.eval.library_benchmark import (
    LibraryScaleReport,
    LibraryScaleResult,
    evaluate_v06_library_benchmark,
    write_library_scale_report,
)
from yisang.eval.library_benchmark_check import main as library_check_main
from yisang.eval.v06_closeout import main as closeout_main


def _scale(book_count: int) -> LibraryScaleResult:
    return LibraryScaleResult(
        book_count=book_count,
        entry_count=book_count,
        query_count=min(book_count, 50),
        correct_top1=min(book_count, 50),
        selection_accuracy=1.0,
        index_build_ms=1.0,
        mean_search_ms=0.5,
        p95_search_ms=0.9,
        mean_delivery_chars=350.0,
        index_terms=book_count * 3,
        posting_refs=book_count * 5,
    )


def _continuity_case() -> ContinuityCaseResult:
    return ContinuityCaseResult(
        case_id="v06",
        source_engine="engine-a",
        target_engine="engine-b",
        passed=True,
        identity_preserved=True,
        goal_preserved=True,
        state_preserved=True,
        memory_preserved=True,
        capabilities_preserved=True,
        continuity_fingerprint_preserved=True,
        source_engine_used=True,
        target_engine_used=True,
        source_expected_memory_retrieved=True,
        source_expected_ego_selected=True,
        expected_memory_retrieved=True,
        expected_ego_selected=True,
        restore_latency_ms=1.0,
        probe_latency_ms=2.0,
        source_fingerprint="a" * 64,
        restored_fingerprint="a" * 64,
        source_used_memory_ids=("m1",),
        source_used_ego_ids=("ego.debug",),
        used_memory_ids=("m1",),
        used_ego_ids=("ego.debug",),
        source_response_text="source",
        response_text="target",
        library_preserved=True,
        source_expected_knowledge_retrieved=True,
        expected_knowledge_retrieved=True,
        source_used_knowledge_refs=("k_123",),
        used_knowledge_refs=("k_123",),
    )


def test_library_benchmark_check_accepts_required_scale_matrix():
    report = LibraryScaleReport(
        schema_version=1,
        results=tuple(_scale(value) for value in (10, 50, 100, 500)),
    )

    check = evaluate_v06_library_benchmark(report)

    assert check.ready is True
    assert check.errors == ()


def test_library_benchmark_check_rejects_missing_scale():
    report = LibraryScaleReport(
        schema_version=1,
        results=tuple(_scale(value) for value in (10, 50, 100)),
    )

    check = evaluate_v06_library_benchmark(report)

    assert check.ready is False
    assert any("500" in error for error in check.errors)


def test_library_check_cli_round_trip(tmp_path, capsys):
    report = LibraryScaleReport(
        schema_version=1,
        results=tuple(_scale(value) for value in (10, 50, 100, 500)),
    )
    path = write_library_scale_report(tmp_path / "library.json", report)

    exit_code = library_check_main(["--input", str(path)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ready"] is True


def test_composite_v06_closeout_accepts_both_evidence_sets(tmp_path, capsys):
    case = _continuity_case()
    continuity = build_continuity_report(
        [case, case, case],
        metadata={
            "source_model": "llama-model",
            "target_model": "qwen-model",
            "source_family": "llama",
            "target_family": "qwen",
            "library_probe": True,
        },
    )
    library = LibraryScaleReport(
        schema_version=1,
        results=tuple(_scale(value) for value in (10, 50, 100, 500)),
    )

    continuity_path = write_continuity_report(
        continuity,
        tmp_path / "continuity.json",
    )
    library_path = write_library_scale_report(
        tmp_path / "library.json",
        library,
    )

    exit_code = closeout_main(
        [
            "--continuity",
            str(continuity_path),
            "--library",
            str(library_path),
            "--min-repeats",
            "3",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ready"] is True
    assert payload["continuity"]["ready"] is True
    assert payload["library"]["ready"] is True
