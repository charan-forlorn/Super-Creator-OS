"use client";

import { useState } from "react";
import { COCKPIT_ACTIVITY, COCKPIT_AGENTS, COCKPIT_APPROVAL, COCKPIT_EVIDENCE, COCKPIT_PROJECTS, COCKPIT_TASKS, ORBIT_BRIEFING } from "@/lib/cockpit-mock-data";
import type { EvidenceItem, ProjectId } from "@/lib/cockpit-types";
import { useLocale } from "@/lib/i18n";
import { OrbitMascot } from "@/components/cockpit/orbit-mascot";
import { CockpitShell } from "@/components/cockpit/cockpit-shell";

function StatusDot({ status }: Readonly<{ status: "completed" | "in-progress" | "waiting" | "blocked" }>) { return <span className={`status-dot status-dot--${status}`} aria-hidden="true" />; }

function CockpitSurface() {
  const { locale, setLocale, t } = useLocale();
  const [project, setProject] = useState<ProjectId>("scos-core");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null);
  const activeProject = COCKPIT_PROJECTS.find((item) => item.id === project) ?? COCKPIT_PROJECTS[0];
  const completed = COCKPIT_TASKS.filter((item) => item.status === "completed").length + 2;
  const active = COCKPIT_TASKS.filter((item) => item.status === "in-progress").length;
  const needsYou = COCKPIT_TASKS.filter((item) => item.status === "waiting").length;

  function chooseProject(value: ProjectId) { setProject(value); setFeedback(t.feedback.project); }

  return (
    <>
      <section className="cockpit-content">
        <header className="cockpit-header">
          <div><p className="cockpit-overline">{t.dashboard.greeting} <span>·</span> {t.dashboard.date}</p><h1>{t.dashboard.title}</h1></div>
          <div className="cockpit-header__controls"><label className="project-select"><span>{t.projectLabel}</span><select value={project} onChange={(event) => chooseProject(event.target.value as ProjectId)}>{COCKPIT_PROJECTS.map((item) => <option key={item.id} value={item.id}>{t.projects[item.id]} · {item.stage}</option>)}</select></label><div className="locale-switcher" role="group" aria-label={t.languageSwitcher}><button type="button" onClick={() => setLocale("th")} aria-pressed={locale === "th"}>{t.thai}</button><span>|</span><button type="button" onClick={() => setLocale("en")} aria-pressed={locale === "en"}>{t.english}</button></div></div>
        </header>

        <section className="cockpit-summary" aria-label={t.dashboard.title}>
          <div><span className="summary-label">{activeProject.stage}</span><strong>{t.projectStates[activeProject.state]}</strong></div><div><span>{t.summary.stage8r}</span><StatusDot status="completed" /></div><div><span>{t.summary.stage8s}</span><StatusDot status="waiting" /></div><div><span>{t.summary.latestCommit}</span><code>00aafbb</code></div><div><span>{t.summary.evidence}</span><strong>25 tests passed</strong></div>
        </section>

        <section className="cockpit-metrics" aria-label={t.dashboard.greeting}>
          <div><StatusDot status="in-progress" /><span>{t.dashboard.running}</span><strong>{active}</strong></div><div><StatusDot status="waiting" /><span>{t.dashboard.needsYou}</span><strong>{needsYou}</strong></div><div><StatusDot status="completed" /><span>{t.dashboard.completed}</span><strong>{completed}</strong></div>
        </section>

        <div className="cockpit-grid">
          <section className="cockpit-panel cockpit-workflow"><div className="panel-heading"><div><h2>{t.dashboard.workflow}</h2><p>{t.dashboard.workflowHint}</p></div><span className="workflow-live"><i />{t.localFirst}</span></div><div className="workflow-map">{COCKPIT_AGENTS.map((agent, index) => <div className="workflow-node-wrap" key={agent.id}>{index > 0 && <span className="workflow-connector" aria-hidden="true" />}<article className={`workflow-node workflow-node--${agent.status}`}><div className="workflow-node__top"><StatusDot status={agent.status} /><span>{t.status[agent.status]}</span></div><h3>{t.agents[agent.id].name}</h3><p className="workflow-role">{t.agents[agent.id].role}</p><p className="workflow-note">{t.agents[agent.id].note}</p><div className="workflow-progress"><span style={{ width: `${agent.progress}%` }} /></div><small>{t.dashboard.progress} {agent.progress}%</small></article></div>)}</div></section>

          <aside className="cockpit-side-stack">
            <section className="cockpit-panel next-action"><p className="action-kicker">{t.action.label}</p><h2>{t.action.title}</h2><p className="awaiting"><StatusDot status="waiting" />{t.action.awaiting}</p><div className="evidence-preview"><span>{t.action.evidencePreview}</span>{COCKPIT_APPROVAL.evidenceIds.map((id) => { const evidence = COCKPIT_EVIDENCE.find((item) => item.id === id); return <button type="button" key={id} onClick={() => { if (evidence) { setSelectedEvidence(evidence); setFeedback(t.feedback.evidence); } }}>{id === "hvs-render" ? t.action.hvsPlaceholder : evidence?.value}</button>; })}</div><div className="action-buttons"><button type="button" className="button-primary" onClick={() => setFeedback(t.feedback.review)}>{t.action.review}</button><button type="button" className="button-secondary" onClick={() => setFeedback(t.feedback.changes)}>{t.action.requestChanges}</button></div></section>
            <section className="cockpit-panel orbit-briefing"><OrbitMascot state={ORBIT_BRIEFING.state} size={120} /><div><p className="action-kicker">{t.orbit.title}</p><p>{t.orbit[ORBIT_BRIEFING.state]}</p></div></section>
          </aside>
        </div>

        <section className="cockpit-panel activity-panel"><div className="panel-heading"><div><h2>{t.dashboard.latestActivity}</h2></div></div><div className="activity-list">{COCKPIT_ACTIVITY.map((entry) => <div className={`activity-row activity-row--${entry.tone}`} key={entry.id}><span className="activity-row__signal" /><p>{t.activity[entry.id]}</p></div>)}</div></section>
        <section className="evidence-rail" aria-label={t.evidence.title}><h2>{t.evidence.title}</h2><div>{COCKPIT_EVIDENCE.map((item) => <button type="button" className="evidence-item" key={item.id} onClick={() => { setSelectedEvidence(item); setFeedback(t.feedback.evidence); }}><span>{t.evidence.labels[item.id]}</span><strong>{item.value}</strong></button>)}</div></section>
      </section>
      {(feedback || selectedEvidence) && <div className="cockpit-toast" role="status"><div>{feedback && <p>{feedback}</p>}{selectedEvidence && <p><strong>{t.evidence.labels[selectedEvidence.id]}:</strong> {t.evidence.details[selectedEvidence.id]}</p>}</div><button type="button" onClick={() => { setFeedback(null); setSelectedEvidence(null); }}>{t.close}</button></div>}
    </>
  );
}

export function CockpitDashboard() { return <CockpitShell><CockpitSurface /></CockpitShell>; }
