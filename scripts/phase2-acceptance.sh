#!/usr/bin/env bash
# Phase 2 — No-Terminal Acceptance gate.
# Runs the Phase-2 vitest suites + the canonical Python regression targets.
# Exits non-zero if either leg fails. Fully local; no network.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CC="$ROOT/apps/control-center"

echo "== Phase 2 — Vitest acceptance (--phase2 --gate) =="
node "$CC/scripts/run-tests-local.mjs" --phase2 --gate
VITEST_RC=$?
if [ "$VITEST_RC" -ne 0 ]; then
  echo "VITEST GATE: RED (rc=$VITEST_RC)"
  exit 2
fi
echo "VITEST GATE: GREEN"

echo "== Phase 2 — Python canonical regression (control_center targets) =="
( cd "$ROOT" && uv run pytest \
    scos/control_center/tests/test_control_center_snapshot.py \
    scos/control_center/tests/test_stage7_closure_gate.py -q )
PY_RC=$?
if [ "$PY_RC" -ne 0 ]; then
  echo "PYTEST: RED (rc=$PY_RC)"
  exit 3
fi
echo "PYTEST: GREEN"

echo "== Phase 2 ACCEPTANCE: PASS =="
exit 0
