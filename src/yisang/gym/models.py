from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class GymTaskSpec:
    task_id: str
    title: str
    difficulty: str
    goal: str
    allowed_paths: tuple[str, ...]
    required_paths: tuple[str, ...]
    verify: tuple[tuple[str, ...], ...]
    forbidden_actions: tuple[str, ...] = ()
    max_changed_files: int | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "GymTaskSpec":
        task_path = Path(path)
        raw = json.loads(task_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("task spec must be a JSON object")

        task_id = _required_text(raw, "id")
        title = _required_text(raw, "title")
        difficulty = _required_text(raw, "difficulty")
        goal = _required_text(raw, "goal")

        allowed_paths = _string_tuple(raw.get("allowed_paths"), "allowed_paths")
        if not allowed_paths:
            raise ValueError("allowed_paths must contain at least one pattern")

        required_paths = _string_tuple(raw.get("required_paths", []), "required_paths")
        forbidden_actions = _string_tuple(
            raw.get("forbidden_actions", []),
            "forbidden_actions",
        )

        raw_verify = raw.get("verify")
        if not isinstance(raw_verify, list) or not raw_verify:
            raise ValueError("verify must contain at least one argv command")
        verify: list[tuple[str, ...]] = []
        for index, command in enumerate(raw_verify):
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(part, str) or not part for part in command)
            ):
                raise ValueError(
                    f"verify[{index}] must be a non-empty string argv list"
                )
            verify.append(tuple(command))

        max_changed_files = raw.get("max_changed_files")
        if max_changed_files is not None:
            if not isinstance(max_changed_files, int) or max_changed_files <= 0:
                raise ValueError("max_changed_files must be a positive integer")

        return cls(
            task_id=task_id,
            title=title,
            difficulty=difficulty,
            goal=goal,
            allowed_paths=allowed_paths,
            required_paths=required_paths,
            verify=tuple(verify),
            forbidden_actions=forbidden_actions,
            max_changed_files=max_changed_files,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "title": self.title,
            "difficulty": self.difficulty,
            "goal": self.goal,
            "allowed_paths": list(self.allowed_paths),
            "required_paths": list(self.required_paths),
            "verify": [list(command) for command in self.verify],
            "forbidden_actions": list(self.forbidden_actions),
            "max_changed_files": self.max_changed_files,
        }


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{key} must contain only non-empty strings")
    return tuple(item.strip() for item in value)
