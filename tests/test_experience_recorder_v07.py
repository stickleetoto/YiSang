from yisang.execution.models import ActionResult
from yisang.experience import ExperienceRecorder

def test_recorder_does_not_copy_raw_request_text():
    raw="SECRET RAW REQUEST SHOULD NOT BE STORED"
    e=ExperienceRecorder().capture(request_id="r1",request_text=raw,request_metadata={},engine_id="e",verification_status="PASS",verification_reason="ok",action_results=[],memories=[],library_payload=())
    assert raw not in e.summary and raw not in repr(e.metadata)
    assert e.metadata["request_sha256"] and e.outcome=="success"

def test_goal_satisfied_tool_result_is_promotable_evidence():
    e=ExperienceRecorder().capture(request_id="r2",request_text="write",request_metadata={},engine_id="e",verification_status="PASS",verification_reason="ok",action_results=[ActionResult(tool_id="write_file",status="EXECUTED",goal_satisfied=True)],memories=[],library_payload=())
    assert e.procedure_steps==("tool:write_file",)
    p=[x for x in e.evidence if x.is_promotable]
    assert len(p)==1 and p[0].source_type=="tool_result"

def test_unverified_tool_result_is_not_promotable():
    e=ExperienceRecorder().capture(request_id="r3",request_text="run",request_metadata={},engine_id="e",verification_status="PASS",verification_reason="ok",action_results=[ActionResult(tool_id="exec",status="EXECUTED",goal_satisfied=False)],memories=[],library_payload=())
    t=[x for x in e.evidence if x.source_type=="tool_result"]
    assert len(t)==1 and not t[0].is_promotable

def test_failed_action_marks_episode_failed():
    e=ExperienceRecorder().capture(request_id="r4",request_text="run",request_metadata={},engine_id="e",verification_status="PASS",verification_reason="ok",action_results=[ActionResult(tool_id="exec",status="ERROR")],memories=[],library_payload=())
    assert e.outcome=="failure"
