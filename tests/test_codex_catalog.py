import json

import pytest

from yisang.integrations.codex import (
    DEFAULT_CODEX_CONTEXT_WINDOW,
    build_codex_model_catalog,
    build_codex_model_info,
    main,
    write_codex_model_catalog,
)


def test_codex_model_info_matches_v0154_shape():
    info = build_codex_model_info("yisang-llama", context_window=4096)

    assert info["slug"] == "yisang-llama"
    assert info["shell_type"] == "unified_exec"
    assert info["visibility"] == "none"
    assert info["supported_in_api"] is True
    assert info["context_window"] == 4096
    assert info["max_context_window"] == 4096
    assert info["input_modalities"] == ["text"]
    assert info["supported_reasoning_levels"] == []
    assert info["include_skills_usage_instructions"] is False
    assert info["include_plugin_usage_instructions"] is False
    assert info["include_apps_usage_instructions"] is False
    assert info["truncation_policy"] == {"mode": "bytes", "limit": 10_000}
    assert "Never invent tool" in info["base_instructions"]
    assert "verified" in info["base_instructions"]


def test_codex_catalog_rejects_invalid_values():
    with pytest.raises(ValueError, match="model_id"):
        build_codex_model_info("   ")
    with pytest.raises(ValueError, match="context_window"):
        build_codex_model_info("yisang-llama", context_window=0)


def test_codex_catalog_default_window_is_local_model_safe_default():
    catalog = build_codex_model_catalog("yisang-llama")
    assert catalog["models"][0]["context_window"] == DEFAULT_CODEX_CONTEXT_WINDOW


def test_write_codex_catalog(tmp_path):
    output = tmp_path / "codex" / "models.json"
    result = write_codex_model_catalog(
        output,
        "yisang-llama",
        context_window=8192,
    )

    assert result == output
    decoded = json.loads(output.read_text(encoding="utf-8"))
    assert decoded["models"][0]["slug"] == "yisang-llama"
    assert decoded["models"][0]["context_window"] == 8192


def test_codex_catalog_cli_writes_file(tmp_path, capsys):
    output = tmp_path / "models.json"
    status = main(
        [
            "--model",
            "yisang-llama",
            "--context-window",
            "4096",
            "--output",
            str(output),
        ]
    )

    assert status == 0
    assert output.exists()
    assert str(output) in capsys.readouterr().out
