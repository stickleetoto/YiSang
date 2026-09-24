from yisang.recovery.workspace_smoke import main


def test_workspace_recovery_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"directive_before_reconcile": "reconcile_side_effect"' in output
    assert '"inspection_status": "matches_expected"' in output
    assert '"receipt_state_after_reconcile": "committed"' in output
    assert '"duplicate_execution_skipped": true' in output
