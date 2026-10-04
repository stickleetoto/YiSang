from yisang.ego.smoke_v2 import main


def test_ego_v2_smoke(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"selected_version": "1.2.0"' in output
    assert '"metadata_only_before_activation": true' in output
    assert '"package_digest_bound_before_activation": true' in output
    assert '"full_loaded_after_activation": true' in output
    assert '"digest_stable_across_activation": true' in output
