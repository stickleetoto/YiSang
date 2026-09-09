from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str = ""

class Verifier(ABC):
    @abstractmethod
    def verify(self, *, request, engine_result) -> VerificationResult:
        raise NotImplementedError

class PassThroughVerifier(Verifier):
    def verify(self, *, request, engine_result) -> VerificationResult:
        if not engine_result.text.strip():
            return VerificationResult("FAIL", "empty_output")
        return VerificationResult("PASS", "non_empty_output")
