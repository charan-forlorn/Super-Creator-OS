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
    "MONETIZATION_READINESS_SCHEMA_VERSION": "monetization_models",
    "MonetizationReadinessCheck": "monetization_models",
    "MonetizationGap": "monetization_models",
    "MonetizationReadinessResult": "monetization_models",
    "MonetizationReadinessError": "monetization_models",
    "review_monetization_readiness": "monetization_readiness",
    "FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION": "dry_run_models",
    "SyntheticCustomerCase": "dry_run_models",
    "DryRunStep": "dry_run_models",
    "DryRunBlocker": "dry_run_models",
    "FirstPaidCustomerDryRunResult": "dry_run_models",
    "FirstPaidCustomerDryRunError": "dry_run_models",
    "run_first_paid_customer_dry_run": "first_paid_customer_dry_run",
    "COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION": "launch_certification_models",
    "LaunchCertificationCheck": "launch_certification_models",
    "LaunchCertificationBlocker": "launch_certification_models",
    "LaunchCertificationArtifact": "launch_certification_models",
    "LaunchCertificationResult": "launch_certification_models",
    "LaunchCertificationError": "launch_certification_models",
    "create_commercial_launch_certification_pack": "launch_certification_pack",
    "OPERATOR_PRACTICE_SCHEMA_VERSION": "practice_models",
    "PracticeScenario": "practice_models",
    "PracticeStep": "practice_models",
    "PracticeObservation": "practice_models",
    "OperatorPracticeResult": "practice_models",
    "OperatorPracticeError": "practice_models",
    "available_practice_scenarios": "operator_practice_lab",
    "run_operator_practice_scenario": "operator_practice_lab",
    "FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION": "outreach_models",
    "OutreachLaunchProfile": "outreach_models",
    "OutreachAsset": "outreach_models",
    "OutreachReadinessCheck": "outreach_models",
    "FirstOutreachLaunchKitResult": "outreach_models",
    "FirstOutreachLaunchKitError": "outreach_models",
    "create_first_outreach_launch_kit": "first_outreach_launch_kit",
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
    "MONETIZATION_READINESS_SCHEMA_VERSION",
    "MonetizationReadinessCheck",
    "MonetizationGap",
    "MonetizationReadinessResult",
    "MonetizationReadinessError",
    "review_monetization_readiness",
    "FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION",
    "SyntheticCustomerCase",
    "DryRunStep",
    "DryRunBlocker",
    "FirstPaidCustomerDryRunResult",
    "FirstPaidCustomerDryRunError",
    "run_first_paid_customer_dry_run",
    "COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION",
    "LaunchCertificationCheck",
    "LaunchCertificationBlocker",
    "LaunchCertificationArtifact",
    "LaunchCertificationResult",
    "LaunchCertificationError",
    "create_commercial_launch_certification_pack",
    "OPERATOR_PRACTICE_SCHEMA_VERSION",
    "PracticeScenario",
    "PracticeStep",
    "PracticeObservation",
    "OperatorPracticeResult",
    "OperatorPracticeError",
    "available_practice_scenarios",
    "run_operator_practice_scenario",
    "FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION",
    "OutreachLaunchProfile",
    "OutreachAsset",
    "OutreachReadinessCheck",
    "FirstOutreachLaunchKitResult",
    "FirstOutreachLaunchKitError",
    "create_first_outreach_launch_kit",
)
