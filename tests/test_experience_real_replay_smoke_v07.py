from yisang.experience.real_replay_smoke import main


def test_real_replay_smoke(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"executed_subprocess_replays": 3' in output
    assert '"all_replays_passed": true' in output
    assert '"evidence_refs_present": true' in output
    assert '"shell_used": false' in output
    assert '"promotion_accepted": true' in output
