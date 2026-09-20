from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    LexicalLibraryRetriever,
)


def _port() -> InMemoryLibraryPort:
    return InMemoryLibraryPort(
        (
            Book(
                book_id="graph-algorithms",
                title="Graph Algorithms",
                version="1",
                description="Shortest path and traversal knowledge.",
                entries=(
                    KnowledgeEntry(
                        entry_id="dijkstra",
                        title="Heap Dijkstra",
                        summary=(
                            "Single-source shortest paths with non-negative "
                            "weighted edges."
                        ),
                        aliases=("shortest path",),
                        tags=("dijkstra", "heap", "graph"),
                        use_when=("edge weights are non-negative",),
                        avoid_when=("negative edge weights are possible",),
                        structure=("priority queue frontier",),
                    ),
                    KnowledgeEntry(
                        entry_id="bellman-ford",
                        title="Bellman-Ford",
                        summary=(
                            "Shortest paths with negative edge weights and "
                            "negative-cycle detection."
                        ),
                        aliases=("negative shortest path",),
                        tags=("bellman-ford", "graph", "negative-weights"),
                        use_when=("negative edge weights are possible",),
                        avoid_when=("a much faster constrained method applies",),
                        structure=("repeat edge relaxation",),
                    ),
                ),
            ),
            Book(
                book_id="python-engineering",
                title="Python Engineering",
                version="1",
                description="Reliable Python implementation patterns.",
                entries=(
                    KnowledgeEntry(
                        entry_id="atomic-replace",
                        title="Atomic file replacement",
                        summary="Write temp data and atomically replace the target.",
                        tags=("filesystem", "atomic", "reliability"),
                        use_when=("partial writes must not become visible",),
                        structure=("temporary file then replace",),
                    ),
                ),
            ),
        )
    )


def test_compact_index_limits_candidates_to_touched_entries() -> None:
    retriever = LexicalLibraryRetriever(_port())
    refs = retriever.index.candidate_refs({"dijkstra"})

    assert len(refs) == 1
    book, entry = retriever.index.materialize(refs[0])
    assert book.book_id == "graph-algorithms"
    assert entry.entry_id == "dijkstra"


def test_exact_algorithm_query_prefers_dijkstra() -> None:
    results = LexicalLibraryRetriever(_port()).search(
        "Dijkstra shortest path with a heap",
        limit=2,
    )

    assert results[0].entry.entry_id == "dijkstra"
    assert results[0].fit == "recommended"


def test_negative_weight_query_surfaces_bellman_ford_and_dijkstra_guardrail() -> None:
    results = LexicalLibraryRetriever(_port()).search(
        "shortest path with negative edge weights",
        limit=3,
    )

    by_id = {result.entry.entry_id: result for result in results}
    assert by_id["bellman-ford"].fit == "recommended"
    assert by_id["dijkstra"].fit in {"caution", "avoid"}
    assert "constraint conflict" in by_id["dijkstra"].reasons


def test_unrelated_query_returns_no_results() -> None:
    results = LexicalLibraryRetriever(_port()).search(
        "quantum chromodynamics lattice gauge"
    )

    assert results == ()


def test_rebuild_reflects_authoritative_library_changes() -> None:
    port = _port()
    retriever = LexicalLibraryRetriever(port)

    port.put_book(
        Book(
            book_id="concurrency",
            title="Concurrency",
            version="1",
            entries=(
                KnowledgeEntry(
                    entry_id="semaphore",
                    title="Bounded semaphore",
                    summary="Bound concurrent access to a scarce resource.",
                    tags=("semaphore", "concurrency"),
                    use_when=("parallel I/O must be bounded",),
                ),
            ),
        )
    )

    assert retriever.search("semaphore") == ()
    retriever.rebuild()
    assert retriever.search("semaphore")[0].entry.entry_id == "semaphore"


def test_compact_index_reports_derived_size() -> None:
    retriever = LexicalLibraryRetriever(_port())
    stats = retriever.index.stats()

    assert stats["books"] == 2
    assert stats["entries"] == 3
    assert stats["terms"] > 0
    assert stats["posting_refs"] >= stats["entries"]
