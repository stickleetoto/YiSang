from yisang.memory.models import MemoryProposal
from yisang.memory.sqlite import SQLiteMemoryPort

def test_sqlite_memory_survives_reopen(tmp_path):
    path = tmp_path / "memory.db"

    first = SQLiteMemoryPort(path)
    first.commit(MemoryProposal(
        content="YiSang memory survives engine replacement",
        source_engine="test",
        confidence=0.9,
        evidence=["unit-test"],
    ))
    first.close()

    second = SQLiteMemoryPort(path)
    records = second.all()
    assert len(records) == 1
    assert records[0].content == "YiSang memory survives engine replacement"
    second.close()

def test_sqlite_search_is_deterministic(tmp_path):
    memory = SQLiteMemoryPort(tmp_path / "memory.db")
    memory.commit(MemoryProposal(
        content="python pytest debugger",
        source_engine="a",
        confidence=0.8,
        evidence=["x"],
    ))
    memory.commit(MemoryProposal(
        content="python repository",
        source_engine="b",
        confidence=1.0,
        evidence=["y"],
    ))

    found = memory.search("python pytest")
    assert found[0].content == "python pytest debugger"
    memory.close()

def test_empty_query_returns_nothing(tmp_path):
    memory = SQLiteMemoryPort(tmp_path / "memory.db")
    memory.commit(MemoryProposal(
        content="some durable memory",
        evidence=["seed"],
        confidence=1.0,
    ))
    assert memory.search("   ") == []
    memory.close()
