from __future__ import annotations

import json
from threading import Thread
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.server.http import create_http_server
from yisang.server.proxy import YiSangModelProxy
from yisang.server.rate_limit import LocalRateLimitError, RateLimitGovernor
from yisang.server.responses_upstream import OpenAIResponsesUpstream
from yisang.server.upstream import OpenAIChatUpstream, UpstreamHTTPError


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_governor_spaces_fast_request_starts():
    clock = FakeClock()
    governor = RateLimitGovernor(
        min_interval=2.0,
        backoff_initial=2.0,
        backoff_max=60.0,
        clock=clock,
        sleeper=clock.sleep,
    )

    governor.before_request()
    governor.before_request()
    governor.before_request()

    assert clock.sleeps == [2.0, 2.0]
    assert clock.now == 104.0


def test_governor_opens_exponential_cooldown_without_provider_retry():
    clock = FakeClock()
    governor = RateLimitGovernor(
        min_interval=0.0,
        backoff_initial=2.0,
        backoff_max=60.0,
        clock=clock,
        sleeper=clock.sleep,
    )

    assert governor.record_rate_limit() == 2.0
    with pytest.raises(LocalRateLimitError) as first:
        governor.before_request()
    assert first.value.retry_after == 2.0

    clock.advance(2.0)
    assert governor.record_rate_limit() == 4.0
    with pytest.raises(LocalRateLimitError) as second:
        governor.before_request()
    assert second.value.retry_after == 4.0

    clock.advance(4.0)
    governor.record_success()
    assert governor.snapshot().consecutive_rate_limits == 0


def test_provider_retry_after_extends_local_cooldown():
    clock = FakeClock()
    governor = RateLimitGovernor(
        min_interval=0.0,
        backoff_initial=2.0,
        backoff_max=60.0,
        clock=clock,
        sleeper=clock.sleep,
    )

    delay = governor.record_rate_limit(17.0)

    assert delay == 17.0
    assert governor.snapshot().blocked_for == 17.0


def test_responses_upstream_fails_locally_during_cooldown_before_network():
    clock = FakeClock()
    governor = RateLimitGovernor(
        min_interval=0.0,
        backoff_initial=2.0,
        backoff_max=60.0,
        clock=clock,
        sleeper=clock.sleep,
    )
    governor.record_rate_limit(9.0)
    upstream = OpenAIResponsesUpstream(
        base_url="http://127.0.0.1:1/v1",
        timeout=0.1,
        rate_limit_governor=governor,
    )

    with pytest.raises(UpstreamHTTPError) as raised:
        upstream.complete({"model": "gpt-6-luna", "input": "hello"})

    error = raised.value
    assert error.status == 429
    assert error.locally_blocked is True
    assert error.retry_after == 9.0


class RateLimitedNativeUpstream:
    def __init__(self, *, locally_blocked: bool = False) -> None:
        self.rate_limit_governor = None
        self.locally_blocked = locally_blocked
        self.calls = 0

    def complete(self, payload):
        self.calls += 1
        raise UpstreamHTTPError(
            429,
            '{"error":{"type":"rate_limit_error"}}',
            retry_after=7.2,
            locally_blocked=self.locally_blocked,
        )


def _native_server(responses_upstream):
    proxy = YiSangModelProxy(
        model_id="yisang-luna",
        upstream_model="gpt-6-luna",
        identity=IdentityCharter("yisang-model", "YiSang"),
        state=AgentState(active_engine="gpt-6-luna"),
        memory=InMemoryMemoryPort(),
        ego_registry=EgoRegistry(),
        context_compiler=ContextCompiler(),
    )
    chat = OpenAIChatUpstream(base_url="http://127.0.0.1:1/v1")
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        proxy=proxy,
        upstream=chat,
        responses_upstream=responses_upstream,
        tool_profile="full",
        reasoning_effort="xhigh",
        reasoning_mode="standard",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.mark.parametrize("locally_blocked", [False, True])
def test_http_preserves_upstream_429_retry_after(locally_blocked):
    upstream = RateLimitedNativeUpstream(locally_blocked=locally_blocked)
    server, thread = _native_server(upstream)
    try:
        body = json.dumps(
            {
                "model": "yisang-luna",
                "input": "hello",
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib_request.Request(
            f"http://127.0.0.1:{server.server_port}/v1/responses",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with pytest.raises(urllib_error.HTTPError) as raised:
            urllib_request.urlopen(request)

        error = raised.value
        decoded = json.loads(error.read())
        assert error.code == 429
        assert error.headers["Retry-After"] == "8"
        assert decoded["error"]["type"] == "upstream_rate_limited"
        assert decoded["error"]["code"] == "upstream_rate_limited"
        assert decoded["error"]["retry_after"] == 8
        assert decoded["error"]["locally_blocked"] is locally_blocked
        assert upstream.calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
