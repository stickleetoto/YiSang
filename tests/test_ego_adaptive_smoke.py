from yisang.ego.adaptive_smoke import main


def test_ego_adaptive_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"min_samples": 3' in output
    assert '"replay_health_weighted": true' in output
    assert '"bounded_adjustment": true' in output
    assert '"ego.stable"' in output
