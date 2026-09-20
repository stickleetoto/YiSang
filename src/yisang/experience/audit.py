from __future__ import annotations
import argparse,json
from .episode_sqlite import SQLiteExperiencePort

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="yisang-experience-audit")
    p.add_argument("--db",required=True); p.add_argument("--json",action="store_true",dest="as_json")
    a=p.parse_args(argv)
    with SQLiteExperiencePort(a.db) as port: episodes=port.list_episodes()
    payload={
      "episode_count":len(episodes),
      "success_count":sum(x.outcome=="success" for x in episodes),
      "failure_count":sum(x.outcome=="failure" for x in episodes),
      "promotable_evidence_count":sum(e.is_promotable for x in episodes for e in x.evidence),
      "episodes":[{
        "episode_id":x.episode_id,"outcome":x.outcome,"summary":x.summary,
        "request_id":x.request_id,"engine_id":x.engine_id,
        "verification_status":x.verification_status,
        "trigger_conditions":list(x.trigger_conditions),
        "procedure_steps":list(x.procedure_steps),
        "promotable_evidence":[e.evidence_ref for e in x.evidence if e.is_promotable],
      } for x in episodes],
    }
    if a.as_json: print(json.dumps(payload,ensure_ascii=False,indent=2))
    else:
      print(f"episodes={payload['episode_count']} success={payload['success_count']} failure={payload['failure_count']} promotable_evidence={payload['promotable_evidence_count']}")
      for x in payload["episodes"]: print(f"{x['episode_id']} {x['outcome']} engine={x['engine_id']} summary={x['summary']}")
    return 0

if __name__=="__main__": raise SystemExit(main())
