from __future__ import annotations

from abc import ABC, abstractmethod
from math import isfinite, sqrt
from threading import RLock
from typing import Any
from urllib import request as urllib_request
import json

from .models import MemoryRecord
from .projection import MemoryHit, MemoryProjection


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise NotImplementedError


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """Minimal OpenAI-compatible embeddings client.

    This is an adapter only. YiSang Core does not depend on a particular
    embedding vendor or local runtime.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must be non-empty")
        if not model.strip():
            raise ValueError("model must be non-empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []

        payload = {
            "model": self.model,
            "input": texts,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib_request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=self.timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))

        data = raw.get("data")
        if not isinstance(data, list):
            raise ValueError("embedding response data must be a list")

        ordered = sorted(
            data,
            key=lambda item: int(item.get("index", 0))
            if isinstance(item, dict)
            else 0,
        )
        vectors: list[tuple[float, ...]] = []
        for item in ordered:
            if not isinstance(item, dict):
                raise ValueError("embedding item must be an object")
            vector = item.get("embedding")
            if not isinstance(vector, list):
                raise ValueError("embedding must be a list")
            vectors.append(_validated_vector(vector))

        if len(vectors) != len(texts):
            raise ValueError("embedding response count mismatch")
        _validate_same_dimension(vectors)
        return vectors


class InMemoryVectorProjection(MemoryProjection):
    """Rebuildable cosine-similarity projection.

    Vectors are secondary data only. The authoritative MemoryPort remains the
    source of record content, provenance, trust, and lifecycle state.
    """

    projection_id = "vector-cosine-v1"

    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        min_similarity: float = -1.0,
        batch_size: int = 32,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not -1.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between -1 and 1")
        self.provider = provider
        self.min_similarity = min_similarity
        self.batch_size = batch_size
        self._lock = RLock()
        self._vectors: dict[str, tuple[float, ...]] = {}
        self._dimension: int | None = None

    def rebuild(self, records: list[MemoryRecord]) -> None:
        eligible = [
            record
            for record in records
            if not record.invalidated and record.is_durable
        ]
        replacement: dict[str, tuple[float, ...]] = {}
        dimension: int | None = None

        for start in range(0, len(eligible), self.batch_size):
            batch = eligible[start:start + self.batch_size]
            vectors = self.provider.embed([record.content for record in batch])
            if len(vectors) != len(batch):
                raise ValueError("embedding provider returned wrong vector count")
            _validate_same_dimension(vectors)
            for record, vector in zip(batch, vectors):
                if dimension is None:
                    dimension = len(vector)
                elif len(vector) != dimension:
                    raise ValueError("embedding dimension changed during rebuild")
                replacement[record.memory_id] = vector

        with self._lock:
            self._vectors = replacement
            self._dimension = dimension

    def upsert(self, record: MemoryRecord) -> None:
        if record.invalidated or not record.is_durable:
            self.remove(record.memory_id)
            return

        vectors = self.provider.embed([record.content])
        if len(vectors) != 1:
            raise ValueError("embedding provider returned wrong vector count")
        vector = vectors[0]

        with self._lock:
            if self._dimension is None:
                self._dimension = len(vector)
            elif len(vector) != self._dimension:
                raise ValueError(
                    f"embedding dimension mismatch: expected {self._dimension}, "
                    f"got {len(vector)}"
                )
            self._vectors[record.memory_id] = vector

    def remove(self, memory_id: str) -> None:
        with self._lock:
            self._vectors.pop(memory_id, None)
            if not self._vectors:
                self._dimension = None

    def search(self, query: str, *, limit: int = 8) -> list[MemoryHit]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0 or not query.strip():
            return []

        vectors = self.provider.embed([query])
        if len(vectors) != 1:
            raise ValueError("embedding provider returned wrong vector count")
        query_vector = vectors[0]

        with self._lock:
            if self._dimension is None:
                return []
            if len(query_vector) != self._dimension:
                raise ValueError(
                    f"query embedding dimension mismatch: expected "
                    f"{self._dimension}, got {len(query_vector)}"
                )
            ranked = []
            for memory_id, vector in self._vectors.items():
                similarity = _cosine_similarity(query_vector, vector)
                if similarity < self.min_similarity:
                    continue
                ranked.append((similarity, memory_id))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            MemoryHit(
                memory_id=memory_id,
                score=similarity,
                projection=self.projection_id,
            )
            for similarity, memory_id in ranked[:limit]
        ]

    def size(self) -> int:
        with self._lock:
            return len(self._vectors)

    @property
    def dimension(self) -> int | None:
        with self._lock:
            return self._dimension


def _validated_vector(raw: list[Any] | tuple[Any, ...]) -> tuple[float, ...]:
    if not raw:
        raise ValueError("embedding vector must be non-empty")
    vector = tuple(float(value) for value in raw)
    if any(not isfinite(value) for value in vector):
        raise ValueError("embedding vector contains non-finite values")
    return vector


def _validate_same_dimension(vectors: list[tuple[float, ...]]) -> None:
    if not vectors:
        return
    dimension = len(vectors[0])
    if dimension <= 0:
        raise ValueError("embedding dimension must be positive")
    for vector in vectors:
        if len(vector) != dimension:
            raise ValueError("embedding vectors must have the same dimension")


def _cosine_similarity(
    left: tuple[float, ...],
    right: tuple[float, ...],
) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions do not match")

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
