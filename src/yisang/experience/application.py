from __future__ import annotations

from dataclasses import replace
import uuid

from yisang.library import Book, KnowledgeEntry, LibraryPort

from .models import (
    EgoInstructionPatch,
    PromotionApplyReceipt,
    PromotionApplyRequest,
    PromotionArtifact,
)
from .port import PromotionPort


class PromotionApplicationError(ValueError):
    pass


def _load_applicable(
    promotions: PromotionPort,
    request: PromotionApplyRequest,
    *,
    allowed_targets: set[str] | frozenset[str],
) -> PromotionArtifact:
    artifact = promotions.get(request.artifact_id)
    if artifact is None:
        raise KeyError(request.artifact_id)
    if not artifact.active:
        raise PromotionApplicationError("promotion artifact is not active")
    if artifact.target not in allowed_targets:
        raise PromotionApplicationError(
            f"promotion target {artifact.target!r} is not supported here"
        )
    return artifact


class LibraryKnowledgeApplyAdapter:
    """Explicit side-effect boundary from promotion artifact to Roland Library."""

    def __init__(
        self,
        promotions: PromotionPort,
        library: LibraryPort,
    ) -> None:
        self._promotions = promotions
        self._library = library

    def apply(
        self,
        request: PromotionApplyRequest,
        *,
        book_id: str,
    ) -> PromotionApplyReceipt:
        artifact = _load_applicable(
            self._promotions,
            request,
            allowed_targets={"library_knowledge"},
        )
        expected_target_ref = f"library_book:{book_id}"
        if request.target_ref != expected_target_ref:
            raise PromotionApplicationError(
                f"target_ref must be {expected_target_ref!r}"
            )

        previous = self._promotions.find_applied(
            artifact_id=artifact.artifact_id,
            target_ref=request.target_ref,
        )
        if previous is not None:
            return PromotionApplyReceipt(
                apply_id=previous.apply_id,
                artifact_id=previous.artifact_id,
                target=previous.target,
                target_ref=previous.target_ref,
                actor=previous.actor,
                approval_ref=previous.approval_ref,
                reason=previous.reason,
                status="already_applied",
                result_ref=previous.result_ref,
                created_at=previous.created_at,
            )

        book = self._library.get_book(book_id)
        if book is None:
            raise KeyError(book_id)

        entry_id = f"promoted-{artifact.artifact_id}"
        existing = self._library.get_entry(book_id, entry_id)
        if existing is None:
            entry = KnowledgeEntry(
                entry_id=entry_id,
                title=artifact.title,
                summary=artifact.content,
                tags=("yisang-promotion", artifact.kind),
                use_when=artifact.trigger_conditions,
                source_refs=tuple(
                    dict.fromkeys(
                        (*artifact.evidence_refs, f"promotion:{artifact.artifact_id}")
                    )
                ),
                trust_class="verified",
                validation_state="promoted",
            )
            updated_book = replace(book, entries=(*book.entries, entry))
            self._library.put_book(updated_book)
        else:
            if (
                existing.title != artifact.title
                or existing.summary != artifact.content
            ):
                raise PromotionApplicationError(
                    "stable promoted entry id already exists with different content"
                )

        receipt = PromotionApplyReceipt(
            apply_id=f"apply-{uuid.uuid4().hex[:12]}",
            artifact_id=artifact.artifact_id,
            target=artifact.target,
            target_ref=request.target_ref,
            actor=request.actor,
            approval_ref=request.approval_ref,
            reason=request.reason,
            status="applied",
            result_ref=f"library:{book_id}/{entry_id}",
        )
        self._promotions.record_receipt(receipt)
        return receipt


class EgoInstructionPatchAdapter:
    """Builds an approved E.G.O patch without mutating the registry.

    E.G.O manifests are file/package backed today. Returning a patch keeps the
    v0.7 promotion boundary explicit until a durable E.G.O mutation port exists.
    """

    def __init__(self, promotions: PromotionPort) -> None:
        self._promotions = promotions

    def build_patch(
        self,
        request: PromotionApplyRequest,
        *,
        ego_id: str,
    ) -> EgoInstructionPatch:
        artifact = _load_applicable(
            self._promotions,
            request,
            allowed_targets={"ego_instruction", "ego_procedure"},
        )
        expected_target_ref = f"ego:{ego_id}"
        if request.target_ref != expected_target_ref:
            raise PromotionApplicationError(
                f"target_ref must be {expected_target_ref!r}"
            )
        return EgoInstructionPatch(
            patch_id=f"ego-patch-{uuid.uuid4().hex[:12]}",
            artifact_id=artifact.artifact_id,
            ego_id=ego_id,
            target=artifact.target,
            instruction=artifact.content,
            version=artifact.version,
            evidence_refs=artifact.evidence_refs,
            approval_ref=request.approval_ref,
        )
