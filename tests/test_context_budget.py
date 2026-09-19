from yisang.context.budget import ContextBudgetPolicy
from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.identity.models import IdentityCharter, AgentState
from yisang.memory.models import MemoryRecord
from yisang.ego.models import EgoManifest

def test_context_budget_limits_payload():
    compiler = ContextCompiler(ContextBudgetPolicy(
        max_total_chars=900,
        max_user_chars=300,
        max_memory_chars=300,
        max_ego_chars=200,
        max_memories=2,
        max_egos=1,
    ))

    memories = [
        MemoryRecord(f"m{i}", "semantic", "memory " + ("x" * 500), "test", 1.0)
        for i in range(5)
    ]
    egos = [
        EgoManifest(
            ego_id=f"ego.{i}",
            name=f"E{i}",
            provides=("x",),
            keywords=("x",),
            instructions="instruction " + ("y" * 500),
        )
        for i in range(3)
    ]

    pack = compiler.compile(
        request=YiSangRequest("r", "z" * 1000),
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="test"),
        memories=memories,
        egos=egos,
    )

    assert len(pack.memories) <= 2
    assert len(pack.egos) <= 1
    assert pack.approx_chars() <= 900
