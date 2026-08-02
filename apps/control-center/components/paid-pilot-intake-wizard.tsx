"use client";
import { useEffect, useMemo, useState } from "react";
import {
  attachConsentEvidence,
  createIntakeDraft,
  getIntakeDraft,
  admitRealAsset,
  refreshAssetInventoryTestOnly,
} from "@/lib/paid-pilot-intake-client";
import { admitRealPacket, type AdmissionResponse } from "@/lib/paid-pilot-admission-client";
import { createCanonicalProject } from "@/lib/paid-pilot-create-client";
import { evaluateRenderReadiness, type RenderReadinessResponse } from "@/lib/paid-pilot-render-readiness-client";
import type { GuidedIntakeDraft } from "@/lib/paid-pilot-intake-types";

const presets = ["Vertical Product Promo", "Square Product Promo", "Landscape Product Promo", "Service Awareness Video", "Manual Local Delivery", "Custom"];
// Packet-approved assets (real, operator-owned). The browser admits each by its
// packet source_location_reference (a safe relative path resolved server-side
// under SCOS_PILOT_APPROVED_INPUT_ROOT). No absolute or browser path is sent.
const APPROVED_ASSETS = [
  { reference: "assets/product-front.jpg", safeName: "product-front.jpg" },
  { reference: "assets/customer-logo.png", safeName: "customer-logo.png" },
  { reference: "assets/promo-music-31s.mp3", safeName: "promo-music-31s.mp3" },
];
const choices = ["Yes", "No", "Not sure"];
const rightChoices = ["Owned", "Licensed", "Explicit consent", "Not used", "Not sure"];
function Status({ s }: { s: string }) {
  return <span className="rounded-full px-2 py-1 text-xs font-semibold ring-1 ring-inset">{s}</span>;
}
export function PaidPilotIntakeWizard() {
  const [mode, setMode] = useState<"quick" | "advanced">("quick");
  const [draft, setDraft] = useState<GuidedIntakeDraft | null>(null);
  const [title, setTitle] = useState("Synthetic Product Promo");
  const [template, setTemplate] = useState(presets[0]);
  const [deadline, setDeadline] = useState("2026-08-15");
  const [consentText, setConsentText] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [admission, setAdmission] = useState<AdmissionResponse | null>(null);
  const [created, setCreated] = useState<{ canonical: string | null; replay: boolean | null } | null>(null);
  const [readiness, setReadiness] = useState<RenderReadinessResponse | null>(null);
  // Create is gated on packet admission PASS (PACKET_ADMISSION = PASS), not on
  // HTTP 200 or asset count. Browser never supplies a filesystem path.
  const packetAdmitted = Boolean(admission?.ok);
  const admissionProjection = admission?.projection ?? null;
  const ready = packetAdmitted;
  const restrictions =
    admissionProjection?.external_action_restrictions ?? draft?.external_action_restrictions ?? {
      customer_notification: "Not authorized",
      external_delivery: "Not authorized",
      publishing: "Not authorized",
      upload: "Not authorized",
      deployment: "Not authorized",
    };
  const rights = useMemo(() => ({ asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" }), []);
  const privacy = useMemo(() => ({ health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" }), []);
  const remember = (next: GuidedIntakeDraft | null | undefined) => {
    setDraft(next ?? null);
    if (typeof window !== "undefined" && next?.draft_id) {
      const url = new URL(window.location.href);
      url.searchParams.set("draft_id", next.draft_id);
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
  };
  useEffect(() => {
    const id = typeof window !== "undefined" ? new URL(window.location.href).searchParams.get("draft_id") : null;
    if (!id) return;
    let live = true;
    getIntakeDraft(id).then((r) => {
      if (live && r.ok && r.draft) remember(r.draft);
      else if (live) setFeedback("Draft identity not found; start a new guided draft.");
    });
    return () => {
      live = false;
    };
  }, []);
  async function start() {
    setPending(true);
    const r = await createIntakeDraft({
      safe_project_title: title,
      selected_template: template,
      deadline,
      commercial_reference: "synthetic-local-pilot",
      rights_answers: rights,
      privacy_answers: privacy,
    });
    remember(r.draft);
    setFeedback(r.ok ? "Draft validated by Python authority" : "Draft failed");
    setPending(false);
  }
  async function attachConsent() {
    if (!draft) return;
    setPending(true);
    const r = await attachConsentEvidence(draft.draft_id, "redacted-consent-evidence.txt", consentText, confirmed);
    remember(r.draft);
    setFeedback(r.ok ? "Consent evidence hashed and stored as safe reference" : "Consent rejected");
    setPending(false);
  }
  // Real packet-approved asset admission: each approved file is attached by its
  // safe relative reference; the server validates hash/size and binds it.
  async function admitApprovedAssets() {
    if (!draft) return;
    setPending(true);
    let last = null as GuidedIntakeDraft | null;
    for (const a of APPROVED_ASSETS) {
      const r = await admitRealAsset(draft.draft_id, a.reference);
      if (!r.ok) {
        setFeedback(`Asset admission failed: ${r.error_code}`);
        setPending(false);
        return;
      }
      last = r.draft;
    }
    remember(last);
    setFeedback("All three packet-approved assets admitted and hash-verified");
    setPending(false);
  }
  // TEST-only synthetic fixture. Rejected in real-packet mode by the authority.
  async function markAssetsReadyTestOnly() {
    if (!draft) return;
    setPending(true);
    const r = await refreshAssetInventoryTestOnly(draft.draft_id);
    remember(r.draft);
    setFeedback(r.ok ? "Test fixture attached (TEST ONLY)" : `Test fixture rejected: ${r.error_code}`);
    setPending(false);
  }
  // Authoritative packet admission (§6.A). The browser submits only the operator
  // seal; all roots + packet path are resolved server-side. Persists one
  // durable admission record. Create stays disabled until this passes.
  async function admitAuthorizationPacket() {
    if (!draft) return;
    setPending(true);
    const exp = typeof window !== "undefined"
      ? (new URL(window.location.href).searchParams.get("expected_sha256") ?? "")
      : "";
    const r = await admitRealPacket(exp);
    setAdmission(r);
    if (r.ok) {
      setFeedback(`Packet admitted: ${r.projection?.project_ref ?? ""} (${r.projection?.asset_count ?? 0} assets)`);
    } else {
      setFeedback(`Packet admission blocked: ${r.error_code}`);
    }
    setPending(false);
  }
  async function createPilot() {
    if (!packetAdmitted) return;
    setPending(true);
    const key = `create-${draft?.draft_id ?? "x"}`;
    const r = await createCanonicalProject(key);
    setCreated({ canonical: r.canonical_internal_project_id, replay: r.replay });
    setFeedback(
      r.ok
        ? `Canonical project created: ${r.canonical_internal_project_id}${r.replay ? " (replay, no second write)" : ""}`
        : `Create blocked: ${r.error_code}`,
    );
    setPending(false);
  }
  async function checkReadiness() {
    // Readiness is keyed by the ADMITTED external project_ref (authoritative,
    // persisted), NOT the displayed canonical spp-* id. The server derives the
    // canonical id server-side from the persisted identity mapping.
    const ref = admissionProjection?.project_ref;
    if (!ref || !created?.canonical) return;
    setPending(true);
    const r = await evaluateRenderReadiness(ref);
    setReadiness(r);
    setPending(false);
  }
  const blocked = draft?.validation_findings ?? [];
  const admittedCount = draft?.asset_references?.length ?? 0;
  return (
    <section aria-labelledby="guided-intake-title" className="space-y-4">
      <div className="panel-heading">
        <div>
          <p className="action-kicker">Paid Pilot Intake</p>
          <h2 id="guided-intake-title">Start New Pilot</h2>
          <p>Quick Setup is default. The browser collects answers; Python creates trusted IDs, hashes, roots, packets, and audit events.</p>
        </div>
        <Status s={admission?.ok ? "PACKET_ADMITTED" : (draft?.status ?? "DRAFT")} />
      </div>
      <div role="tablist" aria-label="Pilot setup mode">
        <button className="button-primary" aria-pressed={mode === "quick"} onClick={() => setMode("quick")}>Quick Setup</button>
        <button className="button-secondary" aria-expanded={mode === "advanced"} aria-pressed={mode === "advanced"} onClick={() => setMode(mode === "advanced" ? "quick" : "advanced")}>Advanced Setup</button>
      </div>
      {mode === "advanced" && (
        <details open>
          <summary>Technical evidence and optional advanced configuration</summary>
          <p>No YAML or JSON editing is required. Manual paths remain server-authorized only.</p>
        </details>
      )}
      <ol className="space-y-4">
        <li>
          <h3>Step 1 — Project</h3>
          <label>Safe project title<input aria-label="Safe project title" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label>Work template<select aria-label="Work template" value={template} onChange={(e) => setTemplate(e.target.value)}>{presets.map((p) => <option key={p}>{p}</option>)}</select></label>
          <label>Deadline<input aria-label="Deadline" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
          <button type="button" className="button-primary" disabled={pending} onClick={start}>Create guided draft</button>
        </li>
        <li>
          <h3>Step 2 — Assets (packet-approved only)</h3>
          <p role="status">Admitted: {admittedCount} / {APPROVED_ASSETS.length}</p>
          <ul>
            {APPROVED_ASSETS.map((a) => (
              <li key={a.reference} data-testid={`approved-asset-${a.safeName}`}>{a.safeName}</li>
            ))}
          </ul>
          <button type="button" className="button-secondary" disabled={!draft || pending} onClick={admitApprovedAssets}>
            Admit packet-approved assets
          </button>
          <button type="button" className="button-secondary" disabled={!draft || pending} onClick={markAssetsReadyTestOnly}>
            Attach test fixture (TEST ONLY, rejected in real mode)
          </button>
        </li>
        <li>
          <h3>Step 3 — Authorization packet admission (§6.A)</h3>
          <p>Authoritative admission of the operator authorization packet. The browser never supplies a filesystem path; the server resolves the trusted packet and verifies the operator seal.</p>
          <button type="button" className="button-primary" disabled={!draft || pending} onClick={admitAuthorizationPacket} data-testid="admit-packet">
            Admit authorization packet
          </button>
          {admissionProjection && (
            <div role="status" data-testid="admission-projection">
              <p>Packet: {admissionProjection.packet_sha256}</p>
              <p>Pilot: {admissionProjection.pilot_id}</p>
              <p>Customer: {admissionProjection.customer_ref}</p>
              <p>Project: {admissionProjection.project_ref}</p>
              <p>Assets: {admissionProjection.assets?.map((a) => a.safe_name).join(", ")}</p>
              <p>Rights: {JSON.stringify(admissionProjection.font_policy)}</p>
              <p>External restrictions: {Object.entries(admissionProjection.external_action_restrictions ?? {}).map(([k, v]) => `${k}=${v}`).join(", ")}</p>
            </div>
          )}
        </li>
        <li>
          <h3>Step 4 — Consent</h3>
          <button type="button" onClick={() => setConsentText("Customer explicitly approves this synthetic pilot asset package.")}>Generate consent message</button>
          <textarea aria-label="Consent evidence text" value={consentText} onChange={(e) => setConsentText(e.target.value)} />
          <label><input type="checkbox" aria-label="Confirm explicit consent" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> Explicit consent confirmed</label>
          <button type="button" className="button-secondary" disabled={!draft || pending} onClick={attachConsent}>Attach consent evidence</button>
        </li>
        <li>
          <h3>Step 5 — Create (disabled until packet admission)</h3>
          {/* External actions are locked by server-side policy and surfaced truthfully
              without leaking any raw evidence, path, or PII (R4/R5). */}
          <p role="note" data-testid="external-action-restrictions">
            External actions: not authorized (publishing, delivery, upload, deployment)
          </p>
          <button type="button" className="button-primary" disabled={!ready || pending} onClick={createPilot} data-testid="create-pilot">
            Create Pilot Project
          </button>
          <p role="status">{ready ? "Ready to create (packet admitted)" : "Create disabled until PACKET_ADMISSION = PASS"}</p>
          {created && (
            <p role="status" data-testid="created-canonical">Created: {created.canonical}{created.replay ? " (replay)" : ""}</p>
          )}
        </li>
        <li>
          <h3>Step 6 — Pre-render readiness (read-only)</h3>
          <button type="button" className="button-secondary" disabled={!created?.canonical || pending} onClick={checkReadiness}>Check render readiness</button>
          {readiness && (
            <p role="status" data-testid="render-readiness-state">{readiness.state}{readiness.projection ? ` — ${readiness.projection.asset_safe_names.join(", ")}` : ""}</p>
          )}
        </li>
      </ol>
      {blocked.length > 0 && (
        <ul>
          {blocked.map((f, i) => (
            <li key={i} data-testid={`finding-${f.field}`}>{f.field}: {f.message}</li>
          ))}
        </ul>
      )}
      {feedback && <p role="status" data-testid="wizard-feedback">{feedback}</p>}
    </section>
  );
}
