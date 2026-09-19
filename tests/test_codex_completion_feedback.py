from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.server.completion import (
    completion_feedback_message,
    summarize_tool_feedback,
)
from yisang.server.proxy import YiSangModelProxy
from yisang.server.responses import prepare_responses_request


def _proxy():
    return YiSangModelProxy(
        model_id="yisang-llama",
        upstream_model="llama3.2:3b",
        identity=IdentityCharter("yisang-model", "YiSang"),
        state=AgentState(active_engine="llama3.2:3b"),
        memory=InMemoryMemoryPort(),
        ego_registry=EgoRegistry(),
        context_compiler=ContextCompiler(),
    )


def test_explicit_success_tool_feedback_is_detected():
    summary = summarize_tool_feedback(
        {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": {
                        "content": "done",
                        "success": True,
                    },
                }
            ]
        }
    )

    assert summary.total == 1
    assert summary.explicit_successes == 1
    assert summary.has_success is True
    assert summary.has_failure is False
    message = completion_feedback_message(summary)
    assert "requested effect is already satisfied" in message
    assert "invent unrelated tools" in message


def test_explicit_failure_takes_precedence_over_success():
    summary = summarize_tool_feedback(
        {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "ok",
                    "output": {"content": "ok", "success": True},
                },
                {
                    "type": "function_call_output",
                    "call_id": "bad",
                    "output": {"content": "bad", "success": False},
                },
            ]
        }
    )

    assert summary.has_failure is True
    assert "Do not claim the task succeeded" in completion_feedback_message(summary)


def test_codex_console_success_can_be_inferred_from_text_output():
    summary = summarize_tool_feedback(
        {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "Process exited with code 0\nFinal output:\nok",
                }
            ]
        }
    )

    assert summary.inferred_successes == 1
    assert summary.has_success is True


def test_codex_small_request_injects_post_tool_completion_guidance():
    payload = {
        "model": "yisang-llama",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "Create result.txt and stop.",
            },
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "exec_command",
                "arguments": '{"cmd":"echo ok"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": {
                    "content": "Process exited with code 0",
                    "success": True,
                },
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "exec_command",
                "description": "run a command",
                "parameters": {
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"],
                },
            }
        ],
    }

    prepared = prepare_responses_request(
        _proxy(),
        payload,
        tool_profile="codex-small",
    )

    assert prepared.tool_feedback.explicit_successes == 1
    system_messages = [
        message["content"]
        for message in prepared.chat_payload["messages"]
        if message.get("role") == "system"
    ]
    assert any("YISANG TOOL FEEDBACK" in message for message in system_messages)
    assert any("do not invent unrelated skills" in message for message in system_messages)
