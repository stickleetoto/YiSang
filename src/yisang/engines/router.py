from .base import LLMEngine

class EngineRouter:
    def __init__(self) -> None:
        self._engines: dict[str, LLMEngine] = {}

    def register(self, engine: LLMEngine) -> None:
        if engine.engine_id in self._engines:
            raise ValueError(f"duplicate engine: {engine.engine_id}")
        self._engines[engine.engine_id] = engine

    def get(self, engine_id: str) -> LLMEngine:
        try:
            return self._engines[engine_id]
        except KeyError as exc:
            raise KeyError(f"engine not registered: {engine_id}") from exc
