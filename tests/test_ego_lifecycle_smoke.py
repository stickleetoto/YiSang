from yisang.ego.lifecycle_smoke import main


def test_ego_lifecycle_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"pending_candidate_does_not_disable": true' in output
    assert '"rejected_candidate_keeps_active": true' in output
    assert '"approved_candidate_disables": true' in output
    assert '"rollback_version": "0.0.1"' in output
