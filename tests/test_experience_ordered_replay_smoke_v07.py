from yisang.experience.ordered_replay_smoke import main


def test_ordered_replay_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"sequence_count": 3' in output
    assert '"steps_per_sequence": [' in output
    assert '"shared_workspace_proven": true' in output
    assert '"fail_fast": true' in output
    assert '"promotion_accepted": true' in output
