from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import GymTaskSpec
from .runner import check_run, prepare_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-gym",
        description="Prepare and verify isolated YiSang development practice tasks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List task specs under a task root.")
    list_parser.add_argument("--task-root", default="gym/tasks")

    prepare_parser = sub.add_parser("prepare", help="Create an isolated task run.")
    prepare_parser.add_argument("--task", required=True)
    prepare_parser.add_argument("--task-root", default="gym/tasks")
    prepare_parser.add_argument("--runs-root", default=".gym/runs")

    check_parser = sub.add_parser("check", help="Verify a prepared task run.")
    check_parser.add_argument("--run", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "list":
        root = Path(args.task_root)
        rows = []
        if root.exists():
            for spec_path in sorted(root.glob("*/task.json")):
                task = GymTaskSpec.from_file(spec_path)
                rows.append(
                    {
                        "id": task.task_id,
                        "title": task.title,
                        "difficulty": task.difficulty,
                    }
                )
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if args.command == "prepare":
        task_dir = Path(args.task_root) / args.task
        run = prepare_run(task_dir, runs_root=args.runs_root)
        print(
            json.dumps(
                {
                    "task_id": run.task.task_id,
                    "run_dir": str(run.run_dir),
                    "workspace": str(run.workspace),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "check":
        result = check_run(args.run)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if result.ready else 1

    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
