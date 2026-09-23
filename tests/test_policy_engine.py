from yisang.policy import (
    AuthorizationPolicyEngine,
    AuthorizationRequest,
    PolicyPrincipal,
    PolicyResource,
    PolicyRule,
)


def _request(resource="README.md", *, side_effecting=False):
    return AuthorizationRequest(
        principal=PolicyPrincipal("ego", "ego.repo", version="1.0.0"),
        action="filesystem.read",
        resource=PolicyResource("workspace_path", resource),
        context={"side_effecting": side_effecting},
    )


def test_policy_is_deny_by_default():
    decision = AuthorizationPolicyEngine().evaluate(_request())
    assert decision.allowed is False
    assert decision.reason == "no_matching_permit"


def test_policy_permit_matches_principal_action_resource_and_context():
    engine = AuthorizationPolicyEngine(
        [
            PolicyRule(
                "permit-docs",
                "permit",
                principal="ego.repo",
                action="filesystem.read",
                resource_type="workspace_path",
                resource="docs/*",
                context_equals={"side_effecting": False},
            )
        ]
    )
    decision = engine.evaluate(_request("docs/EXECUTION.md"))
    assert decision.allowed is True
    assert decision.matched_rule_ids == ("permit-docs",)


def test_explicit_forbid_overrides_permit():
    engine = AuthorizationPolicyEngine(
        [
            PolicyRule(
                "permit-workspace",
                "permit",
                principal="ego.repo",
                action="filesystem.read",
                resource_type="workspace_path",
                resource="*",
            ),
            PolicyRule(
                "forbid-secrets",
                "forbid",
                principal="ego.repo",
                action="filesystem.read",
                resource_type="workspace_path",
                resource="secrets/*",
            ),
        ]
    )
    decision = engine.evaluate(_request("secrets/token.txt"))
    assert decision.allowed is False
    assert decision.reason == "explicit_forbid"
    assert decision.matched_rule_ids == ("forbid-secrets",)


def test_exposure_check_ignores_specific_resource_but_not_action():
    engine = AuthorizationPolicyEngine(
        [
            PolicyRule(
                "permit-docs",
                "permit",
                principal="ego.repo",
                action="filesystem.read",
                resource_type="workspace_path",
                resource="docs/*",
            )
        ]
    )
    request = _request("*")
    assert engine.evaluate(request, exposure_only=True).allowed is True
