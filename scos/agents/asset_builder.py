"""Maps each scene to a real, deterministic media asset (PNG + WAV).

This is the Stage-1 contract: the orchestrator instantiates one AssetBuilder
and calls ``run({"run_id": ..., "scene_plan": ...})`` exactly as before, so
nothing upstream changes.

Internally this delegates to the qualified AssetBuilderV2, which produces
real PNG + WAV bytes deterministically (no RNG, no cloud APIs). The v1
interface is preserved so EditComposer + the render engine consume the
bundle unchanged.
"""

from __future__ import annotations

import hashlib

from scos.assets.asset_builder_v2 import AssetBuilderV2, _derive_run_id


class AssetBuilder:
    """Bounded local asset generator — preserves the v1 orchestrator contract."""

    def __init__(self) -> None:
        self._v2 = AssetBuilderV2()

    def run(self, input_data: dict) -> dict:
        run_id = input_data["run_id"]
        scene_plan = input_data["scene_plan"]
        result = self._v2.run(scene_plan, run_id=run_id)
        return {"assets": result["assets"]}


# Backwards compatibility: _derive_run_id is re-exported so any external
# import of ``from scos.agents.asset_builder import _derive_run_id`` still works.
