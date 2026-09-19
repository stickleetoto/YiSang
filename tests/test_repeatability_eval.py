import json

from yisang.eval.repeatability import (
    RunMetrics,
    aggregate_case,
    build_report,
    evaluate_baseline,
    load_jsonl,
    main,
    run_case,
)


def test_aggregate_case_computes_v031_metrics():
    case = aggregate_case(
        "write-file",
        [
            RunMetrics(
                success=True,
                tool_calls=1,
                completion_after_success=True,
                latency_ms=100,
                context_tokens=1000,
            ),
            RunMetrics(
                success=True,
                tool_calls=1,
                malformed_tool_calls=1,
                retries=1,
                completion_after_success=False,
                latency_ms=200,
                context_tokens=1200,
            ),
        ],
    )

    assert case.runs == 2
    assert case.success_rate == 1.0
    assert case.tool_calls_mean == 1.0
    assert case.malformed_tool_call_rate == 0.5
    assert case.retries_mean == 0.5
    assert case.completion_after_success_rate == 0.5
    assert case.latency_ms_p50 == 150
    assert case.context_tokens_mean == 1100


def test_baseline_gate_requires_success_and_no_duplicate_side_effects():
    report = build_report(
        {
            "good": [
                RunMetrics(success=True),
                RunMetrics(success=True),
            ],
            "bad": [
                RunMetrics(success=True),
                RunMetrics(success=False, duplicate_side_effects=1),
            ],
        }
    )

    gate = evaluate_baseline(report, min_success_rate=0.90)

    assert gate.passed is False
    assert gate.failed_cases == ("bad",)
    assert gate.duplicate_side_effects == 1


def test_run_case_measures_latency_when_runner_does_not():
    case = run_case(
        "noop",
        lambda: RunMetrics(success=True),
        repetitions=2,
    )

    assert case.runs == 2
    assert case.success_rate == 1.0
    assert case.latency_ms_p50 >= 0


def test_load_jsonl_and_cli_write_report(tmp_path, capsys):
    source = tmp_path / "runs.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "read-file",
                        "success": True,
                        "tool_calls": 1,
                        "completion_after_success": True,
                        "latency_ms": 10,
                        "context_tokens": 100,
                    }
                ),
                json.dumps(
                    {
                        "case_id": "read-file",
                        "success": True,
                        "tool_calls": 1,
                        "completion_after_success": True,
                        "latency_ms": 12,
                        "context_tokens": 110,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    grouped = load_jsonl(source)
    assert len(grouped["read-file"]) == 2

    exit_code = main(
        [
            "--input",
            str(source),
            "--output",
            str(output),
            "--min-success-rate",
            "0.9",
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["cases"][0]["success_rate"] == 1.0
    assert '"passed": true' in capsys.readouterr().out.lower()


def test_cli_fails_when_threshold_is_not_met(tmp_path):
    source = tmp_path / "runs.jsonl"
    source.write_text(
        json.dumps({"case_id": "bad", "success": False}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--input",
            str(source),
            "--output",
            str(tmp_path / "report.json"),
        ]
    )

    assert exit_code == 1
