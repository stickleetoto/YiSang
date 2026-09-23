from yisang.policy_smoke import main


def test_policy_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"deny_by_default": true' in output
    assert '"risk_hints_grant_authority": false' in output
    assert '"explicit_forbid_reason": "policy_denied"' in output
    assert '"unmatched_resource_reason": "policy_no_permit"' in output
