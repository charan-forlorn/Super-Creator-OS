"use client";

import { useMemo, useState } from "react";
import { useLocale } from "@/lib/i18n";
import { CockpitShell } from "@/components/cockpit/cockpit-shell";
import { DetailPanel, FilterControl, LocalToast, RouteHeader, StatusBadge } from "@/components/cockpit/route-primitives";
import {
  DEMO_LABEL,
  useControlCenterData,
  type CockpitView,
} from "@/lib/control-center-snapshot";

function SourceModeNote({ mode }: { mode: "LIVE" | "DEMO" }) {
  if (mode === "DEMO") {
    return <span className="cockpit-note cockpit-note--demo" role="status">{DEMO_LABEL}</span>;
  }
  return <span className="cockpit-note cockpit-note--live"><i />{DEMO_LABEL ? "Live local read-only" : ""}</span>;
}

function UnavailableOrEmpty({ available, isEmpty, emptyText, unavailableText }: { available: boolean; isEmpty: boolean; emptyText: string; unavailableText: string }) {
  if (!available) return <p className="empty-state empty-state--unavailable">{unavailableText}</p>;
  if (isEmpty) return <p className="empty-state">{emptyText}</p>;
  return null;
}

function ProjectsSurface() {
  const { t, locale } = useLocale();
  const { mode, view } = useControlCenterData("LIVE");
  const [filter, setFilter] = useState<"all" | "available" | "unavailable">("all");
  const [selected, setSelected] = useState<string | null>(null);

  const tableRows = view.projects.stateTables;
  const filtered = useMemo(() => {
    if (filter === "available") return tableRows;
    return tableRows;
  }, [filter, tableRows]);

  return (
    <section className="cockpit-content route-content">
      <RouteHeader route="projects" />
      <div className="route-toolbar">
        <FilterControl
          value={filter}
          onChange={setFilter}
          label={t.bridge.source}
          options={[
            { value: "all", label: t.bridge.source },
            { value: "available", label: t.bridge.available },
            { value: "unavailable", label: t.bridge.unavailable },
          ]}
        />
        <SourceModeNote mode={mode} />
      </div>
      <div className="route-two-column">
        <section className="route-list" aria-label={t.v02.route.projects.title}>
          {!view.projects.available ? (
            <p className="empty-state empty-state--unavailable">{t.bridge.unavailable}</p>
          ) : (
            <article className="project-row" key="project-state">
              <div className="project-row__head">
                <h2>{t.bridge.backend}</h2>
                <StatusBadge tone={view.projects.hasDedicatedModel ? "active" : "needs-you"}>
                  {view.projects.hasDedicatedModel ? t.bridge.available : t.bridge.readOnlyBridge}
                </StatusBadge>
              </div>
              <p>{t.bridge.readOnlyBridge}</p>
              <div className="project-row__meta">
                <span>{t.bridge.source}: {view.projects.stateTables.length} state tables</span>
                <span>{locale === "th" ? "โหมดข้อมูล: " : "mode: "}{mode}</span>
              </div>
            </article>
          )}
          {filtered.length === 0 && view.projects.available && <p className="empty-state">{t.bridge.noActivity}</p>}
        </section>
        {selected && (
          <DetailPanel title={selected} onClose={() => setSelected(null)}>
            <dl className="detail-list">
              <div><dt>{t.bridge.source}</dt><dd>{selected}</dd></div>
            </dl>
          </DetailPanel>
        )}
      </div>
    </section>
  );
}

function ApprovalsSurface() {
  const { t } = useLocale();
  const { mode, view } = useControlCenterData("LIVE");
  const [feedback, setFeedback] = useState<string | null>(null);

  const available = view.approvals.available;
  const count = view.approvals.count;

  return (
    <section className="cockpit-content route-content">
      <RouteHeader route="approvals" />
      <div className="route-toolbar">
        <SourceModeNote mode={mode} />
      </div>
      <div className="approvals-layout">
        <section className="approval-queue" aria-label={t.v02.route.approvals.title}>
          {!available ? (
            <p className="empty-state empty-state--unavailable">{t.bridge.approvalsUnavailable}</p>
          ) : count === 0 ? (
            <p className="empty-state">{t.bridge.approvalsAvailable(0)}</p>
          ) : (
            <article className="approval-card approval-card--high">
              <div className="approval-card__top">
                <StatusBadge tone="high">{t.bridge.approvals}</StatusBadge>
                <StatusBadge tone="waiting">{t.bridge.available}</StatusBadge>
              </div>
              <h2>{t.bridge.approvalsAvailable(count ?? 0)}</h2>
              <p>{t.bridge.readOnlyBridge}</p>
              <div className="approval-actions">
                {/* Read-only bridge: mutation controls remain disabled. */}
                <button type="button" className="button-primary" disabled aria-disabled="true">{t.v02.actions.approve}</button>
                <button type="button" className="button-secondary" disabled aria-disabled="true">{t.v02.actions.requestChanges}</button>
                <button type="button" className="button-danger" disabled aria-disabled="true">{t.v02.actions.reject}</button>
              </div>
            </article>
          )}
        </section>
        <aside className="approval-side">
          <section className="cockpit-panel activity-panel">
            <h2>{t.v02.labels.activity}</h2>
            <p className="cockpit-note cockpit-note--live">{t.bridge.readOnlyBridge}</p>
          </section>
        </aside>
      </div>
      {mode === "DEMO" && <LocalToast message={DEMO_LABEL} onClose={() => setFeedback(null)} />}
    </section>
  );
}

function EvidenceSurface() {
  const { t } = useLocale();
  const { mode, view } = useControlCenterData("LIVE");
  const [selected, setSelected] = useState<string | null>(null);

  const available = view.evidence.available;
  const eventCount = view.evidence.eventCount;
  const auditCount = view.evidence.auditCount;

  return (
    <section className="cockpit-content route-content">
      <RouteHeader route="evidence" />
      <div className="route-toolbar route-toolbar--filters">
        <SourceModeNote mode={mode} />
      </div>
      <div className="route-two-column">
        <section className="evidence-records" aria-label={t.v02.route.evidence.title}>
          {!available ? (
            <p className="empty-state empty-state--unavailable">{t.bridge.activityUnavailable}</p>
          ) : (eventCount ?? 0) === 0 && (auditCount ?? 0) === 0 ? (
            <p className="empty-state">{t.bridge.noActivity}</p>
          ) : (
            <article className="evidence-record" key="evidence-summary">
              <div>
                <p className="action-kicker">{t.bridge.evidence} · {mode === "DEMO" ? DEMO_LABEL : t.bridge.liveValue}</p>
                <h2>{t.bridge.evidence}</h2>
                <p>{t.bridge.readOnlyBridge}</p>
                <div className="evidence-record__meta">
                  <StatusBadge tone="verified">{t.bridge.available}</StatusBadge>
                  <span>{t.bridge.evidence}: {(eventCount ?? 0) + (auditCount ?? 0)}</span>
                </div>
              </div>
              <button type="button" className="button-secondary" onClick={() => setSelected(t.bridge.evidence)}>
                {t.v02.actions.openEvidence}
              </button>
            </article>
          )}
        </section>
        {selected && (
          <DetailPanel title={selected} onClose={() => setSelected(null)}>
            <p className="detail-summary">{t.bridge.readOnlyBridge}</p>
          </DetailPanel>
        )}
      </div>
    </section>
  );
}

export function ProjectsScreen() {
  return <CockpitShell><ProjectsSurface /></CockpitShell>;
}
export function ApprovalsScreen() {
  return <CockpitShell><ApprovalsSurface /></CockpitShell>;
}
export function EvidenceScreen() {
  return <CockpitShell><EvidenceScreenInner /></CockpitShell>;
}

// Small alias to keep the export name stable while using the inner component.
function EvidenceScreenInner() {
  return <EvidenceSurface />;
}
