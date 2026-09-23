from __future__ import annotations

from yisang.ego.generated import build_promoted_ego_manifest
from yisang.ego.memory_port import InMemoryEgoPort
from yisang.ego.port import InstalledEgoPackage
from yisang.ego.sqlite_port import SQLiteEgoPort
from yisang.experience.models import PromotionArtifact


def _artifact(artifact_id, version, content):
    return PromotionArtifact(
        artifact_id=artifact_id,
        candidate_id=f"candidate-{artifact_id}",
        kind="procedure",
        target="ego_procedure",
        title="Learned debugger",
        content=content,
        version=version,
        source_episode_ids=("episode-1",),
        evidence_refs=("test:1",),
        validation_run_id="replay-1",
        trigger_conditions=("pytest failure",),
        scope="python.debug",
    )


def _package(artifact):
    manifest = build_promoted_ego_manifest(
        artifact,
        ego_id="ego.learned.debug",
    )
    return InstalledEgoPackage(
        ego_id=manifest.ego_id,
        version=manifest.version,
        manifest=manifest,
        source_artifact_id=artifact.artifact_id,
        approval_ref="approval:1",
    )


def _exercise(port):
    first = port.install(_package(_artifact("p1", "1", "step one")))
    second = port.install(_package(_artifact("p2", "2", "step two")))

    assert first.version == "0.0.1"
    assert second.version == "0.0.2"
    assert port.get("ego.learned.debug").version == "0.0.2"
    assert port.get("ego.learned.debug", "0.0.1").state == "superseded"

    restored = port.rollback(
        "ego.learned.debug",
        "0.0.1",
        reason="regression in v2",
    )
    assert restored.active is True
    assert port.get("ego.learned.debug").version == "0.0.1"
    assert port.get("ego.learned.debug", "0.0.2").state == "superseded"

    disabled = port.disable(
        "ego.learned.debug",
        "0.0.1",
        reason="manual disable",
    )
    assert disabled.state == "disabled"
    assert port.list_active() == ()


def test_in_memory_ego_port_install_supersede_rollback():
    _exercise(InMemoryEgoPort())


def test_sqlite_ego_port_survives_restart(tmp_path):
    db = tmp_path / "egos.db"
    with SQLiteEgoPort(db) as port:
        first = port.install(_package(_artifact("p1", "1", "step one")))
        port.install(_package(_artifact("p2", "2", "step two")))
        assert first.version == "0.0.1"

    with SQLiteEgoPort(db) as port:
        assert [item.version for item in port.list_versions("ego.learned.debug")] == [
            "0.0.1",
            "0.0.2",
        ]
        assert port.get("ego.learned.debug").version == "0.0.2"
        port.rollback(
            "ego.learned.debug",
            "0.0.1",
            reason="rollback after restart",
        )

    with SQLiteEgoPort(db) as port:
        assert port.get("ego.learned.debug").version == "0.0.1"
