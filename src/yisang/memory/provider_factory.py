from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

from .native_provider import NativeMemoryProvider
from .pipeline import MemoryWritePipeline
from .port import MemoryPort
from .provider import MemoryProvider

if TYPE_CHECKING:
    from yisang.integrations.bio.client import BioMemoryClient
    from yisang.integrations.bio.config import BioProviderConfig


@dataclass(frozen=True)
class MemoryProviderSelection:
    provider: str = "native"

    def __post_init__(self) -> None:
        normalized = self.provider.strip().casefold()
        if normalized not in {"native", "bio"}:
            raise ValueError(f"unsupported memory provider: {self.provider}")
        object.__setattr__(self, "provider", normalized)

    @classmethod
    def from_env(cls) -> "MemoryProviderSelection":
        return cls(provider=os.getenv("YISANG_MEMORY_PROVIDER", "native"))


def build_memory_provider(
    selection: MemoryProviderSelection,
    *,
    native_memory: MemoryPort | None = None,
    native_pipeline: MemoryWritePipeline | None = None,
    bio_client: "BioMemoryClient | None" = None,
    bio_config: "BioProviderConfig | None" = None,
) -> MemoryProvider:
    if selection.provider == "native":
        if native_memory is None or native_pipeline is None:
            raise ValueError(
                "native provider requires native_memory and native_pipeline"
            )
        return NativeMemoryProvider(
            memory=native_memory,
            pipeline=native_pipeline,
        )

    if bio_client is None:
        raise ValueError("bio provider requires bio_client")
    from yisang.integrations.bio.provider import BioMemoryProvider

    return BioMemoryProvider(client=bio_client, config=bio_config)
