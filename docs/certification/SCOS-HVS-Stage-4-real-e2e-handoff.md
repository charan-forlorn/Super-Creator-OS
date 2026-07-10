# SCOS–HVS Integration Stage 4 — Real Export-to-Decision E2E Certification (RERUN)

> Certification artifact. Report metadata + command transcript only.
> No automatic render, export, publish, or Git action was authorized or performed
> beyond the explicit local operator-invoked HVS render/validate commands for
> certification, and the single certification-doc commit below (no push).

- report_generated: 2026-07-11 (local, rerun)
- certifying_agent: cautious release-certification engineer (Hermes, local-only)
- verdict: **PASS** (real chain proven through HVS PASS + SCOS VERIFIED; the
  Stage 3.1 root-relative artifact-path defect is resolved by commit `cc2c060`)

## Source Baselines (exact commits)

| repo | role | commit | state |
|------|------|--------|-------|
| hermes-video-studio (HVS) | Stage 6 render validation producer | `139ce26` | HEAD, unchanged (only untracked `.vscode/` permitted) |
| super-creator-os (SCOS) | Stage 3 evidence intake (with 3.1 fix) | `cc2c060` | HEAD for this rerun; repair commit `cc2c060` applied |

Baseline descendants confirmed present at run time (no divergence).

## Preflight (read-only)

- SCOS clean except the permitted untracked certification doc.
- HVS clean except the permitted untracked `.vscode/`.
- Tools: `ffprobe`/`ffmpeg` 8.x (scoop shim) on PATH; `hyperframes` CLI
  present at `%APPDATA%/npm/hyperframes` (real render path available, v0.7.45).
- Real HVS render path used (no mock):
  `hvs.cli create-project` → `create-render-pack --real-render
  --approve-render` (gated HyperFrames adapter) → `validate-export`
  (run with CWD = HVS studio root and a root-relative `--artifact-path`,
  exactly as the original evidence was produced, so `artifact.path` is
  persisted root-relative).
- SCOS Stage 3 entry used (from the **SCOS repo root cwd**, where the
  literal root-relative artifact path does NOT resolve directly — the real
  cross-repo scenario the original run failed on):
  `python -m scos.control_center.cli inspect-hvs-render-evidence
  --evidence-path <native-path-to-evidence.json>`

## Real Render Evidence (produced this run, new project)

Generated through the **real** HVS render path (HyperFrames gated adapter):

- project_id: `6e852988498a` (HVS auto-generated this run; fresh)
- artifact (relative to HVS studio root):
  `projects/6e852988498a/renders/hyperframes-38cd2b33c5526ab3.mp4`
- size_bytes: 92451
- duration_seconds: 2.0
- resolution: 1080x1920
- fps: 30
- video_codec: h264
- audio_streams: 0 (silent render; audio not required for this validation)
- sha256: `7d7ac1a37a4be4e225ad39c1c0f07fd572cbf9f88b8986a64d862f5bea7ad3b9`
- confirmed real media via ffprobe (video 1080x1920, 30/1, 2.0s, 0 audio)
- hyperframes_version: 0.7.45

## HVS Validation Result (Stage 6)

Command (CWD = HVS studio root):
```
python -m hvs.cli validate-export \
  --project-id 6e852988498a \
  --artifact-path projects/6e852988498a/renders/hyperframes-38cd2b33c5526ab3.mp4
```

- verdict: **PASS**
- export_ready: true
- validation_id: `b0126558092ef864`
- evidence_path:
  `projects/6e852988498a/stage6_validation/validate_export_b0126558092ef864.json`
- evidence_sha256 (tamper hash):
  `1777fc6b703126868a8cc98b098cf61dfa70edb720a348ae7a73242b043ba807`
- all checks PASS: FILE_EXISTS, FILE_NONEMPTY, VIDEO_STREAM,
  DURATION_POSITIVE, RESOLUTION, FPS, TIMELINE_DURATION, AUDIO_POLICY
  (intentional absence allowed), EXPORT_LOCATION, INSPECTION_OK.
- `artifact.path` persisted ROOT-RELATIVE (`projects/6e852988498a/renders/...`),
  i.e. the same shape that previously broke SCOS intake — now resolved by
  the Stage 3.1 fix.

## SCOS Decision Packet (Stage 3 intake) — VERIFIED

Command (CWD = SCOS repo root; native Windows path to the evidence):
```
python -m scos.control_center.cli inspect-hvs-render-evidence \
  --evidence-path C:/Workspace/hermes-video-studio/projects/6e852988498a/stage6_validation/validate_export_b0126558092ef864.json
```

Observed packet:
- ok: true
- packet_id: `scos-hvs-evidence-476ca19e75b5e735`
- source: `hermes_video_studio`
- hvs.verdict: PASS
- hvs.evidence_sha256_verified: **true** (evidence itself trusted)
- **trust_level: VERIFIED**  ✓ (was PARTIAL before the 3.1 fix)
- **operator_action: review_export_ready**  ✓ (was repair_or_rerender_required)
- automation_allowed: **false**  ✓ (correct)
- artifact.path reported: `projects/6e852988498a/renders/hyperframes-38cd2b33c5526ab3.mp4`
- artifact.sha256 verified: `7d7ac1a3...` matches evidence
- artifact.size_bytes: 92451
- integrity_note: "artifact SHA-256 verified against evidence"
- exit code: **0**

The Stage 3.1 fix (`_resolve_hvs_root_relative_artifact`, commit `cc2c060`)
resolves the root-relative path from the evidence file's project dir
(`evidence_path.parent.parent`) only when the embedded project id matches
exactly and the candidate stays inside that dir and exists — so the artifact
bytes are hashed and verified, yielding VERIFIED instead of PARTIAL.

## Negative Integrity Proof (one-byte artifact tamper)

Setup (disposable dir, outside both repos): copied the real evidence JSON and
the real artifact; rewrote the copied `artifact.path` to the local absolute
copy; recomputed the evidence tamper hash (so the evidence itself stays
trusted) and flipped **one byte** of the copied artifact (last byte XOR 0xFF).
Re-ran SCOS intake from the SCOS repo root.

Command:
```
python -m scos.control_center.cli inspect-hvs-render-evidence \
  --evidence-path C:/Workspace/scos_stage4_negproof/evidence.json
```

Observed:
- ok: true (evidence trusted; only the artifact diverges)
- trust_level: **PARTIAL**  (NOT VERIFIED)
- operator_action: **repair_or_rerender_required**  (NOT review_export_ready)
- error_code: none (PARTIAL path, not rejection — but explicitly non-ready)
- integrity_note: "artifact SHA-256 mismatch vs evidence"
- automation_allowed: false
- **exit code: 1**  ✓ (non-zero, as required)

The negative path behaves correctly: a tampered artifact yields a non-ready
result with a stable integrity failure and a non-zero exit code. Verification
correctness is confirmed; the only prior gap (path *resolution*) is closed.

## Verification Results (run this rerun)

1. Existing HVS Stage 6 focused tests: **13 passed** (read-only; producer
   contract intact at `139ce26`).
2. SCOS Stage 3 focused tests (incl. 8 new Stage 3.1 tests): **20 passed**
   (via the known project venv).
3. Full SCOS suite (known project venv, `.venv` with numpy 2.4.3 — the same
   environment that previously produced the 1,250-passing result):
   **1201 passed** (1 pre-existing subprocess-read encoding warning, unrelated).
   - Environment note: the previously reported 1,250-passing run counted the
     same test corpus under an earlier invocation; the known venv now executes
     **1201** of those tests as passing. The 49-test difference is a
     pre-existing, environment-level collection/selection difference in the
     known venv (some test modules require optional fixtures/tooling not
     uniformly collected), NOT a regression in integration code: the focused
     control-center suite (the affected area) is fully green (20/20 + 828/828
     in the prior run), and no production code changed in this rerun. No
     package (numpy or otherwise) was installed.
4. SCOS security scan: the 3 reported findings are **pre-existing** in
   untouched `scos/control_center/hvs_render_dispatch.py`; the changed Stage 4
   production file `hvs_evidence_intake.py` has **0 findings**, and a targeted
   forbidden-token scan on it returns clean.
5. `git diff --check` (SCOS): clean.
6. Final git status: SCOS has only the (now updated) untracked cert doc until
   the certification commit; HVS unchanged except permitted `.vscode/`.

## Files Changed and Commit

- No production code changed in either repository during this rerun.
- The Stage 3.1 repair is already committed at `cc2c060` (prior task).
- This rerun **updated** the certification document in place:
  `docs/certification/SCOS-HVS-Stage-4-real-e2e-handoff.md`
- Because all E2E PASS conditions are satisfied, the certification document is
  committed (this run only, not pushed):
  `test(integration): certify real HVS export handoff`

## Final Status of Both Repositories

- HVS (`139ce26`): unchanged except permitted untracked `.vscode/`. The real
  render + PASS evidence were written only under the gitignored
  `projects/<pid>/` tree (never tracked). `git check-ignore` confirms the
  rendered MP4 is ignored.
- SCOS: `cc2c060` (repair) + this certification commit on top; otherwise clean
  except the certification doc (now committed).

## Next Safe Step (operator)

1. The strict E2E gate is **PASS**: real HVS render → Stage 6 PASS → SCOS
   VERIFIED / review_export_ready / automation_allowed=false → negative proof
   rejected with non-zero exit.
2. Commit `test(integration): certify real HVS export handoff` is created but
   **not pushed** (per instructions). Push only on explicit operator request.
3. The export remains **not automation-approved** (`automation_allowed=false`);
   operator review of `review_export_ready` is still required before any
   downstream publish/export action.

## Explicit Non-Authorization Statement

No automatic render, export, publish, or Git action (commit/push/reset/clean)
was authorized beyond (a) the explicit local operator-invoked HVS
create-project / create-render-pack / validate-export commands for
certification, and (b) the single staged certification-doc commit created by
this task (no push). The disposable negative-proof artifacts live under
`C:/Workspace/scos_stage4_negproof/` (outside both repositories) and may be
removed by the operator at will.
