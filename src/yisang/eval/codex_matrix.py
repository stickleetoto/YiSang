from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

VerifierKind = Literal[
    "file_exact",
    "file_contains",
    "directory_exists",
    "command_success",
    "expected_failure_then_recovery",
    "stop_after_success",
]


@dataclass(frozen=True)
class CodexEvalCase:
    case_id: str
    description: str
    prompt: str
    verifier: VerifierKind
    setup_files: dict[str, str] = field(default_factory=dict)
    expected_path: str | None = None
    expected_text: str | None = None
    max_tool_calls: int | None = None

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must be non-empty")
        if not self.prompt.strip():
            raise ValueError("prompt must be non-empty")
        if self.max_tool_calls is not None and self.max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")


DEFAULT_CODEX_V031_MATRIX: tuple[CodexEvalCase, ...] = (
    CodexEvalCase(
        case_id="read-file",
        description="Read a known workspace file without mutating it.",
        prompt=(
            "Use exec_command to read test.txt. Then respond with exactly "
            "YISANG_READ_OK if the file contains hello."
        ),
        verifier="command_success",
        setup_files={"test.txt": "hello\n"},
        expected_text="YISANG_READ_OK",
        max_tool_calls=1,
    ),
    CodexEvalCase(
        case_id="write-exact-file",
        description="Create a file with exact requested content.",
        prompt=(
            "Use exec_command to create result.txt containing exactly "
            "YISANG_WRITE_OK with no extra newline."
        ),
        verifier="file_exact",
        expected_path="result.txt",
        expected_text="YISANG_WRITE_OK",
        max_tool_calls=1,
    ),
    CodexEvalCase(
        case_id="edit-one-line",
        description="Perform one deterministic line replacement.",
        prompt=(
            "Use exec_command to replace MODE=old with MODE=new in config.txt. "
            "Do not change any other line."
        ),
        verifier="file_exact",
        setup_files={"config.txt": "NAME=yisang\nMODE=old\n"},
        expected_path="config.txt",
        expected_text="NAME=yisang\nMODE=new\n",
        max_tool_calls=2,
    ),
    CodexEvalCase(
        case_id="create-directory",
        description="Create one requested directory.",
        prompt="Use exec_command to create a directory named yisang-e2e-dir.",
        verifier="directory_exists",
        expected_path="yisang-e2e-dir",
        max_tool_calls=1,
    ),
    CodexEvalCase(
        case_id="git-status",
        description="Inspect repository status without modifying the repository.",
        prompt=(
            "Use exec_command to run git status --short. Do not modify files. "
            "Then briefly report whether the worktree is clean."
        ),
        verifier="command_success",
        max_tool_calls=1,
    ),
    CodexEvalCase(
        case_id="missing-file-recovery",
        description="Encounter a missing file, recover, and finish a bounded task.",
        prompt=(
            "Try to read missing.txt with exec_command. If it does not exist, "
            "create recovery.txt containing exactly YISANG_RECOVERY_OK and stop."
        ),
        verifier="expected_failure_then_recovery",
        expected_path="recovery.txt",
        expected_text="YISANG_RECOVERY_OK",
        max_tool_calls=2,
    ),
    CodexEvalCase(
        case_id="stop-after-success",
        description="Do not perform unrelated work after the requested effect succeeds.",
        prompt=(
            "Use exec_command once to create done.txt containing exactly "
            "YISANG_DONE. After success, do not use any more tools."
        ),
        verifier="stop_after_success",
        expected_path="done.txt",
        expected_text="YISANG_DONE",
        max_tool_calls=1,
    ),
)


def matrix_case_ids(
    matrix: tuple[CodexEvalCase, ...] = DEFAULT_CODEX_V031_MATRIX,
) -> tuple[str, ...]:
    return tuple(case.case_id for case in matrix)
