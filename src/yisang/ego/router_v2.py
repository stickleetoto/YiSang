from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .models import EgoManifest


_TOKEN_RE = re.compile(r"[A-Za-z0-9_+.-]+|[가-힣]+")


@dataclass(frozen=True)
class EgoRouteScore:
    ego: EgoManifest
    score: float
    reasons: tuple[str, ...]


class HybridCapabilityRouter:
    """Deterministic metadata router suitable for progressive E.G.O loading.

    This is intentionally embedding-free in v2 foundation. It combines
    keyword phrase matches, token overlap across tags/provides/description/
    examples, explicit required capabilities, and optional historical success
    priors.
    """

    def rank(
        self,
        query: str,
        egos: list[EgoManifest],
        *,
        required_capabilities: tuple[str, ...] = (),
        success_scores: Mapping[str, float] | None = None,
    ) -> list[EgoRouteScore]:
        query_folded = query.casefold()
        query_tokens = _tokens(query)
        required = set(required_capabilities)
        priors = success_scores or {}
        ranked: list[EgoRouteScore] = []

        for ego in egos:
            provides = set(ego.provides)
            if required and not required.issubset(provides):
                continue

            score = 0.0
            reasons: list[str] = []

            keyword_hits = sum(
                1
                for keyword in ego.keywords
                if keyword.casefold() in query_folded
            )
            if keyword_hits:
                score += keyword_hits * 4.0
                reasons.append(f"keyword:{keyword_hits}")

            tag_hits = len(query_tokens & _tokens(" ".join(ego.tags)))
            if tag_hits:
                score += tag_hits * 3.0
                reasons.append(f"tag:{tag_hits}")

            capability_hits = len(
                query_tokens & _tokens(" ".join(ego.provides))
            )
            if capability_hits:
                score += capability_hits * 3.0
                reasons.append(f"provides:{capability_hits}")

            description_hits = len(
                query_tokens & _tokens(ego.description)
            )
            if description_hits:
                score += description_hits * 1.5
                reasons.append(f"description:{description_hits}")

            example_hits = sum(
                min(
                    2,
                    len(query_tokens & _tokens(example)),
                )
                for example in ego.examples
            )
            if example_hits:
                score += example_hits * 0.75
                reasons.append(f"example:{example_hits}")

            if required:
                score += len(required) * 6.0
                reasons.append(f"required:{len(required)}")

            prior = max(0.0, min(1.0, float(priors.get(ego.ego_id, 0.0))))
            if prior:
                score += prior * 2.0
                reasons.append(f"success_prior:{prior:.3f}")

            if score > 0:
                ranked.append(
                    EgoRouteScore(
                        ego=ego,
                        score=score,
                        reasons=tuple(reasons),
                    )
                )

        ranked.sort(
            key=lambda item: (
                -item.score,
                item.ego.ego_id,
                item.ego.version,
            )
        )
        return ranked

    def route(
        self,
        query: str,
        egos: list[EgoManifest],
        *,
        limit: int = 3,
        required_capabilities: tuple[str, ...] = (),
        success_scores: Mapping[str, float] | None = None,
    ) -> list[EgoManifest]:
        if limit <= 0:
            return []
        return [
            item.ego
            for item in self.rank(
                query,
                egos,
                required_capabilities=required_capabilities,
                success_scores=success_scores,
            )[:limit]
        ]


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(value)
        if token.strip()
    }
