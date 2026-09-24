from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock

from .models import GoalPlan, PlanStep
from .port import PlanPort


class SQLitePlanPort(PlanPort):
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
                CREATE TABLE IF NOT EXISTS plan_revisions (
                    plan_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    goal_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (plan_id, revision)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_plan_goal_latest
                ON plan_revisions(goal_id, updated_at)
                """
            )
            self._conn.commit()

    def append(self, plan: GoalPlan) -> None:
        with self._lock:
            latest = self._conn.execute(
                """
                SELECT * FROM plan_revisions
                WHERE plan_id=?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (plan.plan_id,),
            ).fetchone()
            if latest is None:
                if plan.revision != 1:
                    raise ValueError("first plan revision must be 1")
            else:
                previous = _from_row(latest)
                if plan.goal_id != previous.goal_id:
                    raise ValueError("plan goal_id is immutable")
                if plan.created_at != previous.created_at:
                    raise ValueError("plan created_at is immutable")
                if plan.revision != previous.revision + 1:
                    raise ValueError(
                        "plan revisions must be sequential"
                    )
            try:
                self._conn.execute(
                    """
                    INSERT INTO plan_revisions (
                        plan_id, revision, goal_id, state, steps_json,
                        provenance_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.plan_id,
                        plan.revision,
                        plan.goal_id,
                        plan.state,
                        json.dumps(
                            [_step_to_dict(step) for step in plan.steps],
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        json.dumps(
                            plan.provenance,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        plan.created_at,
                        plan.updated_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate plan revision: "
                    f"{plan.plan_id}@{plan.revision}"
                ) from exc
            self._conn.commit()

    def latest(self, plan_id: str) -> GoalPlan | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM plan_revisions
                WHERE plan_id=?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (plan_id,),
            ).fetchone()
        return None if row is None else _from_row(row)

    def history(self, plan_id: str) -> tuple[GoalPlan, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM plan_revisions
                WHERE plan_id=?
                ORDER BY revision
                """,
                (plan_id,),
            ).fetchall()
        return tuple(_from_row(row) for row in rows)

    def latest_for_goal(self, goal_id: str) -> GoalPlan | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM plan_revisions
                WHERE goal_id=?
                ORDER BY updated_at DESC, revision DESC
                LIMIT 1
                """,
                (goal_id,),
            ).fetchone()
        return None if row is None else _from_row(row)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLitePlanPort":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _step_to_dict(step: PlanStep) -> dict:
    return {
        "step_id": step.step_id,
        "title": step.title,
        "description": step.description,
        "ordinal": step.ordinal,
        "depends_on": list(step.depends_on),
        "required_capabilities": list(step.required_capabilities),
        "verification": step.verification,
        "max_attempts": step.max_attempts,
        "priority": step.priority,
        "state": step.state,
        "attempt_count": step.attempt_count,
        "result_ref": step.result_ref,
        "evidence_refs": list(step.evidence_refs),
        "blocker": step.blocker,
        "last_error": step.last_error,
        "run_id": step.run_id,
    }


def _step_from_dict(raw: dict) -> PlanStep:
    return PlanStep(
        step_id=str(raw["step_id"]),
        title=str(raw["title"]),
        description=str(raw.get("description", "")),
        ordinal=int(raw["ordinal"]),
        depends_on=tuple(str(x) for x in raw.get("depends_on", [])),
        required_capabilities=tuple(
            str(x) for x in raw.get("required_capabilities", [])
        ),
        verification=str(raw.get("verification", "")),
        max_attempts=int(raw.get("max_attempts", 1)),
        priority=int(raw.get("priority", 0)),
        state=str(raw.get("state", "pending")),
        attempt_count=int(raw.get("attempt_count", 0)),
        result_ref=raw.get("result_ref"),
        evidence_refs=tuple(str(x) for x in raw.get("evidence_refs", [])),
        blocker=raw.get("blocker"),
        last_error=raw.get("last_error"),
        run_id=raw.get("run_id"),
    )


def _from_row(row: sqlite3.Row) -> GoalPlan:
    provenance = json.loads(row["provenance_json"])
    raw_steps = json.loads(row["steps_json"])
    return GoalPlan(
        plan_id=row["plan_id"],
        goal_id=row["goal_id"],
        revision=int(row["revision"]),
        state=row["state"],
        steps=tuple(_step_from_dict(item) for item in raw_steps),
        provenance=provenance if isinstance(provenance, dict) else {},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )
