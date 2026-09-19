from pathlib import Path

from yisang.eval.codex_matrix import DEFAULT_CODEX_V031_MATRIX, matrix_case_ids
from yisang.eval.codex_runner import (
    count_retries,
    count_tool_calls,
    parse_tokens_used,
    verify_case,
)


def _case(case_id):
    return next(case for case in DEFAULT_CODEX_V031_MATRIX if case.case_id == case_id)


def test_v031_matrix_has_unique_required_cases():
    ids = matrix_case_ids()

    assert len(ids) == len(set(ids))
    assert {
        "read-file",
        "write-exact-file",
        "edit-one-line",
        "create-directory",
        "git-status",
        "missing-file-recovery",
        "stop-after-success",
    }.issubset(set(ids))


def test_verify_exact_file_case(tmp_path):
    case = _case("write-exact-file")
    target = tmp_path / case.expected_path
    target.write_text(case.expected_text, encoding="utf-8")

    ok, error = verify_case(
        case,
        tmp_path,
        process_returncode=0,
        combined_output="",
        tool_calls=1,
    )

    assert ok is True
    assert error is None


def test_stop_after_success_fails_when_tool_budget_exceeded(tmp_path):
    case = _case("stop-after-success")
    target = tmp_path / case.expected_path
    target.write_text(case.expected_text, encoding="utf-8")

    ok, error = verify_case(
        case,
        tmp_path,
        process_returncode=0,
        combined_output="",
        tool_calls=2,
    )

    assert ok is False
    assert error == "tool call budget exceeded"


def test_parse_codex_console_metrics():
    output = """exec
command here
 succeeded in 100ms:
exec
command two
tokens used
4,337
retrying request
"""

    assert count_tool_calls(output) == 2
    assert count_retries(output) == 1
    assert parse_tokens_used(output) == 4337


def test_command_success_requires_expected_marker(tmp_path):
    case = _case("read-file")

    ok, error = verify_case(
        case,
        Path(tmp_path),
        process_returncode=0,
        combined_output="wrong answer",
        tool_calls=1,
    )

    assert ok is False
    assert "expected response marker missing" in error
