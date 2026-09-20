from yisang.evaluation.bio.smoke import main


def test_bio_ab_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"real_bio_used": false' in output
    assert '"scenario_count": 3' in output
    assert '"provider_id": "native"' in output
    assert '"provider_id": "bio"' in output
    assert '"ranking_produced": false' in output
