from __future__ import annotations

import json
import subprocess
import sys

from log_inspector import analyze_lines


def test_analyze_lines_counts_levels_and_repeated_errors():
    result = analyze_lines(
        [
            "INFO boot\n",
            "WARNING disk warm\n",
            "ERROR database unavailable\n",
            "ERROR database unavailable\n",
            "ERROR timeout\n",
            "DEBUG ignored\n",
        ]
    )

    assert result == {
        "counts": {"INFO": 1, "WARNING": 1, "ERROR": 3},
        "repeated_errors": [
            {"message": "database unavailable", "count": 2},
        ],
    }


def test_analyze_lines_accepts_prefix_metadata_and_sorts_repeats():
    result = analyze_lines(
        [
            "2026-10-05T10:00:00 INFO ready\n",
            "[worker-1] ERROR zeta\n",
            "[worker-2] ERROR alpha\n",
            "[worker-3] ERROR zeta\n",
            "[worker-4] ERROR alpha\n",
        ]
    )

    assert result["counts"] == {"INFO": 1, "WARNING": 0, "ERROR": 4}
    assert result["repeated_errors"] == [
        {"message": "alpha", "count": 2},
        {"message": "zeta", "count": 2},
    ]


def test_cli_json_output(tmp_path):
    path = tmp_path / "sample.log"
    path.write_text(
        "INFO start\nERROR boom\nERROR boom\nWARNING hot\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "log_inspector.py", str(path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "counts": {"INFO": 1, "WARNING": 1, "ERROR": 2},
        "repeated_errors": [{"message": "boom", "count": 2}],
    }


def test_cli_human_output(tmp_path):
    path = tmp_path / "sample.log"
    path.write_text("INFO start\nERROR boom\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "log_inspector.py", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "INFO: 1" in completed.stdout
    assert "WARNING: 0" in completed.stdout
    assert "ERROR: 1" in completed.stdout
    assert "Repeated errors: none" in completed.stdout
