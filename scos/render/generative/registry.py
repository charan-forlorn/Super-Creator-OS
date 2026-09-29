"""Provider registry for local generative video backends.

The registry is intentionally small: provider names are explicit, missing providers
fail closed, and adapters remain independent of deterministic render code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from scos.render.base import GenerativeBackend, RenderError


@dataclass(frozen=True)
class GenerativeBackendRegistry:
    providers: dict[str, GenerativeBackend]

    def get(self, backend_id: str) -> GenerativeBackend:
        key = str(backend_id or "").strip()
        provider = self.providers.get(key)
        if provider is None:
            raise RenderError(
                f"generative backend '{key}' is not registered; generation failed closed"
            )
        return provider

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.providers))


def build_registry(providers: Iterable[GenerativeBackend] = ()) -> GenerativeBackendRegistry:
    registry: dict[str, GenerativeBackend] = {}
    for provider in providers:
        key = provider.backend_id.strip()
        if not key:
            raise ValueError("generative provider backend_id must be non-empty")
        if key in registry:
            raise ValueError(f"duplicate generative backend registration: {key}")
        registry[key] = provider
    return GenerativeBackendRegistry(registry)


__all__ = ["GenerativeBackendRegistry", "build_registry"]
