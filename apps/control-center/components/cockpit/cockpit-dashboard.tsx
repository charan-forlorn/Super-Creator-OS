"use client";

import { useState } from "react";
import { useLocale } from "@/lib/i18n";
import { OrbitMascot } from "@/components/cockpit/orbit-mascot";
import { CockpitShell } from "@/components/cockpit/cockpit-shell";
import {
  DEMO_LABEL,
  useControlCenterData,
  type CockpitView,
} from "@/lib/control-center-snapshot";

function StatusDot({
  status,
}: Readonly<{ status: "completed" | "in-progress" | "waiting" | "blocked" | "degraded" | "unavailable" | "empty" }>) {
  return <span className={`status-dot status-dot--${status}`} aria-hidden="true" />;
}

function SourceModeBadge({ mode, observedAt }: { mode: "LIVE" | "DEMO"; observedAt: string | null }) {
  if (mode === "DEMO") {
    return (
      <span className="source-mode-badge source-mode-badge--demo" role="status" aria-live="polite">
        {DEMO_LABEL}
      </span>
    );
  }
  return (
    <span className="source-mode-badge source-mode-badge--live" title={observedAt ?? ""}>
      <i /> Live local read-only{observedAt ? ` · ${observedAt}` : ""}
    </span>
  );
}

function sectionTone(s: CockpitView["health"]["status"]): "completed" | "in-progress" | "waiting" | "blocked" | "degraded" | "unavailable" | "empty" {
  switch (s) {
    case "AVAILABLE_WITH_DATA":
      return "completed";
    case "AVAILABLE_EMPTY":
      return "empty";
    case "DEGRADED":
      return "degraded";
    case "UNAVAILABLE":
    case "ERROR":
      return "unavailable";
    default:
      return "waiting";
  }
}

function CockpitSurface() {
  const { t, locale, setLocale } = useLocale();
  const { mode, setMode, view, loadState, lastUpdatedAt, refresh, errorMessage } = useControlCenterData("LIVE");
  const [feedback, setFeedback] = useState<string | null>(null);

  function toggleMode() {
    setMode(mode === "LIVE" ? "DEMO" : "LIVE");
    setFeedback(t.bridge.modeSwitched);
  }

  const healthTone = sectionTone(view.health.status);
  const queueTone = sectionTone(view.queue.status);
  const approvalTone = sectionTone(view.approvals.status);
  const activityTone = sectionTone(view.activity.status);

  return (
    <>
      <section className="cockpit-content">
        <header className="cockpit-header">
          <div>
            <p className="cockpit-overline">
              {t.dashboard.greeting} <span>·</span> {t.dashboard.date}
            </p>
            <h1>{t.dashboard.title}</h1>
          </div>
          <div className="cockpit-header__controls">
            <SourceModeBadge mode={mode} observedAt={lastUpdatedAt} />
            <button type="button" className="button-secondary" onClick={toggleMode} aria-pressed={mode === "DEMO"}>
              {mode === "LIVE" ? t.bridge.switchToDemo : t.bridge.switchToLive}
            </button>
            {mode === "LIVE" && (
              <button type="button" className="button-secondary" onClick={refresh}>
                {t.bridge.refresh}
              </button>
            )}
            <div className="locale-switcher" role="group" aria-label={t.languageSwitcher}>
              <button type="button" onClick={() => setLocale("th")} aria-pressed={locale === "th"}>
                {t.thai}
              </button>
              <span>|</span>
              <button type="button" onClick={() => setLocale("en")} aria-pressed={locale === "en"}>
                {t.english}
              </button>
            </div>
          </div>
        </header>

        {loadState === "loading" && (
          <div className="cockpit-state cockpit-state--loading" role="status" aria-live="polite">
            {t.bridge.loading}
          </div>
        )}
        {loadState === "error" && (
          <div className="cockpit-state cockpit-state--error" role="alert">
            {t.bridge.loadError}
            {errorMessage ? ` (${errorMessage})` : ""}
            <button type="button" className="button-secondary" onClick={refresh}>
              {t.bridge.retry}
            </button>
          </div>
        )}

        <section className="cockpit-summary" aria-label={t.dashboard.title}>
          <div>
            <span className="summary-label">{t.bridge.source}</span>
            <strong>{mode === "DEMO" ? t.bridge.demoValue : t.bridge.liveValue}</strong>
          </div>
          <div>
            <span>{t.bridge.health}</span>
            <StatusDot status={healthTone} />
            <strong>
              {view.health.available ? (view.health.healthStatus ?? t.bridge.available) : t.bridge.unavailable}
            </strong>
          </div>
          <div>
            <span>{t.bridge.queue}</span>
            <StatusDot status={queueTone} />
            <strong>
              {view.queue.available ? (view.queue.count ?? 0) : t.bridge.unavailable}
            </strong>
          </div>
          <div>
            <span>{t.bridge.approvals}</span>
            <StatusDot status={approvalTone} />
            <strong>
              {view.approvals.available ? (view.approvals.count ?? 0) : t.bridge.unavailable}
            </strong>
          </div>
          <div>
            <span>{t.bridge.evidence}</span>
            <StatusDot status={sectionTone(view.evidence.status)} />
            <strong>
              {view.evidence.available ? (view.evidence.eventCount ?? 0) : t.bridge.unavailable}
            </strong>
          </div>
        </section>

        <section className="cockpit-metrics" aria-label={t.dashboard.greeting}>
          <div>
            <StatusDot status={queueTone} />
            <span>{t.dashboard.needsYou}</span>
            <strong>{view.queue.available ? (view.queue.count ?? 0) : t.bridge.unavailable}</strong>
          </div>
          <div>
            <StatusDot status={activityTone} />
            <span>{t.dashboard.latestActivity}</span>
            <strong>{view.activity.available ? (view.activity.count ?? 0) : t.bridge.unavailable}</strong>
          </div>
          <div>
            <StatusDot status={healthTone} />
            <span>{t.bridge.health}</span>
            <strong>{view.health.available ? (view.health.healthStatus ?? t.bridge.available) : t.bridge.unavailable}</strong>
          </div>
        </section>

        <div className="cockpit-grid">
          <section className="cockpit-panel cockpit-workflow">
            <div className="panel-heading">
              <div>
                <h2>{t.dashboard.workflow}</h2>
                <p>{t.dashboard.workflowHint}</p>
              </div>
              <span className="workflow-live">
                <i />
                {t.localFirst}
              </span>
            </div>
            <div className="workflow-map">
              <article className={`workflow-node workflow-node--${healthTone}`}>
                <div className="workflow-node__top">
                  <StatusDot status={healthTone} />
                  <span>{t.bridge.backend}</span>
                </div>
                <h3>{t.bridge.backend}</h3>
                <p className="workflow-role">{t.bridge.readOnlyBridge}</p>
                <div className="workflow-progress">
                  <span
                    style={{
                      width: `${view.health.available ? (view.health.blockerCount ? 60 : 100) : 10}%`,
                    }}
                  />
                </div>
                <small>
                  {t.dashboard.progress}{" "}
                  {view.health.available ? (view.health.blockerCount ? 60 : 100) : 0}%
                </small>
              </article>
            </div>
          </section>

          <aside className="cockpit-side-stack">
            <section className="cockpit-panel next-action">
              <p className="action-kicker">{t.action.label}</p>
              <h2>{t.action.title}</h2>
              <p className="awaiting">
                <StatusDot status={approvalTone} />
                {view.approvals.available
                  ? t.bridge.approvalsAvailable(view.approvals.count ?? 0)
                  : t.bridge.approvalsUnavailable}
              </p>
              <div className="action-buttons">
                <button type="button" className="button-primary" onClick={() => setFeedback(t.feedback.review)}>
                  {t.action.review}
                </button>
                <button type="button" className="button-secondary" onClick={() => setFeedback(t.feedback.changes)}>
                  {t.action.requestChanges}
                </button>
              </div>
            </section>
            <section className="cockpit-panel orbit-briefing">
              <OrbitMascot state="attention" size={120} />
              <div>
                <p className="action-kicker">{t.orbit.title}</p>
                <p>{mode === "DEMO" ? t.bridge.demoBriefing : t.bridge.liveBriefing}</p>
              </div>
            </section>
          </aside>
        </div>

        <section className="cockpit-panel activity-panel">
          <div className="panel-heading">
            <div>
              <h2>{t.dashboard.latestActivity}</h2>
            </div>
            {view.activity.status === "UNAVAILABLE" && (
              <span className="cockpit-note cockpit-note--unavailable">{t.bridge.unavailable}</span>
            )}
          </div>
          <div className="activity-list">
            {view.activity.available && view.activity.items && view.activity.items.length > 0 ? (
              view.activity.items.map((item) => (
                <div className={`activity-row activity-row--${item.status === "ok" ? "success" : "info"}`} key={item.activity_id}>
                  <span className="activity-row__signal" />
                  <p>{item.summary}</p>
                </div>
              ))
            ) : (
              <p className="empty-state">
                {view.activity.available ? t.bridge.noActivity : t.bridge.activityUnavailable}
              </p>
            )}
          </div>
        </section>

        {mode === "DEMO" && <p className="cockpit-note cockpit-note--demo" role="status">{DEMO_LABEL}</p>}
      </section>
      {feedback && (
        <div className="cockpit-toast" role="status">
          <div>
            <p>{feedback}</p>
          </div>
          <button type="button" onClick={() => setFeedback(null)}>
            {t.close}
          </button>
        </div>
      )}
    </>
  );
}

export function CockpitDashboard() {
  return (
    <CockpitShell>
      <CockpitSurface />
    </CockpitShell>
  );
}
