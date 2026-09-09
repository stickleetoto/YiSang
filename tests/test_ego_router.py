from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter

def test_routes_relevant_ego():
    registry = EgoRegistry()
    registry.register(EgoManifest(
        ego_id="ego.python.debug",
        name="Python Debugger",
        provides=("python_debugging",),
        keywords=("python", "pytest"),
    ))
    registry.register(EgoManifest(
        ego_id="ego.git",
        name="Git",
        provides=("git",),
        keywords=("git", "commit"),
    ))

    found = CapabilityRouter().route("python pytest failure", registry.list_all())
    assert [e.ego_id for e in found] == ["ego.python.debug"]
