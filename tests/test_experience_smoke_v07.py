from yisang.experience.audit import main as audit_main
from yisang.experience.smoke import main as smoke_main

def test_experience_smoke_cli_and_audit(tmp_path,capsys):
    db=tmp_path/"smoke.db"
    assert smoke_main(["--db",str(db)])==0
    out=capsys.readouterr().out
    assert '"ready": true' in out and '"raw_request_stored": false' in out
    assert audit_main(["--db",str(db),"--json"])==0
    out=capsys.readouterr().out
    assert '"episode_count": 1' in out and '"success_count": 1' in out
