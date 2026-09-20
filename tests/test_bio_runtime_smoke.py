from yisang.integrations.bio.runtime_smoke import main


def test_bio_runtime_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"memory_provider_id": "bio"' in output
    assert '"memory_context_ref": "ctx-runtime-smoke"' in output
    assert '"write_status": "pending"' in output
    assert '"direct_bio_approval": false' in output
