"""SCOS Stage 4.1 commercial report contract + Stage 4.2 delivery package.

Stage 4.3 note: exports are resolved lazily via PEP 562 module ``__getattr__``
so importing this package (for example ``python -m scos.commercial.cli``) does
not eagerly import the Stage 4.1 report builder or the Stage 3.9 knowledge access
layer. This keeps the knowledge-free CLI commands (version / package / validate)
importable without ``scos/knowledge`` on ``sys.path``, while preserving every
existing public export unchanged.
"""

from __future__ import annotations

from typing import Any

# name -> sibling module that defines it (imported on first access only)
_LAZY_EXPORTS: dict[str, str] = {
    "COMMERCIAL_REPORT_SCHEMA_VERSION": "report_models",
    "CommercialReport": "report_models",
    "CommercialReportError": "report_models",
    "ReportEvidence": "report_models",
    "ReportRisk": "report_models",
    "build_commercial_report": "report_builder",
    "DELIVERY_PACKAGE_SCHEMA_VERSION": "package_models",
    "DeliveryPackageError": "package_models",
    "DeliveryPackageFile": "package_models",
    "DeliveryPackageManifest": "package_models",
    "DeliveryPackageResult": "package_models",
    "create_delivery_package": "delivery_package",
    "COMMERCIAL_CLI_SCHEMA_VERSION": "cli",
    "COMMERCIAL_RUN_SCHEMA_VERSION": "run_models",
    "CommercialRunStep": "run_models",
    "CommercialRunResult": "run_models",
    "CommercialRunError": "run_models",
    "run_commercial_delivery": "run_orchestrator",
    "COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION": "acceptance_models",
    "AcceptanceCheck": "acceptance_models",
    "CommercialAcceptanceReport": "acceptance_models",
    "CommercialAcceptanceError": "acceptance_models",
    "run_commercial_acceptance_gate": "acceptance_gate",
    "CUSTOMER_KIT_SCHEMA_VERSION": "customer_kit_models",
    "CustomerKitFile": "customer_kit_models",
    "CustomerKitResult": "customer_kit_models",
    "CustomerKitError": "customer_kit_models",
    "generate_first_customer_kit": "customer_kit",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f".{module_name}", __name__)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = (
    "COMMERCIAL_REPORT_SCHEMA_VERSION",
    "CommercialReport",
    "CommercialReportError",
    "ReportEvidence",
    "ReportRisk",
    "build_commercial_report",
    "DELIVERY_PACKAGE_SCHEMA_VERSION",
    "DeliveryPackageError",
    "DeliveryPackageFile",
    "DeliveryPackageManifest",
    "DeliveryPackageResult",
    "create_delivery_package",
    "COMMERCIAL_CLI_SCHEMA_VERSION",
    "COMMERCIAL_RUN_SCHEMA_VERSION",
    "CommercialRunStep",
    "CommercialRunResult",
    "CommercialRunError",
    "run_commercial_delivery",
    "COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION",
    "AcceptanceCheck",
    "CommercialAcceptanceReport",
    "CommercialAcceptanceError",
    "run_commercial_acceptance_gate",
    "CUSTOMER_KIT_SCHEMA_VERSION",
    "CustomerKitFile",
    "CustomerKitResult",
    "CustomerKitError",
    "generate_first_customer_kit",
)
