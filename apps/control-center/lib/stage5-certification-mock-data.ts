// SCOS Control Center - Stage 5.10 static mock data for the Stage 5 Final
// Certification panel. Deterministic, hand-authored fixtures only. No
// clock, no random, no UUIDs, no fetch. This mirrors a real (expected)
// result shape from scos/control_center/stage5_final_certification.py - the
// real gate is expected to certify NO_GO today because of the confirmed
// Stage 5.6 defects, which this static mock reflects rather than hides.

import type {
  Stage5CertificationBlockerView,
  Stage5CertificationCheckView,
  Stage5FinalCertificationResultView,
  Stage6HandoffItemView,
} from "./stage5-certification-types";

const CHECKS: readonly Stage5CertificationCheckView[] = [
  { checkName: "validate_inputs", status: "success", severity: "info", category: "preflight", artifactPath: ".", errorKind: null, errorDetail: null },
  { checkName: "validate_repo_root_exists", status: "success", severity: "info", category: "preflight", artifactPath: ".", errorKind: null, errorDetail: null },
  { checkName: "validate_git_state", status: "success", severity: "info", category: "preflight", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_1_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_2_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_3_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_4_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_5_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  {
    checkName: "validate_stage5_6_artifacts",
    status: "failure",
    severity: "error",
    category: "source_contract",
    artifactPath: "scos/control_center/__init__.py",
    errorKind: "STAGE_ARTIFACT_MISSING",
    errorDetail: "Stage 5.6 artifacts/exports incomplete",
  },
  { checkName: "validate_stage5_7_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_8_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage5_9_artifacts", status: "success", severity: "info", category: "source_contract", artifactPath: null, errorKind: null, errorDetail: null },
  {
    checkName: "validate_init_no_duplicate_lazy_export_keys",
    status: "failure",
    severity: "error",
    category: "source_contract",
    artifactPath: "scos/control_center/__init__.py",
    errorKind: "DUPLICATE_LAZY_EXPORT_KEY",
    errorDetail: "ALLOWED_COMMAND_TYPES is defined more than once",
  },
  {
    checkName: "validate_stage5_6_frontend_wiring",
    status: "failure",
    severity: "warning",
    category: "source_contract",
    artifactPath: "apps/control-center/components/app-shell.tsx",
    errorKind: "FRONTEND_PANEL_UNWIRED",
    errorDetail: "workflow-router-panel is not wired into app-shell/sidebar",
  },
  {
    checkName: "run_stage5_6_tests",
    status: "failure",
    severity: "error",
    category: "testing",
    artifactPath: null,
    errorKind: "STAGE_TEST_FAILED",
    errorDetail: "one or more Stage 5.6 test files failed",
  },
  { checkName: "validate_no_real_ai_dispatch", status: "success", severity: "info", category: "safety_boundary", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_backend_forbidden_tokens", status: "success", severity: "info", category: "safety_boundary", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_frontend_forbidden_tokens", status: "success", severity: "info", category: "safety_boundary", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_no_app_api_or_middleware", status: "success", severity: "info", category: "safety_boundary", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_subprocess_allowlist_exception", status: "success", severity: "info", category: "safety_boundary", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "run_smoke_script", status: "success", severity: "info", category: "testing", artifactPath: "scripts/test_smoke.py", errorKind: null, errorDetail: null },
  { checkName: "run_security_scan_baseline", status: "success", severity: "info", category: "security", artifactPath: "scripts/security_scan_baseline.py", errorKind: null, errorDetail: null },
  { checkName: "validate_stage6_handoff_items_generated", status: "success", severity: "info", category: "stage6_handoff", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "validate_stage6_handoff_doc_exists", status: "success", severity: "info", category: "stage6_handoff", artifactPath: "docs/roadmap/STAGE6_HANDOFF.md", errorKind: null, errorDetail: null },
  { checkName: "validate_no_stage5_11_plus", status: "success", severity: "info", category: "stage5_readiness", artifactPath: null, errorKind: null, errorDetail: null },
  { checkName: "compute_stage5_readiness", status: "success", severity: "info", category: "stage5_readiness", artifactPath: null, errorKind: null, errorDetail: null },
];

const BLOCKERS: readonly Stage5CertificationBlockerView[] = [
  {
    blockerId: "blk-stage5-6-artifacts",
    category: "source_contract",
    severity: "error",
    title: "Stage 5.6 artifacts or package exports are incomplete",
    detail: "scos/control_center/__init__.py has zero _LAZY_EXPORTS entries for workflow_router*.",
    recommendedAction: "Add the missing _LAZY_EXPORTS entries for Stage 5.6's modules.",
    sourceCheck: "validate_stage5_6_artifacts",
  },
  {
    blockerId: "blk-duplicate-lazy-export-key",
    category: "source_contract",
    severity: "error",
    title: "scos/control_center/__init__.py has duplicate _LAZY_EXPORTS keys",
    detail: "ALLOWED_COMMAND_TYPES resolves to Stage 5.9's constant, silently shadowing Stage 5.1's.",
    recommendedAction: "Rename the colliding constant in one of the two stages.",
    sourceCheck: "validate_init_no_duplicate_lazy_export_keys",
  },
  {
    blockerId: "blk-stage5-6-frontend-wiring",
    category: "source_contract",
    severity: "warning",
    title: "Stage 5.6 workflow-router-panel is never rendered",
    detail: "Not imported into app-shell.tsx and missing from sidebar.tsx NAV_SECTIONS.",
    recommendedAction: "Wire the panel into app-shell.tsx and add a NAV_SECTIONS entry.",
    sourceCheck: "validate_stage5_6_frontend_wiring",
  },
  {
    blockerId: "blk-stage5-6-tests",
    category: "testing",
    severity: "error",
    title: "Stage 5.6 test suite failed",
    detail: "Stage 5.6 test files use a different import bootstrap than every other stage.",
    recommendedAction: "Align Stage 5.6's test files with the sys.path.insert convention.",
    sourceCheck: "run_stage5_6_tests",
  },
];

const STAGE6_HANDOFF_ITEMS: readonly Stage6HandoffItemView[] = [
  { itemId: "stage6-001", title: "Implement the real Control Center backend & command API", category: "control_center_backend", priority: "urgent", description: "Turn the Stage 5.1 command bridge design into a working local backend.", stage6Owner: "stage6-platform", sourceStage5Evidence: "scos/control_center/command_runner.py" },
  { itemId: "stage6-002", title: "Design and wire a real operator event stream", category: "event_stream", priority: "high", description: "Deliver a live event stream reflecting command/workflow progress in real time.", stage6Owner: "stage6-platform", sourceStage5Evidence: "scos/control_center/event_log.py" },
  { itemId: "stage6-003", title: "Fix the Stage 5.6 package export gap", category: "technical_debt", priority: "urgent", description: "scos/control_center/__init__.py has zero exports for workflow_router*.", stage6Owner: "stage6-platform", sourceStage5Evidence: "scos/control_center/__init__.py" },
  { itemId: "stage6-004", title: "Resolve the duplicate ALLOWED_COMMAND_TYPES lazy-export key", category: "technical_debt", priority: "urgent", description: "The second entry silently shadows the first at runtime.", stage6Owner: "stage6-platform", sourceStage5Evidence: "scos/control_center/__init__.py" },
  { itemId: "stage6-005", title: "Wire workflow-router-panel.tsx into the app shell", category: "frontend", priority: "normal", description: "The panel renders nowhere in the actual app today.", stage6Owner: "stage6-frontend", sourceStage5Evidence: "apps/control-center/components/app-shell.tsx" },
  { itemId: "stage6-006", title: "Clean up the stray Stage 5.6 leftover line in the README", category: "documentation", priority: "low", description: "A pre-heading line does not match the README's structure.", stage6Owner: "stage6-docs", sourceStage5Evidence: "apps/control-center/README.md" },
  { itemId: "stage6-007", title: "Decide which agent adapters become real dispatchers", category: "ai_dispatch_boundary", priority: "urgent", description: "Always gated behind explicit operator approval, never automatic.", stage6Owner: "stage6-lead", sourceStage5Evidence: "scos/control_center/agent_adapter_simulator.py" },
  { itemId: "stage6-008", title: "Execute the remaining Stage 5 handoff gates", category: "commercial_execution", priority: "high", description: "Work through Gates 5.A-5.D before Stage 6 builds further.", stage6Owner: "stage6-lead", sourceStage5Evidence: "docs/roadmap/STAGE5_HANDOFF.md" },
  { itemId: "stage6-009", title: "Add an automated test tier for apps/control-center", category: "testing", priority: "normal", description: "Only dev/build/start/lint exist today; no test runner.", stage6Owner: "stage6-operations", sourceStage5Evidence: "apps/control-center/package.json" },
  { itemId: "stage6-010", title: "Define Stage 6 success criteria and its own closure gate", category: "stage6_readiness", priority: "urgent", description: "Mirror the Stage 5.10 / Stage 4.19 certification pattern.", stage6Owner: "stage6-lead", sourceStage5Evidence: "docs/certification/Stage-5-final-ai-command-center-certification.md" },
];

export const STAGE5_FINAL_CERTIFICATION_RESULT: Stage5FinalCertificationResultView = {
  certificationId: "s5c-0123456789abcdef",
  checkedAt: "2026-07-06T00:00:00Z",
  stage: "5",
  stageClosed: false,
  goNoGo: "NO_GO",
  readinessLevel: "blocked",
  readinessScore: 78,
  readinessMaxScore: 100,
  checks: CHECKS,
  blockers: BLOCKERS,
  stage6HandoffItems: STAGE6_HANDOFF_ITEMS,
};
