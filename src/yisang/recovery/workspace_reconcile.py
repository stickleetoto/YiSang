from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .coordinator import RecoveryCoordinator
from .models import SideEffectReceipt


@dataclass(frozen=True)
class WorkspaceWriteInspection:
    status: str
    workspace_path: str | None
    expected_sha256: str | None
    observed_sha256: str | None
    evidence_ref: str | None = None

    @property
    def matches_expected(self) -> bool:
        return self.status == "matches_expected"


class WorkspaceWriteReconciler:
    """Inspect an uncertain workspace.write_text receipt conservatively."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def inspect(self, receipt: SideEffectReceipt) -> WorkspaceWriteInspection:
        if receipt.tool_id != "workspace.write_text":
            return WorkspaceWriteInspection(
                status="unsupported_tool",
                workspace_path=None,
                expected_sha256=None,
                observed_sha256=None,
            )

        path = receipt.metadata.get("workspace_path")
        expected = receipt.metadata.get("expected_sha256")
        if not isinstance(path, str) or not path:
            return WorkspaceWriteInspection(
                status="missing_metadata",
                workspace_path=None,
                expected_sha256=(
                    expected if isinstance(expected, str) else None
                ),
                observed_sha256=None,
            )
        if not isinstance(expected, str) or not expected.startswith("sha256:"):
            return WorkspaceWriteInspection(
                status="missing_metadata",
                workspace_path=path,
                expected_sha256=None,
                observed_sha256=None,
            )

        target = (self.root / path).resolve()
        if not (target == self.root or self.root in target.parents):
            return WorkspaceWriteInspection(
                status="path_escape",
                workspace_path=path,
                expected_sha256=expected,
                observed_sha256=None,
            )
        if not target.is_file():
            return WorkspaceWriteInspection(
                status="missing",
                workspace_path=path,
                expected_sha256=expected,
                observed_sha256=None,
            )

        observed = "sha256:" + sha256(target.read_bytes()).hexdigest()
        evidence = f"workspace:{path}@{observed}"
        return WorkspaceWriteInspection(
            status=(
                "matches_expected"
                if observed == expected
                else "mismatch"
            ),
            workspace_path=path,
            expected_sha256=expected,
            observed_sha256=observed,
            evidence_ref=evidence,
        )

    def resolve_if_matches(
        self,
        recovery: RecoveryCoordinator,
        *,
        goal_id: str,
        idempotency_key: str,
        run_id: str,
    ) -> WorkspaceWriteInspection:
        if recovery.side_effects is None:
            raise ValueError("side-effect store is not configured")
        receipt = recovery.side_effects.get_receipt(
            goal_id,
            idempotency_key,
        )
        if receipt is None:
            raise KeyError(idempotency_key)
        if receipt.state != "started":
            raise ValueError("only started receipts are uncertain")

        inspection = self.inspect(receipt)
        if not inspection.matches_expected:
            return inspection

        assert inspection.expected_sha256 is not None
        assert inspection.workspace_path is not None
        evidence_refs = (
            (inspection.evidence_ref,)
            if inspection.evidence_ref is not None
            else ()
        )
        recovery.resolve_uncertain_as_committed(
            goal_id=goal_id,
            idempotency_key=idempotency_key,
            run_id=run_id,
            result_ref=(
                f"workspace-file:{inspection.workspace_path}@"
                f"{inspection.expected_sha256}"
            ),
            evidence_refs=evidence_refs,
        )
        return inspection
