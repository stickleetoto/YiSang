from __future__ import annotations

import importlib
from typing import Any, Callable, Protocol


class BioClientConfigurationError(RuntimeError):
    pass


class BioMemoryClient(Protocol):
    def search(
        self,
        query: str,
        *,
        project: str | None,
        namespace: str | None,
        limit: int,
    ) -> dict[str, Any]: ...

    def propose(self, **payload: Any) -> dict[str, Any]: ...

    def current_state(
        self,
        *,
        project: str | None,
        namespace: str | None,
        topic_key: str,
    ) -> dict[str, Any]: ...

    def context_pack(
        self,
        query: str,
        *,
        project: str | None,
        namespace: str | None,
        limit: int,
        char_budget: int,
    ) -> dict[str, Any]: ...


class BioBridgeClientAdapter:
    """Duck-typed adapter for BIO's BioMemoryBridge."""

    def __init__(
        self,
        bridge: Any,
        *,
        context_options_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.bridge = bridge
        self.context_options_factory = context_options_factory

    def search(
        self,
        query: str,
        *,
        project: str | None,
        namespace: str | None,
        limit: int,
    ) -> dict[str, Any]:
        return self.bridge.search_memory_with_graph(
            query,
            project=project,
            namespace=namespace,
            limit=limit,
        )

    def propose(self, **payload: Any) -> dict[str, Any]:
        return self.bridge.propose_memory_write(**payload)

    def current_state(
        self,
        *,
        project: str | None,
        namespace: str | None,
        topic_key: str,
    ) -> dict[str, Any]:
        return self.bridge.resolve_current_state(
            project=project,
            namespace=namespace,
            topic_key=topic_key,
        )

    def context_pack(
        self,
        query: str,
        *,
        project: str | None,
        namespace: str | None,
        limit: int,
        char_budget: int,
    ) -> dict[str, Any]:
        factory = self.context_options_factory or self._discover_options_factory()
        options = factory(
            project=project,
            namespace=namespace,
            limit=limit,
            char_budget=char_budget,
        )
        return self.bridge.build_context_pack(query, options=options)

    def _discover_options_factory(self) -> Callable[..., Any]:
        module_name = type(self.bridge).__module__
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise BioClientConfigurationError(
                "cannot import BIO bridge module for ContextPackOptions"
            ) from exc
        options_type = getattr(module, "ContextPackOptions", None)
        if options_type is None:
            raise BioClientConfigurationError(
                "BIO bridge module does not expose ContextPackOptions; "
                "provide context_options_factory"
            )
        return options_type
