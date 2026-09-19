from yisang.engines.openai_compatible import OpenAICompatibleEngine
from yisang.context.models import ContextPack

def make_pack():
    return ContextPack(
        request_id="r",
        agent_id="yisang-001",
        user_text="hello",
        identity={"name": "YiSang", "principles": ["verify"]},
        state={"active_engine": "local"},
        memories=[],
        egos=[],
        constraints=[],
    )

def test_openai_compatible_engine_builds_request():
    seen = {}

    def fake_transport(url, headers, payload, timeout):
        seen.update({
            "url": url,
            "headers": headers,
            "payload": payload,
            "timeout": timeout,
        })
        return {
            "model": "qwen",
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"prompt_tokens": 12},
        }

    engine = OpenAICompatibleEngine(
        engine_id="local",
        base_url="http://127.0.0.1:1234/v1/",
        model="qwen",
        transport=fake_transport,
    )

    result = engine.generate(make_pack())
    assert result.text == "answer"
    assert result.engine_id == "local"
    assert seen["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert seen["payload"]["model"] == "qwen"
    assert "YiSang" in seen["payload"]["messages"][1]["content"]

def test_openai_compatible_engine_rejects_bad_response():
    def bad_transport(url, headers, payload, timeout):
        return {"choices": []}

    engine = OpenAICompatibleEngine(
        engine_id="local",
        base_url="http://localhost/v1",
        model="qwen",
        transport=bad_transport,
    )

    try:
        engine.generate(make_pack())
    except ValueError as exc:
        assert "response shape" in str(exc)
    else:
        raise AssertionError("bad response was accepted")


def test_openai_compatible_engine_includes_max_tokens_when_bounded():
    seen = {}

    def fake_transport(url, headers, payload, timeout):
        seen["payload"] = payload
        return {
            "model": "llama",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }

    engine = OpenAICompatibleEngine(
        engine_id="local",
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.2:3b",
        max_tokens=64,
        transport=fake_transport,
    )

    engine.generate(make_pack())

    assert seen["payload"]["max_tokens"] == 64
