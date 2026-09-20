from __future__ import annotations

import argparse
import json

from .continuity import evaluate_v06_closeout, load_continuity_report
from .library_benchmark import (
    evaluate_v06_library_benchmark,
    load_library_scale_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-v06-closeout",
        description=(
            "Validate YiSang v0.6 closeout evidence from continuity and "
            "Roland Library scale reports."
        ),
    )
    parser.add_argument("--continuity", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--min-repeats", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    continuity = load_continuity_report(args.continuity)
    library = load_library_scale_report(args.library)

    continuity_check = evaluate_v06_closeout(
        continuity,
        min_repeats=args.min_repeats,
    )
    library_check = evaluate_v06_library_benchmark(library)

    errors = tuple(
        dict.fromkeys(
            [
                *(f"continuity: {error}" for error in continuity_check.errors),
                *(f"library: {error}" for error in library_check.errors),
            ]
        )
    )
    ready = not errors

    payload = {
        "ready": ready,
        "errors": list(errors),
        "continuity": {
            "ready": continuity_check.ready,
            "case_count": len(continuity.cases),
            "pass_rate": continuity.pass_rate,
            "metadata": dict(continuity.metadata),
        },
        "library": {
            "ready": library_check.ready,
            "all_passed": library.all_passed,
            "scales": [
                {
                    "book_count": item.book_count,
                    "selection_accuracy": item.selection_accuracy,
                    "p95_search_ms": item.p95_search_ms,
                    "mean_delivery_chars": item.mean_delivery_chars,
                }
                for item in library.results
            ],
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
