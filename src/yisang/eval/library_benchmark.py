from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import perf_counter
from typing import Iterable

from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    LexicalLibraryRetriever,
    build_library_delivery,
    delivery_chars,
)


DEFAULT_LIBRARY_SCALES = (10, 50, 100, 500)


@dataclass(frozen=True)
class LibraryScaleResult:
    book_count: int
    entry_count: int
    query_count: int
    correct_top1: int
    selection_accuracy: float
    index_build_ms: float
    mean_search_ms: float
    p95_search_ms: float
    mean_delivery_chars: float
    index_terms: int
    posting_refs: int

    @property
    def passed(self) -> bool:
        return self.query_count > 0 and self.selection_accuracy == 1.0


@dataclass(frozen=True)
class LibraryScaleReport:
    schema_version: int
    results: tuple[LibraryScaleResult, ...]

    @property
    def all_passed(self) -> bool:
        return bool(self.results) and all(item.passed for item in self.results)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "all_passed": self.all_passed,
            "scales": [asdict(item) | {"passed": item.passed} for item in self.results],
        }


@dataclass(frozen=True)
class LibraryBenchmarkCheck:
    ready: bool
    errors: tuple[str, ...]


def load_library_scale_report(path: str | Path) -> LibraryScaleReport:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Library scale report is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("Library scale report root must be an object")
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported Library scale report schema")

    raw_scales = raw.get("scales")
    if not isinstance(raw_scales, list):
        raise ValueError("Library scale report scales must be a list")

    results: list[LibraryScaleResult] = []
    for item in raw_scales:
        if not isinstance(item, dict):
            raise ValueError("Library scale result must be an object")
        try:
            results.append(
                LibraryScaleResult(
                    book_count=int(item["book_count"]),
                    entry_count=int(item["entry_count"]),
                    query_count=int(item["query_count"]),
                    correct_top1=int(item["correct_top1"]),
                    selection_accuracy=float(item["selection_accuracy"]),
                    index_build_ms=float(item["index_build_ms"]),
                    mean_search_ms=float(item["mean_search_ms"]),
                    p95_search_ms=float(item["p95_search_ms"]),
                    mean_delivery_chars=float(item["mean_delivery_chars"]),
                    index_terms=int(item["index_terms"]),
                    posting_refs=int(item["posting_refs"]),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"Library scale result missing field: {exc.args[0]}"
            ) from exc

    return LibraryScaleReport(
        schema_version=1,
        results=tuple(results),
    )


def evaluate_v06_library_benchmark(
    report: LibraryScaleReport,
    *,
    required_scales: tuple[int, ...] = DEFAULT_LIBRARY_SCALES,
    min_selection_accuracy: float = 1.0,
    max_mean_delivery_chars: float = 4_000.0,
) -> LibraryBenchmarkCheck:
    errors: list[str] = []
    by_scale = {item.book_count: item for item in report.results}

    for scale in required_scales:
        if scale not in by_scale:
            errors.append(f"missing required Library scale: {scale}")

    for item in report.results:
        prefix = f"{item.book_count} books"
        if item.query_count <= 0:
            errors.append(f"{prefix}: query_count must be positive")
        if item.correct_top1 > item.query_count:
            errors.append(f"{prefix}: correct_top1 exceeds query_count")
        if item.selection_accuracy < min_selection_accuracy:
            errors.append(
                f"{prefix}: selection_accuracy "
                f"{item.selection_accuracy:.6f} is below "
                f"{min_selection_accuracy:.6f}"
            )
        if item.index_build_ms < 0:
            errors.append(f"{prefix}: index_build_ms is negative")
        if item.mean_search_ms < 0 or item.p95_search_ms < 0:
            errors.append(f"{prefix}: search latency is negative")
        if item.mean_delivery_chars <= 0:
            errors.append(f"{prefix}: mean_delivery_chars must be positive")
        if item.mean_delivery_chars > max_mean_delivery_chars:
            errors.append(
                f"{prefix}: mean_delivery_chars exceeds "
                f"{max_mean_delivery_chars:.0f}"
            )
        if item.index_terms <= 0 or item.posting_refs <= 0:
            errors.append(f"{prefix}: index statistics are empty")

    if not report.results:
        errors.append("Library scale report contains no results")

    return LibraryBenchmarkCheck(
        ready=not errors,
        errors=tuple(dict.fromkeys(errors)),
    )


def build_synthetic_library(book_count: int) -> InMemoryLibraryPort:
    if book_count <= 0:
        raise ValueError("book_count must be positive")

    books = []
    for index in range(book_count):
        token = f"topic_{index}"
        books.append(
            Book(
                book_id=f"book-{index:04d}",
                title=f"Synthetic Book {index}",
                version="1",
                description=f"Benchmark knowledge for {token}.",
                entries=(
                    KnowledgeEntry(
                        entry_id=f"entry-{index:04d}",
                        title=f"Technique {index}",
                        summary=(
                            f"{token} is the deterministic benchmark technique "
                            f"for synthetic case {index}."
                        ),
                        aliases=(token,),
                        tags=(token, "benchmark"),
                        use_when=(f"query asks for {token}",),
                        avoid_when=(f"query explicitly excludes {token}",),
                        source_refs=(f"synthetic://book-{index:04d}",),
                        trust_class="benchmark",
                        validation_state="validated",
                    ),
                ),
                source_refs=(f"synthetic://book-{index:04d}",),
                trust_class="benchmark",
                validation_state="validated",
            )
        )
    return InMemoryLibraryPort(tuple(books))


def run_library_scale(
    book_count: int,
    *,
    max_queries: int = 50,
) -> LibraryScaleResult:
    if max_queries <= 0:
        raise ValueError("max_queries must be positive")

    port = build_synthetic_library(book_count)

    started = perf_counter()
    retriever = LexicalLibraryRetriever(port)
    index_build_ms = (perf_counter() - started) * 1000.0

    indices = _probe_indices(book_count, max_queries=max_queries)
    search_latencies: list[float] = []
    delivery_sizes: list[int] = []
    correct = 0

    for index in indices:
        query = f"topic_{index}"
        search_started = perf_counter()
        results = retriever.search(query, limit=3)
        search_latencies.append((perf_counter() - search_started) * 1000.0)

        expected_book = f"book-{index:04d}"
        expected_entry = f"entry-{index:04d}"
        if (
            results
            and results[0].book.book_id == expected_book
            and results[0].entry.entry_id == expected_entry
        ):
            correct += 1

        payload = build_library_delivery(
            results,
            request=query,
            max_chars=4_000,
        )
        delivery_sizes.append(delivery_chars(payload))

    stats = retriever.index.stats()
    query_count = len(indices)
    return LibraryScaleResult(
        book_count=book_count,
        entry_count=stats["entries"],
        query_count=query_count,
        correct_top1=correct,
        selection_accuracy=(correct / query_count if query_count else 0.0),
        index_build_ms=index_build_ms,
        mean_search_ms=_mean(search_latencies),
        p95_search_ms=_percentile(search_latencies, 0.95),
        mean_delivery_chars=_mean([float(value) for value in delivery_sizes]),
        index_terms=stats["terms"],
        posting_refs=stats["posting_refs"],
    )


def run_library_scale_benchmark(
    scales: Iterable[int] = DEFAULT_LIBRARY_SCALES,
    *,
    max_queries: int = 50,
) -> LibraryScaleReport:
    normalized = tuple(int(value) for value in scales)
    if not normalized:
        raise ValueError("at least one scale is required")
    if any(value <= 0 for value in normalized):
        raise ValueError("library scales must be positive")

    return LibraryScaleReport(
        schema_version=1,
        results=tuple(
            run_library_scale(scale, max_queries=max_queries)
            for scale in normalized
        ),
    )


def write_library_scale_report(
    path: str | Path,
    report: LibraryScaleReport,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-library",
        description=(
            "Run deterministic YiSang v0.6 Roland retrieval scale benchmarks."
        ),
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--scale",
        action="append",
        type=int,
        dest="scales",
        help="Book count to benchmark; may be repeated. Defaults to 10/50/100/500.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=50,
        help="Maximum deterministic probe queries per scale.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scales = tuple(args.scales) if args.scales else DEFAULT_LIBRARY_SCALES
    report = run_library_scale_benchmark(
        scales,
        max_queries=args.max_queries,
    )
    output = write_library_scale_report(args.output, report)
    print(output)
    print(
        json.dumps(
            {
                "all_passed": report.all_passed,
                "scales": [
                    {
                        "book_count": item.book_count,
                        "selection_accuracy": item.selection_accuracy,
                        "index_build_ms": item.index_build_ms,
                        "mean_search_ms": item.mean_search_ms,
                        "p95_search_ms": item.p95_search_ms,
                        "mean_delivery_chars": item.mean_delivery_chars,
                    }
                    for item in report.results
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.all_passed else 1


def _probe_indices(book_count: int, *, max_queries: int) -> tuple[int, ...]:
    query_count = min(book_count, max_queries)
    if query_count == book_count:
        return tuple(range(book_count))
    if query_count == 1:
        return (0,)

    step = (book_count - 1) / (query_count - 1)
    return tuple(
        sorted(
            {
                min(book_count - 1, round(index * step))
                for index in range(query_count)
            }
        )
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(
            len(ordered) - 1,
            int((len(ordered) - 1) * fraction),
        ),
    )
    return ordered[index]


if __name__ == "__main__":
    raise SystemExit(main())
