from __future__ import annotations

from .base import VerificationResult, Verifier


class CompositeVerifier(Verifier):
    """Run independent verifiers and fail if any verifier fails."""

    def __init__(self, verifiers: list[Verifier]) -> None:
        if not verifiers:
            raise ValueError("CompositeVerifier requires at least one verifier")
        self.verifiers = list(verifiers)

    def verify(self, *, request, engine_result) -> VerificationResult:
        reasons: list[str] = []
        for verifier in self.verifiers:
            result = verifier.verify(request=request, engine_result=engine_result)
            reasons.append(f"{type(verifier).__name__}:{result.reason}")
            if result.status != "PASS":
                return VerificationResult(result.status, ";".join(reasons))
        return VerificationResult("PASS", ";".join(reasons))
