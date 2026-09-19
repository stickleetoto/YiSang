import pytest

from yisang.context.models import ContextPack
from yisang.engines.openai_compatible import OpenAICompatibleEngine
from yisang.engines.structured import StructuredActionDecoder


def _pack():
    return ContextPack(
        request_id="r",
        agent_id="yisang-001",
        user_text="read README",
        identity={"name": "YiSang", "principles": ["verify"]},
        state={"active_engine": "local"},
        memories=[],
        egos=[],
        tools=[
            {
                "tool_id": "workspace.read_text",
                "description": "read a workspace text file",
                "argument_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
    )


def test_decoder_accepts_provider_neutral_action_envelope():
    decoded = StructuredActionDecoder().decode(
        {
            "content": (
                '{"response":"checking","actions":['
                '{"tool":"workspace.read_text","arguments":{"path":"README.md"}}]}'
            )
        },
        requested_by="local",
    )
    assert decoded.text == "checking"
    assert decoded.actions[0].action == "workspace.read_text"
    assert decoded.actions[0].arguments == {"path": "README.md"}
    assert decoded.actions[0].requested_by == "local"


def test_decoder_accepts_native_tool_calls():
    decoded = StructuredActionDecoder().decode(
        {
            "content": None,
            "tool_calls": [
                {
                    "function": {
                        "name": "workspace.read_text",
                        "arguments": '{"path":"README.md"}',
                    }
                }
            ],
        },
        requested_by="local",
    )
    assert decoded.text == ""
    assert decoded.actions[0].action == "workspace.read_text"


def test_decoder_rejects_malformed_action_entries():
    with pytest.raises(ValueError):
        StructuredActionDecoder().decode(
            {"content": '{"response":"x","actions":[{"tool":"","arguments":{}}]}'},
            requested_by="local",
        )


def test_openai_compatible_engine_decodes_actions_and_surfaces_protocol():
    seen = {}

    def fake_transport(url, headers, payload, timeout):
        seen["payload"] = payload
        return {
            "model": "qwen",
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"response":"checking","actions":['
                            '{"tool":"workspace.read_text","arguments":{"path":"README.md"}}]}'
                        )
                    }
                }
            ],
        }

    engine = OpenAICompatibleEngine(
        engine_id="local",
        base_url="http://127.0.0.1:1234/v1",
        model="qwen",
        transport=fake_transport,
    )
    result = engine.generate(_pack())

    assert result.text == "checking"
    assert result.action_proposals[0].action == "workspace.read_text"
    assert engine.supports_action_feedback is True
    assert "ACTION PROTOCOL" in seen["payload"]["messages"][1]["content"]
