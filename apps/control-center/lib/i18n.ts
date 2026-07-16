"use client";

import { createContext, createElement, useContext, useEffect, useMemo, useState } from "react";
import { en } from "@/lib/messages/en";
import { th } from "@/lib/messages/th";
import type { Locale } from "@/lib/cockpit-types";

export interface MessageDictionary {
  appName: string; productName: string; languageSwitcher: string; thai: string; english: string; workspace: string; localFirst: string; projectLabel: string;
  nav: Record<"today" | "projects" | "agents" | "workflows" | "evidence" | "approvals" | "activity" | "settings", string>;
  dashboard: Record<"greeting" | "title" | "date" | "running" | "needsYou" | "completed" | "workflow" | "workflowHint" | "progress" | "latestActivity", string>;
  projects: Record<"scos-core" | "orbit-lab", string>; projectStates: Record<"certified" | "awaiting-review", string>;
  summary: Record<"stage8r" | "stage8s" | "latestCommit" | "evidence", string>;
  status: Record<"completed" | "in-progress" | "waiting" | "blocked", string>;
  agents: Record<"hermes" | "claude" | "codex" | "hvs" | "n8n", { name: string; role: string; note: string }>;
  action: Record<"label" | "title" | "awaiting" | "evidencePreview" | "review" | "requestChanges" | "hvsPlaceholder", string>;
  orbit: Record<"title" | "normal" | "attention" | "success", string>;
  evidence: { title: string; details: Record<"tests" | "commit" | "hvs-render" | "n8n-run", string>; labels: Record<"tests" | "commit" | "hvs-render" | "n8n-run", string> };
  activity: Record<"certification" | "build" | "review", string>;
  feedback: Record<"review" | "changes" | "project" | "evidence", string>;
  bridge: {
    source: string; liveValue: string; demoValue: string; health: string; queue: string; approvals: string; evidence: string;
    available: string; unavailable: string; loading: string; loadError: string; retry: string; refresh: string;
    switchToDemo: string; switchToLive: string; modeSwitched: string;
    backend: string; readOnlyBridge: string; liveBriefing: string; demoBriefing: string;
    noActivity: string; activityUnavailable: string;
    approvalsAvailable: (count: number) => string; approvalsUnavailable: string;
  };
  v02: {
    demo: string; route: Record<"projects" | "approvals" | "evidence", { title: string; description: string }>;
    filters: { all: string; active: string; needsYou: string; completed: string; status: string; source: string; };
    labels: Record<"purpose" | "stage" | "status" | "lead" | "lastActivity" | "nextAction" | "evidence" | "risk" | "blocker" | "details" | "priority" | "requestedBy" | "reason" | "scope" | "deadline" | "result" | "timestamp" | "technical" | "source" | "activity" | "mockData", string>;
    projectStatus: Record<"active" | "healthy" | "needs-you" | "completed", string>;
    priorities: Record<"high" | "medium" | "low", string>;
    risks: Record<"high" | "medium" | "low" | "none", string>;
    decisions: Record<"pending" | "approved" | "changes-requested" | "rejected", string>;
    evidenceStatus: Record<"verified" | "passed" | "healthy", string>;
    sources: Record<"hermes" | "codex" | "git" | "hvs" | "n8n", string>;
    projectData: Record<"scos-hvs" | "hermes-factory" | "client-video", { name: string; purpose: string; nextAction: string; risk: string; blocker: string }>;
    approvalData: Record<"stage-8s" | "asset-rights" | "weekly-schedule", { title: string; reason: string; scope: string; evidence: string; activity: string }>;
    evidenceData: Record<"stage-8r" | "stage-8s-tests" | "commit-00aafbb" | "hvs-render" | "n8n-schedule", { title: string; type: string; summary: string; metadata: string }>;
    actions: Record<"approve" | "requestChanges" | "reject" | "openEvidence" | "copyValue" | "closePanel", string>;
    feedback: Record<"projectSelected" | "approvalApproved" | "approvalChanges" | "approvalRejected" | "evidenceOpened" | "copied", string>;
    empty: string;
  };
  close: string;
}

const messages: Record<Locale, MessageDictionary> = { en, th };
const LocaleContext = createContext<{ locale: Locale; setLocale: (locale: Locale) => void; t: MessageDictionary } | null>(null);

export function LocaleProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [locale, setLocale] = useState<Locale>("th");
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const value = useMemo(() => ({ locale, setLocale, t: messages[locale] }), [locale]);
  return createElement(LocaleContext.Provider, { value }, children);
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("useLocale must be used inside LocaleProvider");
  return context;
}
