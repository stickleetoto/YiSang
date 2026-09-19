from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .snapshot import MigrationRecord

PayloadTransform = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SnapshotMigration:
    migration_id: str
    from_version: int
    to_version: int
    transform: PayloadTransform

    def __post_init__(self) -> None:
        if not self.migration_id.strip():
            raise ValueError("migration_id must be non-empty")
        if self.from_version <= 0 or self.to_version <= 0:
            raise ValueError("migration versions must be positive")
        if self.to_version <= self.from_version:
            raise ValueError("migration must advance the schema version")


class SnapshotMigrationRegistry:
    """Explicit snapshot-schema migration graph.

    No implicit best-effort coercion is performed. Every version transition must
    be registered and the resulting path must be unambiguous.
    """

    def __init__(self) -> None:
        self._migrations: dict[tuple[int, int], SnapshotMigration] = {}

    def register(self, migration: SnapshotMigration) -> None:
        key = (migration.from_version, migration.to_version)
        if key in self._migrations:
            raise ValueError(
                f"duplicate snapshot migration: {migration.from_version}->{migration.to_version}"
            )
        self._migrations[key] = migration

    def plan(
        self,
        from_version: int,
        to_version: int,
    ) -> tuple[SnapshotMigration, ...]:
        if from_version <= 0 or to_version <= 0:
            raise ValueError("snapshot versions must be positive")
        if from_version == to_version:
            return ()
        if from_version > to_version:
            raise ValueError("snapshot downgrade is not supported")

        paths: list[tuple[SnapshotMigration, ...]] = []

        def walk(
            version: int,
            path: tuple[SnapshotMigration, ...],
            visited: frozenset[int],
        ) -> None:
            if version == to_version:
                paths.append(path)
                return
            for (source, target), migration in sorted(self._migrations.items()):
                if source != version or target > to_version or target in visited:
                    continue
                walk(
                    target,
                    (*path, migration),
                    visited | {target},
                )

        walk(from_version, (), frozenset({from_version}))

        if not paths:
            raise ValueError(
                f"no snapshot migration path: {from_version}->{to_version}"
            )
        shortest = min(len(path) for path in paths)
        candidates = [path for path in paths if len(path) == shortest]
        if len(candidates) != 1:
            raise ValueError(
                f"ambiguous snapshot migration path: {from_version}->{to_version}"
            )
        return candidates[0]

    def apply(
        self,
        payload: dict[str, Any],
        *,
        from_version: int,
        to_version: int,
    ) -> tuple[dict[str, Any], tuple[MigrationRecord, ...]]:
        current = dict(payload)
        records: list[MigrationRecord] = []

        for migration in self.plan(from_version, to_version):
            transformed = migration.transform(dict(current))
            if not isinstance(transformed, dict):
                raise ValueError(
                    f"migration {migration.migration_id} returned non-object payload"
                )
            current = transformed
            current["schema_version"] = migration.to_version
            records.append(
                MigrationRecord(
                    migration_id=migration.migration_id,
                    from_version=migration.from_version,
                    to_version=migration.to_version,
                )
            )

        return current, tuple(records)
