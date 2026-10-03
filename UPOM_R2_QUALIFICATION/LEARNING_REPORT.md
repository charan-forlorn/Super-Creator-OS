# AI Business Production R1 — UPOM R2 Learning Report

## 1. Starting truth
The branch contained committed adaptive routing source and tests, but the worktree had stale dependency junctions pointing to a removed historical worktree. The shared TypeScript base config was also absent from the active branch lineage used by the package build.

## 2. Defects found and remediated
1. Broken dependency junctions prevented build/test. Re-established the pnpm workspace and lockfile so the package can be installed from current repository state.
2. Missing shared TypeScript base config blocked package compilation. Restored the historical qualified config bytes.
3. Public type surface lagged runtime router exports. Enabled declaration generation for @haios/ai-providers and regenerated dist declarations.

## 3. Verification
- Frozen install PASS
- Build PASS
- 26/26 provider tests PASS
- Runtime export check PASS
- git diff --check PASS
- Fresh read-only Ollama observation PASS

## 4. Governance learning
Machine model presence is useful evidence but is not provider qualification or execution authority. The router binds machine observation to governance evidence and denies missing/stale/mismatched evidence.

## 5. UPOM R2 learning inputs
- Reproducible workspace state should be a first-class dependency node.
- Runtime API and declared type surface should be qualified together.
- Machine observation freshness should be explicit and separately classified from governance qualification.
- Route decisions should remain non-authorizing.
- Closure should bind evidence hashes to the exact committed source state.

## 6. Remaining scope outside this closure
Public deployment readiness, provider qualification, credential activation, external publishing and production promotion remain separate governed work.
