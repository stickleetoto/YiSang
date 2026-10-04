from yisang.ego.promotion_smoke import main


def test_ego_promotion_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"active_after_second_apply": "0.0.2"' in output
    assert '"routed_version": "0.0.2"' in output
    assert '"rollback_target": "0.0.1"' in output
    assert '"active_after_rollback": "0.0.1"' in output
    assert '"package_digest_bound": true' in output
