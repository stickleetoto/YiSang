import json

import pytest

from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.sqlite import SQLiteMemoryPort
from yisang.memory.transfer import (
    build_memory_archive,
    export_memory_archive,
    load_memory_archive,
    restore_memory_archive,
)


def _seed(memory):
    memory.commit(
        MemoryProposal(
            content="persistent identity memory",
            kind="semantic",
            source_engine="engine-a",
            source_id="turn-1",
            source_type="conversation",
            confidence=0.9,
            evidence=["user:turn-1"],
            trust_class="verified",
            importance=0.8,
            writer="governor",
        )
    )
    memory.commit(
        MemoryProposal(
            content="validated procedure",
            kind="procedural",
            source_engine="engine-b",
            confidence=0.95,
            evidence=["tool:run-1"],
            trust_class="trusted",
        )
    )


def test_memory_archive_round_trip_between_backends(tmp_path):
    source = InMemoryMemoryPort()
    _seed(source)

    archive_path = export_memory_archive(source, tmp_path / "memory.json")
    archive = load_memory_archive(archive_path)

    target = SQLiteMemoryPort(tmp_path / "restored.db")
    restored = restore_memory_archive(target, archive)

    assert restored == 2
    assert [record.content for record in target.all()] == [
        "persistent identity memory",
        "validated procedure",
    ]
    first = target.all()[0]
    assert first.source_id == "turn-1"
    assert first.evidence_refs == ("user:turn-1",)
    assert first.trust_class == "verified"
    target.close()


def test_memory_archive_detects_tampering_before_restore(tmp_path):
    source = InMemoryMemoryPort()
    _seed(source)
    archive = build_memory_archive(source)
    archive["records"][0]["content"] = "tampered"

    target = InMemoryMemoryPort()
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_memory_archive(target, archive)

    assert target.all() == []


def test_restore_preflights_id_conflicts_without_partial_mutation():
    source = InMemoryMemoryPort()
    _seed(source)
    archive = build_memory_archive(source)

    target = InMemoryMemoryPort()
    target.import_record(source.all()[0])
    before = list(target.all())

    with pytest.raises(ValueError, match="conflicts"):
        restore_memory_archive(target, archive)

    assert target.all() == before


def test_restore_overwrite_replaces_same_memory_id():
    source = InMemoryMemoryPort()
    _seed(source)
    archive = build_memory_archive(source)
    original = source.all()[0]

    target = InMemoryMemoryPort()
    target.import_record(original)
    archive["records"][0]["content"] = "updated content"

    # Recompute a valid archive after the intentional content change.
    changed = InMemoryMemoryPort()
    for raw in archive["records"]:
        from yisang.memory.transfer import record_from_dict

        changed.import_record(record_from_dict(raw))
    valid_archive = build_memory_archive(changed)

    restored = restore_memory_archive(target, valid_archive, overwrite=True)

    assert restored == 2
    assert len(target.all()) == 2
    assert target.all()[0].content == "updated content"


def test_memory_archive_cli_shape_is_json_serializable():
    memory = InMemoryMemoryPort()
    _seed(memory)

    archive = build_memory_archive(memory)
    encoded = json.dumps(archive)

    assert archive["record_count"] == 2
    assert len(archive["records_sha256"]) == 64
    assert '"archive_schema_version": 1' in encoded
