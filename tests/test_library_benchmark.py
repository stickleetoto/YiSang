import json

from yisang.eval.library_benchmark import (
    DEFAULT_LIBRARY_SCALES,
    main,
    run_library_scale,
    run_library_scale_benchmark,
)


def test_single_scale_has_perfect_top1_accuracy():
    result = run_library_scale(25, max_queries=25)

    assert result.book_count == 25
    assert result.entry_count == 25
    assert result.query_count == 25
    assert result.correct_top1 == 25
    assert result.selection_accuracy == 1.0
    assert result.index_terms > 0
    assert result.posting_refs > 0
    assert result.mean_delivery_chars > 0


def test_default_scale_matrix_covers_v06_targets():
    report = run_library_scale_benchmark()

    assert tuple(item.book_count for item in report.results) == DEFAULT_LIBRARY_SCALES
    assert report.all_passed is True
    assert all(item.selection_accuracy == 1.0 for item in report.results)
    assert all(item.query_count > 0 for item in report.results)


def test_library_benchmark_cli_writes_serializable_report(tmp_path, capsys):
    output = tmp_path / "library-scale.json"

    exit_code = main(
        [
            "--output",
            str(output),
            "--scale",
            "10",
            "--scale",
            "50",
            "--max-queries",
            "10",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["all_passed"] is True
    assert [item["book_count"] for item in payload["scales"]] == [10, 50]
    assert "selection_accuracy" in capsys.readouterr().out
