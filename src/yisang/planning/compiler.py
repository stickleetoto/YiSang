from __future__ import annotations

from .models import GoalPlan, PlanProposal, PlanStep


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
            updated_at=proposal.created_at,
        )

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
