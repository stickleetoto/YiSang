from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import time
from typing import Any, Iterable, TYPE_CHECKING

from yisang.execution.models import ActionProposal, ActionResult

from .executor import (
    FileExpectation,
    ReplayExecutionSpec,
    ReplaySetupFile,
)
from .models import ExperienceEpisode
from .replay import ReplayPlan
if TYPE_CHECKING:
    from .trace_port import ActionTracePort

_REPLAY_MANIFEST_KEYS = frozenset(
    {
        "version",
        "argv",
        "expected_exit_code",
        "stdout_contains",
        "stderr_contains",
        "setup_files",
        "file_expectations",
        "timeout_seconds",
    }
)


class ReplayManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayExecutionTemplate:
    argv: tuple[str, ...]
    expected_exit_code: int = 0
    stdout_contains: tuple[str, ...] = ()
    stderr_contains: tuple[str, ...] = ()
    setup_files: tuple[ReplaySetupFile, ...] = ()
    file_expectations: tuple[FileExpectation, ...] = ()
    timeout_seconds: float = 30.0
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError("unsupported replay manifest version")
        ReplayExecutionSpec(
            test_id="template-validation",
            argv=self.argv,
            expected_exit_code=self.expected_exit_code,
            stdout_contains=self.stdout_contains,
            stderr_contains=self.stderr_contains,
            setup_files=self.setup_files,
            file_expectations=self.file_expectations,
            timeout_seconds=self.timeout_seconds,
        )

    def to_spec(self, test_id: str) -> ReplayExecutionSpec:
        return ReplayExecutionSpec(
            test_id=test_id,
            argv=self.argv,
            expected_exit_code=self.expected_exit_code,
            stdout_contains=self.stdout_contains,
            stderr_contains=self.stderr_contains,
            setup_files=self.setup_files,
            file_expectations=self.file_expectations,
            timeout_seconds=self.timeout_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "argv": list(self.argv),
            "expected_exit_code": self.expected_exit_code,
            "stdout_contains": list(self.stdout_contains),
            "stderr_contains": list(self.stderr_contains),
            "setup_files": [
                {"path": item.path, "content": item.content}
                for item in self.setup_files
            ],
            "file_expectations": [
                {
                    "path": item.path,
                    "must_exist": item.must_exist,
                    "exact_text": item.exact_text,
                }
                for item in self.file_expectations
            ],
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReplayExecutionTemplate":
        if not isinstance(value, dict):
            raise ReplayManifestError("replay_manifest must be an object")
        unknown = sorted(set(value) - _REPLAY_MANIFEST_KEYS)
        if unknown:
            raise ReplayManifestError(
                "unknown replay manifest fields: " + ", ".join(unknown)
            )
        version = value.get("version", 1)
        if version != 1:
            raise ReplayManifestError(
                f"unsupported replay manifest version: {version}"
            )

        argv = _string_tuple(value.get("argv"), name="argv", required=True)
        stdout_contains = _string_tuple(
            value.get("stdout_contains", ()),
            name="stdout_contains",
        )
        stderr_contains = _string_tuple(
            value.get("stderr_contains", ()),
            name="stderr_contains",
        )

        expected_exit_code = value.get("expected_exit_code", 0)
        if isinstance(expected_exit_code, bool) or not isinstance(
            expected_exit_code, int
        ):
            raise ReplayManifestError("expected_exit_code must be an integer")

        timeout_seconds = value.get("timeout_seconds", 30.0)
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, float)
        ):
            raise ReplayManifestError("timeout_seconds must be numeric")

        setup_raw = value.get("setup_files", ())
        if not isinstance(setup_raw, (list, tuple)):
            raise ReplayManifestError("setup_files must be an array")
        setup_files: list[ReplaySetupFile] = []
        for item in setup_raw:
            if not isinstance(item, dict) or set(item) != {"path", "content"}:
                raise ReplayManifestError(
                    "each setup_file must contain exactly path and content"
                )
            if not isinstance(item["path"], str) or not isinstance(
                item["content"], str
            ):
                raise ReplayManifestError(
                    "setup_file path/content must be strings"
                )
            setup_files.append(
                ReplaySetupFile(path=item["path"], content=item["content"])
            )

        expectations_raw = value.get("file_expectations", ())
        if not isinstance(expectations_raw, (list, tuple)):
            raise ReplayManifestError("file_expectations must be an array")
        expectations: list[FileExpectation] = []
        for item in expectations_raw:
            if not isinstance(item, dict):
                raise ReplayManifestError(
                    "each file_expectation must be an object"
                )
            allowed = {"path", "must_exist", "exact_text"}
            unknown_expectation = sorted(set(item) - allowed)
            if unknown_expectation or "path" not in item:
                raise ReplayManifestError(
                    "invalid file_expectation fields"
                )
            path = item["path"]
            must_exist = item.get("must_exist", True)
            exact_text = item.get("exact_text")
            if not isinstance(path, str):
                raise ReplayManifestError(
                    "file_expectation path must be a string"
                )
            if not isinstance(must_exist, bool):
                raise ReplayManifestError(
                    "file_expectation must_exist must be boolean"
                )
            if exact_text is not None and not isinstance(exact_text, str):
                raise ReplayManifestError(
                    "file_expectation exact_text must be a string"
                )
            expectations.append(
                FileExpectation(
                    path=path,
                    must_exist=must_exist,
                    exact_text=exact_text,
                )
            )

        try:
            return cls(
                argv=argv,
                expected_exit_code=expected_exit_code,
                stdout_contains=stdout_contains,
                stderr_contains=stderr_contains,
                setup_files=tuple(setup_files),
                file_expectations=tuple(expectations),
                timeout_seconds=float(timeout_seconds),
                version=version,
            )
        except ValueError as exc:
            raise ReplayManifestError(str(exc)) from exc


@dataclass(frozen=True)
class ActionTrace:
    trace_id: str
    request_id: str
    ordinal: int
    tool_id: str
    status: str
    goal_satisfied: bool
    arguments_sha256: str
    replay_template: ReplayExecutionTemplate | None = None
    manifest_rejection_reason: str | None = None
    created_at: float = field(default_factory=time.time)

    @property
    def replayable(self) -> bool:
        return (
            self.status == "EXECUTED"
            and self.goal_satisfied
            and self.replay_template is not None
            and self.manifest_rejection_reason is None
        )


class ActionTraceRecorder:
    def record(
        self,
        *,
        request_id: str,
        ordinal: int,
        proposal: ActionProposal,
        result: ActionResult,
    ) -> ActionTrace:
        if ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        arguments_sha256 = _arguments_digest(proposal.arguments)
        manifest = result.completion_evidence.get("replay_manifest")
        template: ReplayExecutionTemplate | None = None
        rejection: str | None = None

        if manifest is not None:
            if result.status != "EXECUTED" or not result.goal_satisfied:
                rejection = "action_not_verified_for_replay"
            else:
                try:
                    template = ReplayExecutionTemplate.from_dict(manifest)
                except (ReplayManifestError, ValueError) as exc:
                    rejection = f"invalid_replay_manifest:{exc}"

        identity = {
            "request_id": request_id,
            "ordinal": ordinal,
            "tool_id": proposal.action,
            "arguments_sha256": arguments_sha256,
        }
        digest = sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        return ActionTrace(
            trace_id=f"trace-{digest}",
            request_id=request_id,
            ordinal=ordinal,
            tool_id=proposal.action,
            status=result.status,
            goal_satisfied=result.goal_satisfied,
            arguments_sha256=arguments_sha256,
            replay_template=template,
            manifest_rejection_reason=rejection,
        )


class ReplayManifestCompiler:
    """Compile trusted runtime traces into executor specs.

    v1 intentionally supports one replayable tool step per ReplayPlan case.
    Multi-tool historical traces require an ordered multi-step executor contract
    and are rejected instead of being guessed.
    """

    def compile(
        self,
        plan: ReplayPlan,
        episodes: Iterable[ExperienceEpisode],
        traces: ActionTracePort,
    ) -> tuple[ReplayExecutionSpec, ...]:
        episode_items = tuple(episodes)
        episode_map = {
            episode.episode_id: episode for episode in episode_items
        }
        if len(episode_map) != len(episode_items):
            raise ReplayManifestError("duplicate source episode ids")

        specs: list[ReplayExecutionSpec] = []
        for case in plan.cases:
            episode = episode_map.get(case.source_episode_id)
            if episode is None:
                raise ReplayManifestError(
                    f"missing source episode: {case.source_episode_id}"
                )
            if not episode.request_id:
                raise ReplayManifestError(
                    f"source episode lacks request_id: {episode.episode_id}"
                )
            expected_tools = tuple(
                step.removeprefix("tool:")
                for step in case.expected_procedure_steps
                if step.startswith("tool:")
            )
            if len(expected_tools) != 1:
                raise ReplayManifestError(
                    "v1 trace compiler requires exactly one replayable "
                    f"tool step per case: {case.test_id}"
                )
            expected_tool = expected_tools[0]
            candidates = tuple(
                trace
                for trace in traces.for_request(episode.request_id)
                if trace.tool_id == expected_tool and trace.replayable
            )
            if not candidates:
                raise ReplayManifestError(
                    f"no replayable trace for {case.test_id}: {expected_tool}"
                )
            if len(candidates) > 1:
                raise ReplayManifestError(
                    f"ambiguous replayable trace for {case.test_id}: "
                    f"{expected_tool}"
                )
            template = candidates[0].replay_template
            assert template is not None
            specs.append(template.to_spec(case.test_id))
        return tuple(specs)


def _arguments_digest(arguments: dict[str, Any]) -> str:
    raw = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _string_tuple(
    value: Any,
    *,
    name: str,
    required: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ReplayManifestError(f"{name} must be an array")
    result = tuple(value)
    if any(not isinstance(item, str) for item in result):
        raise ReplayManifestError(f"{name} must contain only strings")
    if required and not result:
        raise ReplayManifestError(f"{name} must be non-empty")
    return result
