from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    LexicalLibraryRetriever,
    build_library_delivery,
    delivery_chars,
    stable_knowledge_ref,
)


def _results(query: str):
    port = InMemoryLibraryPort(
        (
            Book(
                book_id="graph-algorithms",
                title="Graph Algorithms",
                version="1",
                entries=(
                    KnowledgeEntry(
                        entry_id="dijkstra",
                        title="Heap Dijkstra",
                        summary=(
                            "Use a priority queue for shortest paths when "
                            "all edge weights are non-negative."
                        ),
                        aliases=("shortest path",),
                        tags=("dijkstra", "heap", "graph"),
                        use_when=("edge weights are non-negative",),
                        avoid_when=("negative edge weights are possible",),
                        structure=("distance table", "priority queue frontier"),
                        tradeoffs=("fast but requires non-negative weights",),
                        complexity={"time": "O((V+E) log V)"},
                        pitfalls=("negative weights invalidate the algorithm",),
                        implementation_hint="Skip stale heap entries.",
                        source_refs=("book://graph-algorithms",),
                        trust_class="curated",
                        validation_state="validated",
                    ),
                    KnowledgeEntry(
                        entry_id="bellman-ford",
                        title="Bellman-Ford",
                        summary=(
                            "Repeated edge relaxation supports negative "
                            "weights and negative-cycle detection."
                        ),
                        aliases=("negative shortest path",),
                        tags=("bellman-ford", "graph", "negative-weights"),
                        use_when=("negative edge weights are possible",),
                        avoid_when=("large constrained graphs need faster methods",),
                        structure=("repeat edge relaxation",),
                        tradeoffs=("more general but slower",),
                        complexity={"time": "O(VE)"},
                        pitfalls=("extra pass is needed for cycle detection",),
                        implementation_hint="Stop early when a pass changes nothing.",
                        source_refs=("book://graph-algorithms",),
                        trust_class="curated",
                        validation_state="validated",
                    ),
                ),
            ),
        )
    )
    return LexicalLibraryRetriever(port).search(query, limit=3)


def test_stable_knowledge_ref_is_deterministic() -> None:
    assert stable_knowledge_ref("book", "entry") == stable_knowledge_ref(
        "book",
        "entry",
    )
    assert stable_knowledge_ref("book", "entry").startswith("k_")


def test_delivery_includes_provenance_and_core_fields() -> None:
    payload = build_library_delivery(
        _results("Dijkstra shortest path"),
        request="Dijkstra shortest path",
    )

    first = payload[0]
    assert first["role"] == "primary"
    assert first["book_id"] == "graph-algorithms"
    assert first["source_refs"] == ["book://graph-algorithms"]
    assert first["trust_class"] == "curated"
    assert first["validation_state"] == "validated"
    assert "avoid_when" in first


def test_request_aware_fields_are_not_always_emitted() -> None:
    plain = build_library_delivery(
        _results("Dijkstra shortest path"),
        request="Dijkstra shortest path",
    )[0]
    implementation = build_library_delivery(
        _results("implement Dijkstra shortest path"),
        request="implement Dijkstra shortest path",
    )[0]
    performance = build_library_delivery(
        _results("Dijkstra shortest path performance"),
        request="Dijkstra shortest path performance",
    )[0]

    assert "implementation_hint" not in plain
    assert "complexity" not in plain
    assert "implementation_hint" in implementation
    assert "complexity" in performance


def test_negative_constraint_keeps_guardrail_delivery() -> None:
    payload = build_library_delivery(
        _results("shortest path with negative edge weights"),
        request="shortest path with negative edge weights",
        max_chars=1_400,
    )

    roles = {item["topic"]: item["role"] for item in payload}
    fits = {item["topic"]: item["fit"] for item in payload}

    assert roles["Bellman-Ford"] == "primary"
    assert roles["Heap Dijkstra"] == "guardrail"
    assert fits["Heap Dijkstra"] in {"caution", "avoid"}
    guardrail = next(
        item for item in payload if item["topic"] == "Heap Dijkstra"
    )
    assert "avoid_when" in guardrail


def test_budget_prunes_optional_detail_before_safety_boundary() -> None:
    payload = build_library_delivery(
        _results("implement shortest path with negative edge weights performance"),
        request=(
            "implement shortest path with negative edge weights "
            "performance and tradeoffs"
        ),
        max_chars=1_050,
    )

    assert delivery_chars(payload) <= 1_050
    topics = {item["topic"] for item in payload}
    assert "Bellman-Ford" in topics
    assert "Heap Dijkstra" in topics
    guardrail = next(
        item for item in payload if item["topic"] == "Heap Dijkstra"
    )
    assert "avoid_when" in guardrail



def test_severe_budget_prefers_guardrail_over_primary() -> None:
    payload = build_library_delivery(
        _results("implement shortest path with negative edge weights performance"),
        request=(
            "implement shortest path with negative edge weights "
            "performance and tradeoffs"
        ),
        max_chars=650,
    )

    assert delivery_chars(payload) <= 650
    guardrails = [item for item in payload if item["role"] == "guardrail"]
    assert guardrails
    assert "avoid_when" in guardrails[0]

    if len(payload) == 1:
        assert payload[0]["role"] == "guardrail"
