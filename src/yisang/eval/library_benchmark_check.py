from __future__ import annotations

import argparse
import json

from .library_benchmark import (
    DEFAULT_LIBRARY_SCALES,
    evaluate_v06_library_benchmark,
    load_library_scale_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-library-check",
        description="Validate a saved YiSang v0.6 Roland scale report.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--required-scale",
        action="append",
        type=int,
        dest="required_scales",
        help="Required Book count; may be repeated. Defaults to 10/50/100/500.",
    )
    parser.add_argument(
        "--min-selection-accuracy",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--max-mean-delivery-chars",
        type=float,
        default=4_000.0,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    required_scales = (
        tuple(args.required_scales)
        if args.required_scales
        else DEFAULT_LIBRARY_SCALES
    )
    report = load_library_scale_report(args.input)
    check = evaluate_v06_library_benchmark(
        report,
        required_scales=required_scales,
        min_selection_accuracy=args.min_selection_accuracy,
        max_mean_delivery_chars=args.max_mean_delivery_chars,
    )
    payload = {
        "ready": check.ready,
        "errors": list(check.errors),
        "required_scales": list(required_scales),
        "all_passed": report.all_passed,
        "scales": [
            {
                "book_count": item.book_count,
                "selection_accuracy": item.selection_accuracy,
                "index_build_ms": item.index_build_ms,
                "mean_search_ms": item.mean_search_ms,
                "p95_search_ms": item.p95_search_ms,
                "mean_delivery_chars": item.mean_delivery_chars,
            }
            for item in report.results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if check.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
