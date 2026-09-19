import json

from yisang.server.responses import _normalize_tool_arguments


def test_optional_textual_null_tool_argument_is_omitted():
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "string"},
            "max_output_tokens": {"type": "number"},
        },
        "required": ["cmd"],
        "additionalProperties": False,
    }
    arguments = json.dumps(
        {
            "cmd": "Get-Content test.txt",
            "max_output_tokens": "null",
        }
    )

    normalized = json.loads(_normalize_tool_arguments(arguments, schema))

    assert normalized == {"cmd": "Get-Content test.txt"}


def test_optional_textual_none_tool_argument_is_omitted():
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "string"},
            "yield_time_ms": {"type": "number"},
        },
        "required": ["cmd"],
    }

    normalized = json.loads(
        _normalize_tool_arguments(
            '{"cmd":"echo ok","yield_time_ms":"None"}',
            schema,
        )
    )

    assert normalized == {"cmd": "echo ok"}


def test_required_textual_null_is_not_silently_removed():
    schema = {
        "type": "object",
        "properties": {"limit": {"type": "number"}},
        "required": ["limit"],
    }

    normalized = json.loads(
        _normalize_tool_arguments('{"limit":"null"}', schema)
    )

    assert normalized == {"limit": "null"}
