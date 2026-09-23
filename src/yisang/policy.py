from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Iterable


POLICY_EFFECTS = frozenset({"permit", "forbid"})


@dataclass(frozen=True)
class PolicyPrincipal:
    principal_type: str
    principal_id: str
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.principal_type.strip():
            raise ValueError("principal_type must be non-empty")
        if not self.principal_id.strip():
            raise ValueError("principal_id must be non-empty")


@dataclass(frozen=True)
class PolicyResource:
    resource_type: str
    resource_id: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError("resource_type must be non-empty")
        if not self.resource_id.strip():
            raise ValueError("resource_id must be non-empty")


@dataclass(frozen=True)
class AuthorizationRequest:
    principal: PolicyPrincipal
    action: str
    resource: PolicyResource
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("action must be non-empty")


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    effect: str
    principal_type: str = "*"
    principal: str = "*"
    action: str = "*"
    resource_type: str = "*"
    resource: str = "*"
    context_equals: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id must be non-empty")
        if self.effect not in POLICY_EFFECTS:
            raise ValueError(f"unsupported policy effect: {self.effect}")

    def matches(
        self,
        request: AuthorizationRequest,
        *,
        exposure_only: bool = False,
    ) -> bool:
        if not fnmatchcase(
            request.principal.principal_type,
            self.principal_type,
        ):
            return False
        if not fnmatchcase(request.principal.principal_id, self.principal):
            return False
        if not fnmatchcase(request.action, self.action):
            return False
        if not fnmatchcase(
            request.resource.resource_type,
            self.resource_type,
        ):
            return False
        if not exposure_only and not fnmatchcase(
            request.resource.resource_id,
            self.resource,
        ):
            return False
        for key, expected in self.context_equals.items():
            if request.context.get(key) != expected:
                return False
        return True


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    matched_rule_ids: tuple[str, ...] = ()


class AuthorizationPolicyEngine:
    """Small deny-by-default policy engine.

    The shape is intentionally principal/action/resource/context-oriented so a
    future Cedar/OPA adapter can implement the same boundary.
    """

    def __init__(self, rules: Iterable[PolicyRule] = ()) -> None:
        self._rules: list[PolicyRule] = []
        for rule in rules:
            self.add_rule(rule)

    def add_rule(self, rule: PolicyRule) -> None:
        if any(item.rule_id == rule.rule_id for item in self._rules):
            raise ValueError(f"duplicate policy rule id: {rule.rule_id}")
        self._rules.append(rule)

    def list_rules(self) -> tuple[PolicyRule, ...]:
        return tuple(self._rules)

    def evaluate(
        self,
        request: AuthorizationRequest,
        *,
        exposure_only: bool = False,
    ) -> PolicyDecision:
        matched = tuple(
            rule
            for rule in self._rules
            if rule.matches(request, exposure_only=exposure_only)
        )
        forbids = tuple(
            rule
            for rule in matched
            if rule.effect == "forbid"
            and (not exposure_only or rule.resource == "*")
        )
        if forbids:
            return PolicyDecision(
                allowed=False,
                reason="explicit_forbid",
                matched_rule_ids=tuple(rule.rule_id for rule in forbids),
            )

        permits = tuple(rule for rule in matched if rule.effect == "permit")
        if permits:
            return PolicyDecision(
                allowed=True,
                reason="explicit_permit",
                matched_rule_ids=tuple(rule.rule_id for rule in permits),
            )

        return PolicyDecision(
            allowed=False,
            reason="no_matching_permit",
            matched_rule_ids=(),
        )
