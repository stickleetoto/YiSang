from __future__ import annotations

import argparse
import json

from .continuity import (
    evaluate_v05_closeout,
    evaluate_v06_closeout,
    load_continuity_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-continuity-check",
        description="Validate a saved YiSang continuity report for closeout.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--min-repeats", type=int, default=3)
    parser.add_argument(
        "--phase",
        choices=("auto", "v0.5", "v0.6"),
        default="auto",
        help="Validation gate. auto selects v0.6 when library_probe evidence is present.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = load_continuity_report(args.input)
    phase = args.phase
    if phase == "auto":
        phase = "v0.6" if report.metadata.get("library_probe") is True else "v0.5"

    evaluator = (
        evaluate_v06_closeout
        if phase == "v0.6"
        else evaluate_v05_closeout
    )
    check = evaluator(
        report,
        min_repeats=args.min_repeats,
    )
    payload = {
        "ready": check.ready,
        "errors": list(check.errors),
        "case_count": len(report.cases),
        "pass_rate": report.pass_rate,
        "phase": phase,
        "metadata": dict(report.metadata),
        "summary": report.to_dict()["summary"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if check.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
