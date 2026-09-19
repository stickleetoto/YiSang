from threading import Thread

from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.session.in_memory import InMemorySessionPort
from yisang.session.sqlite import SQLiteSessionPort


def _exercise_basic_session_port(port):
    first = port.append(
        "s1",
        role="user",
        content="hello",
        metadata={"source": "test"},
    )
    second = port.append(
        "s1",
        role="assistant",
        content="hi",
    )
    port.append("s2", role="user", content="other")

    assert first.sequence == 1
    assert second.sequence == 2
    assert [item.content for item in port.history("s1")] == ["hello", "hi"]
    assert [item.content for item in port.history("s1", limit=1)] == ["hi"]
    assert port.session_ids() == ["s1", "s2"]
    assert port.clear("s2") == 1
    assert port.session_ids() == ["s1"]


def test_in_memory_session_port():
    _exercise_basic_session_port(InMemorySessionPort())


def test_sqlite_session_port_survives_reopen(tmp_path):
    path = tmp_path / "sessions.db"
    first = SQLiteSessionPort(path)
    _exercise_basic_session_port(first)
    first.close()

    second = SQLiteSessionPort(path)
    history = second.history("s1")

    assert [item.sequence for item in history] == [1, 2]
    assert history[0].metadata == {"source": "test"}
    assert [item.content for item in history] == ["hello", "hi"]
    second.close()


def test_session_storage_does_not_create_durable_memory():
    sessions = InMemorySessionPort()
    memory = InMemoryMemoryPort()

    sessions.append(
        "s1",
        role="user",
        content="remember this forever",
    )

    assert len(sessions.history("s1")) == 1
    assert memory.all() == []


def test_sqlite_session_append_is_thread_safe(tmp_path):
    port = SQLiteSessionPort(tmp_path / "sessions.db")
    errors = []

    def worker(index):
        try:
            port.append(
                "shared",
                role="user",
                content=f"message-{index}",
            )
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [Thread(target=worker, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    history = port.history("shared")
    assert len(history) == 10
    assert [item.sequence for item in history] == list(range(1, 11))
    port.close()


def test_session_history_rejects_negative_limit():
    port = InMemorySessionPort()
    port.append("s", role="user", content="x")

    try:
        port.history("s", limit=-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
