from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock

from .models import GOAL_STATES, GoalBudget, GoalRecord
from .port import GoalPort


class SQLiteGoalPort(GoalPort):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    state TEXT NOT NULL,
                    milestones_json TEXT NOT NULL,
                    completed_work_json TEXT NOT NULL,
                    blockers_json TEXT NOT NULL,
                    next_action TEXT,
                    exit_condition TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_goals_state
                ON goals(state, updated_at)
                """
            )
            self._conn.commit()

    def put(self, goal: GoalRecord) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO goals (
                        goal_id, description, state, milestones_json,
                        completed_work_json, blockers_json, next_action,
                        exit_condition, budget_json, provenance_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _goal_values(goal),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"duplicate goal: {goal.goal_id}") from exc
            self._conn.commit()

    def get(self, goal_id: str) -> GoalRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM goals WHERE goal_id=?",
                (goal_id,),
            ).fetchone()
        return None if row is None else _goal_from_row(row)

    def update(self, goal: GoalRecord) -> None:
        current = self.get(goal.goal_id)
        if current is None:
            raise KeyError(goal.goal_id)
        if goal.created_at != current.created_at:
            raise ValueError("goal created_at is immutable")
        with self._lock:
            self._conn.execute(
                """
                UPDATE goals
                SET description=?, state=?, milestones_json=?,
                    completed_work_json=?, blockers_json=?, next_action=?,
                    exit_condition=?, budget_json=?, provenance_json=?,
                    updated_at=?
                WHERE goal_id=?
                """,
                (
                    goal.description,
                    goal.state,
                    json.dumps(goal.milestones, ensure_ascii=False),
                    json.dumps(goal.completed_work, ensure_ascii=False),
                    json.dumps(goal.blockers, ensure_ascii=False),
                    goal.next_action,
                    goal.exit_condition,
                    json.dumps(
                        {
                            "max_attempts": goal.budget.max_attempts,
                            "max_failures": goal.budget.max_failures,
                            "max_tokens": goal.budget.max_tokens,
                            "max_seconds": goal.budget.max_seconds,
                        },
                        sort_keys=True,
                    ),
                    json.dumps(
                        goal.provenance,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    goal.updated_at,
                    goal.goal_id,
                ),
            )
            self._conn.commit()

    def list_all(self) -> tuple[GoalRecord, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM goals ORDER BY goal_id"
            ).fetchall()
        return tuple(_goal_from_row(row) for row in rows)

    def list_by_state(self, state: str) -> tuple[GoalRecord, ...]:
        if state not in GOAL_STATES:
            raise ValueError(f"unsupported goal state: {state}")
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM goals
                WHERE state=?
                ORDER BY updated_at, goal_id
                """,
                (state,),
            ).fetchall()
        return tuple(_goal_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteGoalPort":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _goal_values(goal: GoalRecord) -> tuple[object, ...]:
    return (
        goal.goal_id,
        goal.description,
        goal.state,
        json.dumps(goal.milestones, ensure_ascii=False),
        json.dumps(goal.completed_work, ensure_ascii=False),
        json.dumps(goal.blockers, ensure_ascii=False),
        goal.next_action,
        goal.exit_condition,
        json.dumps(
            {
                "max_attempts": goal.budget.max_attempts,
                "max_failures": goal.budget.max_failures,
                "max_tokens": goal.budget.max_tokens,
                "max_seconds": goal.budget.max_seconds,
            },
            sort_keys=True,
        ),
        json.dumps(goal.provenance, ensure_ascii=False, sort_keys=True),
        goal.created_at,
        goal.updated_at,
    )


def _goal_from_row(row: sqlite3.Row) -> GoalRecord:
    budget = json.loads(row["budget_json"])
    provenance = json.loads(row["provenance_json"])
    return GoalRecord(
        goal_id=row["goal_id"],
        description=row["description"],
        state=row["state"],
        milestones=tuple(json.loads(row["milestones_json"])),
        completed_work=tuple(json.loads(row["completed_work_json"])),
        blockers=tuple(json.loads(row["blockers_json"])),
        next_action=row["next_action"],
        exit_condition=row["exit_condition"],
        budget=GoalBudget(
            max_attempts=budget.get("max_attempts"),
            max_failures=budget.get("max_failures"),
            max_tokens=budget.get("max_tokens"),
            max_seconds=budget.get("max_seconds"),
        ),
        provenance=provenance if isinstance(provenance, dict) else {},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )
