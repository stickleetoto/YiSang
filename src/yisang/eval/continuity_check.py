from __future__ import annotations

import argparse
import json

from .continuity import evaluate_v05_closeout, load_continuity_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-continuity-check",
        description="Validate a saved YiSang v0.5 continuity report for closeout.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--min-repeats", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = load_continuity_report(args.input)
    check = evaluate_v05_closeout(
        report,
        min_repeats=args.min_repeats,
    )
    payload = {
        "ready": check.ready,
        "errors": list(check.errors),
        "case_count": len(report.cases),
        "pass_rate": report.pass_rate,
        "metadata": dict(report.metadata),
        "summary": report.to_dict()["summary"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if check.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
