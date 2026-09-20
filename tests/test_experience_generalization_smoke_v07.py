from yisang.experience.generalization_smoke import main


def test_generalization_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"source_episode_count": 3' in output
    assert '"replay_case_count": 3' in output
    assert '"promotion_accepted": true' in output
    assert '"simulated_replay_results": true' in output
