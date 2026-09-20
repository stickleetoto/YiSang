from yisang.experience import ExperienceEpisode,ExperienceEvidence,SQLiteExperiencePort

def test_sqlite_experience_round_trip(tmp_path):
    db=tmp_path/"experience.db"
    e=ExperienceEpisode(episode_id="episode-1",outcome="success",summary="verified",evidence=(ExperienceEvidence("tool:1","tool_result","ok",True),),trigger_conditions=("write",),procedure_steps=("tool:write",),request_id="r1",engine_id="e",verification_status="PASS",metadata={"request_sha256":"abc"})
    with SQLiteExperiencePort(db) as p: p.put_episode(e)
    with SQLiteExperiencePort(db) as p:
        assert p.get_episode("episode-1")==e
        assert p.list_episodes()==(e,)
