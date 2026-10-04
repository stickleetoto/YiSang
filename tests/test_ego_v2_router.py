from yisang.ego.models import EgoManifest
from yisang.ego.router_v2 import HybridCapabilityRouter


def _ego(ego_id, description, *, tags=(), provides=(), keywords=(), examples=()):
    return EgoManifest(
        ego_id=ego_id,
        name=ego_id,
        provides=provides,
        keywords=keywords,
        schema_version=2,
        version="1.0.0",
        description=description,
        tags=tags,
        examples=examples,
        detail_level="metadata",
    )


def test_hybrid_router_uses_description_tags_and_examples():
    debug = _ego(
        "ego.debug",
        "Diagnose Python traceback and test failures",
        tags=("debugging", "pytest"),
        provides=("python.debug",),
        examples=("pytest가 실패해",),
    )
    git = _ego(
        "ego.git",
        "Manage Git commits and branches",
        tags=("git",),
        provides=("git.commit",),
    )

    found = HybridCapabilityRouter().route(
        "python pytest traceback failure",
        [git, debug],
    )

    assert [item.ego_id for item in found] == ["ego.debug"]


def test_hybrid_router_can_require_capability():
    debug = _ego(
        "ego.debug",
        "Python debugging",
        provides=("python.debug",),
    )
    repair = _ego(
        "ego.repair",
        "Python repair",
        provides=("python.debug", "python.test.repair"),
    )

    found = HybridCapabilityRouter().route(
        "",
        [debug, repair],
        required_capabilities=("python.test.repair",),
    )

    assert [item.ego_id for item in found] == ["ego.repair"]


def test_success_prior_only_breaks_relevant_metadata_ties():
    first = _ego("ego.a", "python debugging", tags=("python",))
    second = _ego("ego.b", "python debugging", tags=("python",))

    ranked = HybridCapabilityRouter().route(
        "python debugging",
        [first, second],
        success_scores={"ego.b": 0.9, "ego.a": 0.1},
    )

    assert [item.ego_id for item in ranked] == ["ego.b", "ego.a"]
