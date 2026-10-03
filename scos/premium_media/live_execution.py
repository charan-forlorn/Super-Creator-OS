
"""Live provider readiness and D3-safe smoke gate."""
from __future__ import annotations
from dataclasses import dataclass
from .video_generation import GenerationPlan
from .video_generation_runtime import ProviderAdapterRegistry


@dataclass(frozen=True)
class ProviderReadiness:
    provider_id: str
    configured: bool
    adapter_present: bool
    executable_shots: tuple[str, ...]
    blocked_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class LiveExecutionReadiness:
    ready: bool
    providers: tuple[ProviderReadiness, ...]
    reason: str


class LiveExecutionAuthorityError(RuntimeError):
    pass


def assess_live_readiness(plan: GenerationPlan, registry: ProviderAdapterRegistry) -> LiveExecutionReadiness:
    reports = []
    provider_ids = sorted({p for d in plan.decisions for p in (d.selected_provider_id, *d.fallback_provider_ids)})
    for provider_id in provider_ids:
        try:
            adapter = registry.get(provider_id)
        except KeyError:
            reports.append(ProviderReadiness(provider_id, False, False, (), ("adapter_missing",)))
            continue
        configured = adapter.available()
        executable = tuple(shot.shot_id for shot in plan.shots if configured and not adapter.validate_spec(shot))
        reasons = () if configured and executable else (("credential_not_configured",) if not configured else ("no_plan_shot_executable",))
        reports.append(ProviderReadiness(provider_id, configured, True, executable, reasons))
    ready = any(r.configured and r.executable_shots for r in reports)
    return LiveExecutionReadiness(ready, tuple(reports), "live provider execution is available" if ready else "no configured executable provider")


def require_explicit_live_authority(*, authorized: bool) -> None:
    if not authorized:
        raise LiveExecutionAuthorityError("live generation may create external/financial side effects; explicit authority is required")
