from yisang.integrations.bio.smoke import main


def test_bio_adapter_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"provider": "bio"' in output
    assert '"real_bio_used": false' in output
    assert '"write_status": "pending"' in output
    assert '"approval_calls": 0' in output
