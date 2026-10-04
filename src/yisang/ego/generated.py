from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import json
import re

from yisang.experience.models import PromotionArtifact

from .models import EgoManifest, EgoRiskHints
from .package import semantic_version_key


_INTEGER_VERSION = re.compile(r"^[0-9]+$")


def promotion_version_to_semver(version: str) -> str:
    value = str(version).strip()
    try:
        semantic_version_key(value)
        return value
    except ValueError:
        pass
    if _INTEGER_VERSION.fullmatch(value):
        return f"0.0.{int(value)}"
    raise ValueError(
        "promotion version must be semantic major.minor.patch "
        "or a non-negative integer"
    )


def build_promoted_ego_manifest(
    artifact: PromotionArtifact,
    *,
    ego_id: str,
    version: str | None = None,
) -> EgoManifest:
    if artifact.target not in {"ego_instruction", "ego_procedure"}:
        raise ValueError(
            f"promotion target cannot create E.G.O package: {artifact.target}"
        )
    selected_version = (
        promotion_version_to_semver(version)
        if version is not None
        else promotion_version_to_semver(artifact.version)
    )
    triggers = tuple(
        item.strip()
        for item in artifact.trigger_conditions
        if item.strip()
    )
    base = EgoManifest(
        ego_id=ego_id,
        name=artifact.title,
        provides=(f"learned.{artifact.scope}",),
        keywords=triggers,
        instructions=artifact.content,
        permissions={},
        schema_version=2,
        version=selected_version,
        description=(
            f"Validated YiSang {artifact.kind} promoted from "
            f"{len(artifact.source_episode_ids)} experience episode(s)."
        ),
        tags=("yisang-promotion", artifact.kind, artifact.scope),
        examples=triggers,
        requires=(),
        conflicts=(),
        risk=EgoRiskHints(
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        runtime_type="prompt",
        resources=(),
        evals=(),
        detail_level="full",
    )
    digest = _generated_digest(base, artifact)
    return replace(base, package_digest=f"sha256:{digest}")


def _generated_digest(
    manifest: EgoManifest,
    artifact: PromotionArtifact,
) -> str:
    payload = {
        "manifest": {
            key: value
            for key, value in asdict(manifest).items()
            if key != "package_digest"
        },
        "promotion": {
            "artifact_id": artifact.artifact_id,
            "candidate_id": artifact.candidate_id,
            "validation_run_id": artifact.validation_run_id,
            "evidence_refs": list(artifact.evidence_refs),
            "source_episode_ids": list(artifact.source_episode_ids),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
