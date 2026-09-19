from yisang.context.budget import ContextBudgetPolicy
from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.ego.models import EgoManifest
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.models import MemoryRecord


def test_compile_with_report_tracks_selected_and_dropped_inputs():
    compiler = ContextCompiler(
        ContextBudgetPolicy(
            max_total_chars=4000,
            max_user_chars=100,
            max_memory_chars=1000,
            max_ego_chars=500,
            max_tool_chars=500,
            max_action_history_chars=500,
            max_memories=2,
            max_egos=1,
            max_tools=1,
            max_action_history=1,
        )
    )
    memories = [
        MemoryRecord(
            f"m{i}",
            "semantic",
            f"memory-{i}",
            "test",
            1.0,
        )
        for i in range(4)
    ]
    egos = [
        EgoManifest(
            ego_id=f"ego.{i}",
            name=f"E{i}",
            provides=("x",),
            keywords=("x",),
        )
        for i in range(2)
    ]

    compiled = compiler.compile_with_report(
        request=YiSangRequest("r", "hello"),
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="test"),
        memories=memories,
        egos=egos,
        tools=[
            {"tool_id": "a", "description": "a"},
            {"tool_id": "b", "description": "b"},
        ],
        action_history=[
            {"step": 1},
            {"step": 2},
        ],
    )

    report = compiled.budget
    assert report.selected_memories == 2
    assert report.dropped_memories == 2
    assert report.selected_egos == 1
    assert report.dropped_egos == 1
    assert report.selected_tools == 1
    assert report.dropped_tools == 1
    assert report.selected_action_history == 1
    assert report.dropped_action_history == 1
    assert report.within_budget is True


def test_compile_legacy_api_returns_same_pack_shape():
    compiler = ContextCompiler()
    kwargs = dict(
        request=YiSangRequest("r", "hello"),
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="test"),
        memories=[],
        egos=[],
    )

    direct = compiler.compile(**kwargs)
    compiled = compiler.compile_with_report(**kwargs)

    assert direct.to_dict() == compiled.pack.to_dict()


def test_budget_report_detects_user_truncation():
    compiler = ContextCompiler(
        ContextBudgetPolicy(
            max_total_chars=2000,
            max_user_chars=10,
            max_memory_chars=500,
            max_ego_chars=500,
            max_tool_chars=500,
            max_action_history_chars=500,
            max_memories=1,
            max_egos=1,
            max_tools=1,
            max_action_history=1,
        )
    )

    compiled = compiler.compile_with_report(
        request=YiSangRequest("r", "x" * 100),
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="test"),
        memories=[],
        egos=[],
    )

    assert compiled.budget.user_truncated is True
    assert compiled.budget.user_chars <= 10
    assert compiled.budget.total_chars == compiled.pack.approx_chars()
