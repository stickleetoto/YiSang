from __future__ import annotations

from dataclasses import replace
import time

from .models import (
    GoalPlan,
    PlanProposal,
    PlanRevisionProposal,
    PlanStep,
    PlanStepSpec,
)


class PlanCompileError(ValueError):
    pass


class PlanCompiler:
    """Validate a proposed step graph and compile revision 1."""

    def compile(
        self,
        proposal: PlanProposal,
        *,
        provenance: dict | None = None,
    ) -> GoalPlan:
        specs = proposal.steps
        self._validate_specs(specs)

        compiled = tuple(
            PlanStep(
                step_id=step.step_id,
                title=step.title,
                description=step.description,
                ordinal=index,
                depends_on=step.depends_on,
                required_capabilities=step.required_capabilities,
                verification=step.verification,
                max_attempts=step.max_attempts,
                priority=step.priority,
            )
            for index, step in enumerate(specs)
        )
        merged_provenance = dict(proposal.provenance)
        merged_provenance.update(
            {
                "proposal_id": proposal.proposal_id,
                "proposed_by": proposal.proposed_by,
            }
        )
        merged_provenance.update(dict(provenance or {}))
        return GoalPlan(
            plan_id=proposal.plan_id,
            goal_id=proposal.goal_id,
            revision=1,
            state="active",
            steps=compiled,
            provenance=merged_provenance,
            created_at=proposal.created_at,
            updated_at=max(time.time(), current.updated_at),
        )

    def compile_revision(
        self,
        current: GoalPlan,
        proposal: PlanRevisionProposal,
        *,
        provenance: dict | None = None,
    ) -> GoalPlan:
        if proposal.plan_id != current.plan_id:
            raise PlanCompileError("revision proposal plan_id mismatch")
        if proposal.goal_id != current.goal_id:
            raise PlanCompileError("revision proposal goal_id mismatch")
        if proposal.base_revision != current.revision:
            raise PlanCompileError(
                f"stale revision proposal: expected base {current.revision}, "
                f"got {proposal.base_revision}"
            )
        if current.terminal:
            raise PlanCompileError("terminal plan cannot be replanned")
        if any(step.state == "running" for step in current.steps):
            raise PlanCompileError(
                "running steps must be recovered or resolved before replan"
            )

        specs = proposal.steps
        self._validate_specs(specs)
        current_by_id = {
            step.step_id: step
            for step in current.steps
        }
        proposed_by_id = {
            step.step_id: step
            for step in specs
        }

        for old in current.steps:
            if old.state == "completed":
                new_spec = proposed_by_id.get(old.step_id)
                if new_spec is None:
                    raise PlanCompileError(
                        f"completed step cannot be removed: {old.step_id}"
                    )
                if not _spec_matches_step(new_spec, old):
                    raise PlanCompileError(
                        f"completed step cannot be changed: {old.step_id}"
                    )

        compiled: list[PlanStep] = []
        for index, spec in enumerate(specs):
            previous = current_by_id.get(spec.step_id)
            if previous is None:
                compiled.append(
                    PlanStep(
                        step_id=spec.step_id,
                        title=spec.title,
                        description=spec.description,
                        ordinal=index,
                        depends_on=spec.depends_on,
                        required_capabilities=spec.required_capabilities,
                        verification=spec.verification,
                        max_attempts=spec.max_attempts,
                        priority=spec.priority,
                    )
                )
                continue

            if not _spec_matches_step(spec, previous):
                raise PlanCompileError(
                    f"existing step id cannot change meaning: {spec.step_id}; "
                    "use a new step_id"
                )
            compiled.append(
                replace(
                    previous,
                    ordinal=index,
                )
            )

        if all(step.state == "completed" for step in compiled):
            state = "completed"
        elif any(
            step.state in {"failed", "blocked"}
            for step in compiled
        ):
            state = "blocked"
        else:
            state = "active"

        merged = dict(current.provenance)
        history = list(merged.get("replan_history", []))
        history.append(
            {
                "revision_proposal_id": proposal.revision_proposal_id,
                "base_revision": proposal.base_revision,
                "proposed_by": proposal.proposed_by,
                "proposal_reason": proposal.reason,
                **dict(provenance or {}),
            }
        )
        merged["replan_history"] = history
        merged.update(dict(proposal.provenance))

        return GoalPlan(
            plan_id=current.plan_id,
            goal_id=current.goal_id,
            revision=current.revision + 1,
            state=state,
            steps=tuple(compiled),
            provenance=merged,
            created_at=current.created_at,
            updated_at=proposal.created_at,
        )

    def _validate_specs(self, specs) -> None:
        ids = tuple(step.step_id for step in specs)
        if len(set(ids)) != len(ids):
            raise PlanCompileError("plan proposal contains duplicate step ids")
        known = set(ids)
        for step in specs:
            missing = tuple(dep for dep in step.depends_on if dep not in known)
            if missing:
                raise PlanCompileError(
                    f"step {step.step_id} depends on missing steps: {missing}"
                )
        self._assert_acyclic(specs)

    def _assert_acyclic(self, specs) -> None:
        deps = {
            step.step_id: tuple(step.depends_on)
            for step in specs
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                raise PlanCompileError(
                    f"plan contains dependency cycle at {step_id}"
                )
            visiting.add(step_id)
            for dep in deps[step_id]:
                visit(dep)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in deps:
            visit(step_id)



def _spec_matches_step(spec: PlanStepSpec, step: PlanStep) -> bool:
    return (
        spec.step_id == step.step_id
        and spec.title == step.title
        and spec.description == step.description
        and spec.depends_on == step.depends_on
        and spec.required_capabilities == step.required_capabilities
        and spec.verification == step.verification
        and spec.max_attempts == step.max_attempts
        and spec.priority == step.priority
    )
