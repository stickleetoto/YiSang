from yisang.experience.trace_replay_smoke import main


def test_trace_replay_smoke(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"recorded_trace_count": 3' in output
    assert '"compiled_manifest_count": 3' in output
    assert '"executed_replay_count": 3' in output
    assert '"all_replays_passed": true' in output
    assert '"raw_action_arguments_stored": false' in output
    assert '"promotion_accepted": true' in output
