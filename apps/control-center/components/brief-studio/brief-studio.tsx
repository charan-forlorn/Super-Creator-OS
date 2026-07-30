"use client";

// Cohort 10K — Brief Studio orchestrator.
//
// AUTHORITY CONTRACT
//   * This component is a COLLECTOR and a PROJECTION SURFACE only.
//   * The Python guided-intake service remains the sole authoritative writer.
//   * No localStorage / sessionStorage / IndexedDB / cookie carries workflow truth.
//   * Resume identity is the authoritative opaque `?draft_id=` only.
//   * A failed save is never rendered as saved.
//   * One confirmation creates at most one authoritative Pilot identity.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  attachConsentEvidence,
  createIntakeDraft,
  createPilotFromDraft,
  getIntakeDraft,
  refreshAssetInventory,
  saveBriefSection,
  updateIntakeDraft,
} from "@/lib/paid-pilot-intake-client";
import type { BriefProjection, GuidedIntakeDraft, IntakeResponse } from "@/lib/paid-pilot-intake-types";
import { BRIEF_STEPS, REVIEW_SECTION_TITLES, STATE_GLYPH, STATE_LABEL, safeErrorMessage } from "@/lib/brief-studio-model";
import { BriefQuestionCards } from "@/components/brief-studio/brief-question-cards";
import { BriefSummaryPanel } from "@/components/brief-studio/brief-summary-panel";

type SaveState = "IDLE" | "SAVING" | "SAVED" | "FAILED";
const REVIEW_INDEX = BRIEF_STEPS.length; // review step
const CONFIRM_INDEX = BRIEF_STEPS.length + 1; // confirm step
const TOTAL_STEPS = BRIEF_STEPS.length + 2;

const DEFAULT_RIGHTS: Record<string, string> = {};
const DEFAULT_PRIVACY: Record<string, string> = {};

function briefOf(draft: GuidedIntakeDraft | null): BriefProjection | null {
  const b = draft?.generated?.brief;
  return b && typeof b === "object" ? (b as BriefProjection) : null;
}

export function BriefStudio({ initialDraftId }: Readonly<{ initialDraftId?: string }>) {
  const [draft, setDraft] = useState<GuidedIntakeDraft | null>(null);
  const [draftId, setDraftId] = useState<string>(initialDraftId ?? "");
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [rights, setRights] = useState<Record<string, string>>(DEFAULT_RIGHTS);
  const [privacy, setPrivacy] = useState<Record<string, string>>(DEFAULT_PRIVACY);
  const [saveState, setSaveState] = useState<SaveState>("IDLE");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [notice, setNotice] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(Boolean(initialDraftId));
  const [busy, setBusy] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [created, setCreated] = useState<{ pilot: string; project: string } | null>(null);
  const inFlight = useRef(false);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const errorRef = useRef<HTMLParagraphElement | null>(null);

  const brief = briefOf(draft);

  const absorb = useCallback((res: IntakeResponse): boolean => {
    if (res.ok && res.draft) {
      setDraft(res.draft);
      setDraftId(res.draft.draft_id);
      if (res.draft.brief_answers) setAnswers({ ...res.draft.brief_answers });
      if (res.draft.rights_answers && Object.keys(res.draft.rights_answers).length > 0) setRights({ ...res.draft.rights_answers });
      if (res.draft.privacy_answers && Object.keys(res.draft.privacy_answers).length > 0) setPrivacy({ ...res.draft.privacy_answers });
      setErrorMessage("");
      return true;
    }
    setErrorMessage(safeErrorMessage(res.error_code));
    return false;
  }, []);

  // Authoritative hydration from the URL identity. No browser storage is read.
  useEffect(() => {
    if (!initialDraftId) return;
    let alive = true;
    (async () => {
      const res = await getIntakeDraft(initialDraftId);
      if (!alive) return;
      absorb(res);
      if (res.ok && res.draft?.status === "CREATED") {
        setCreated({ pilot: res.draft.pilot_safe_id, project: res.draft.project_safe_id });
        setStepIndex(CONFIRM_INDEX);
      }
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [initialDraftId, absorb]);

  const publishIdentity = useCallback((id: string) => {
    if (typeof window === "undefined" || !id) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("draft_id") === id) return;
    url.searchParams.set("draft_id", id);
    window.history.replaceState(null, "", url.toString());
  }, []);

  /** Single in-flight authoritative save of the current section. */
  const persist = useCallback(
    async (sectionId: string): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setSaveState("SAVING");
      try {
        let id = draftId;
        if (!id) {
          const created0 = await createIntakeDraft({ safe_project_title: (answers.goal_detail || answers.goal || "บรีฟใหม่").slice(0, 80), commercial_reference: "brief-studio" });
          if (!absorb(created0) || !created0.draft) {
            setSaveState("FAILED");
            return false;
          }
          id = created0.draft.draft_id;
        }
        const res = await saveBriefSection(id, sectionId, answers);
        if (!absorb(res)) {
          setSaveState("FAILED");
          return false;
        }
        if (sectionId === "rights") {
          const upd = await updateIntakeDraft(id, { rights_answers: rights, privacy_answers: privacy });
          if (!absorb(upd)) {
            setSaveState("FAILED");
            return false;
          }
        }
        publishIdentity(id);
        setSaveState("SAVED");
        return true;
      } finally {
        inFlight.current = false;
      }
    },
    [answers, draftId, privacy, rights, absorb, publishIdentity],
  );

  const currentStep = stepIndex < BRIEF_STEPS.length ? BRIEF_STEPS[stepIndex] : null;
  const sectionState = useMemo(() => {
    if (!brief || !currentStep) return null;
    return brief.sections.find((s) => s.id === currentStep.id) ?? null;
  }, [brief, currentStep]);

  const focusAfterNav = useCallback(() => {
    window.requestAnimationFrame(() => headingRef.current?.focus());
  }, []);

  const goNext = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (currentStep) {
        const ok = await persist(currentStep.id);
        if (!ok) {
          window.requestAnimationFrame(() => errorRef.current?.focus());
          return;
        }
      }
      setStepIndex((i) => Math.min(i + 1, CONFIRM_INDEX));
      focusAfterNav();
    } finally {
      setBusy(false);
    }
  }, [busy, currentStep, persist, focusAfterNav]);

  const goBack = useCallback(() => {
    setStepIndex((i) => Math.max(0, i - 1));
    focusAfterNav();
  }, [focusAfterNav]);

  const saveAndExit = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (currentStep) {
        const ok = await persist(currentStep.id);
        setNotice(ok ? "บันทึกแล้ว คุณปิดหน้านี้ได้ และกลับมาต่อจากลิงก์เดิมได้" : "");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, currentStep, persist]);

  const jumpTo = useCallback(
    (sectionId: string) => {
      const idx = BRIEF_STEPS.findIndex((s) => s.id === sectionId);
      if (idx >= 0) {
        setStepIndex(idx);
        focusAfterNav();
      }
    },
    [focusAfterNav],
  );

  const onRefreshAssets = useCallback(async () => {
    if (!draftId || busy) return;
    setBusy(true);
    try {
      absorb(await refreshAssetInventory(draftId));
    } finally {
      setBusy(false);
    }
  }, [draftId, busy, absorb]);

  const onConfirmConsent = useCallback(async () => {
    if (!draftId || busy) return;
    setBusy(true);
    try {
      absorb(await attachConsentEvidence(draftId, "redacted-consent.txt", "operator confirmed explicit approval", true));
    } finally {
      setBusy(false);
    }
  }, [draftId, busy, absorb]);

  const canCreate = draft?.status === "READY_TO_CREATE" && !created;

  const onCreate = useCallback(async () => {
    if (!draftId || !canCreate || busy) return;
    setBusy(true);
    try {
      const res = await createPilotFromDraft(draftId, `brief-${draftId}`);
      if (res.ok && res.draft) {
        setDraft(res.draft);
        setCreated({ pilot: res.pilot_safe_id ?? res.draft.pilot_safe_id, project: res.project_safe_id ?? res.draft.project_safe_id });
        setErrorMessage("");
      } else {
        setErrorMessage(safeErrorMessage(res.error_code));
      }
    } finally {
      setBusy(false);
    }
  }, [draftId, canCreate, busy]);

  const setAnswer = useCallback((key: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [key]: value }));
    setSaveState("IDLE");
    setNotice("");
  }, []);

  const saveBadge =
    saveState === "SAVING" ? "กำลังบันทึก…" : saveState === "SAVED" ? "บันทึกแล้ว" : saveState === "FAILED" ? "บันทึกไม่สำเร็จ" : "ยังไม่ได้บันทึก";

  const assetSummaryText = brief
    ? `พร้อมใช้งาน ${brief.assets.available} ไฟล์ · ต้องตรวจสอบ ${brief.assets.needs_review} ไฟล์ · ใช้ไม่ได้ ${brief.assets.unsupported} ไฟล์`
    : "ยังไม่มีข้อมูลไฟล์";

  if (loading) {
    return (
      <div className="brief-shell">
        <p className="brief-loading" role="status">
          กำลังเปิดบรีฟที่บันทึกไว้…
        </p>
      </div>
    );
  }

  return (
    <div className="brief-shell">
      <header className="brief-topbar">
        <div>
          <p className="brief-overline">สร้างบรีฟงานใหม่</p>
          <h1 className="brief-title">เล่าให้เราฟังว่าคุณต้องการสร้างอะไร</h1>
        </div>
        <div className="brief-topbar__right">
          <span className={`brief-savebadge brief-savebadge--${saveState.toLowerCase()}`} role="status" aria-live="polite">
            {saveBadge}
          </span>
          <Link className="brief-exit" href="/">
            กลับหน้าหลัก
          </Link>
        </div>
      </header>

      {errorMessage ? (
        <p className="brief-error" role="alert" tabIndex={-1} ref={errorRef}>
          {errorMessage}
        </p>
      ) : null}
      {notice ? (
        <p className="brief-notice" role="status">
          {notice}
        </p>
      ) : null}

      <div className="brief-layout">
        <nav className="brief-stepper" aria-label="ขั้นตอนการทำบรีฟ">
          <ol>
            {BRIEF_STEPS.map((s, i) => {
              const st = brief?.sections.find((x) => x.id === s.id);
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    className={`brief-stepper__item${i === stepIndex ? " is-current" : ""}`}
                    aria-current={i === stepIndex ? "step" : undefined}
                    onClick={() => {
                      setStepIndex(i);
                      focusAfterNav();
                    }}
                  >
                    <span className="brief-stepper__num" aria-hidden="true">
                      {st ? STATE_GLYPH[st.state] : i + 1}
                    </span>
                    <span className="brief-stepper__name">{REVIEW_SECTION_TITLES[s.id]}</span>
                    <span className="brief-stepper__state">{st ? STATE_LABEL[st.state] : "ยังไม่เริ่ม"}</span>
                  </button>
                </li>
              );
            })}
            <li>
              <button type="button" className={`brief-stepper__item${stepIndex === REVIEW_INDEX ? " is-current" : ""}`} onClick={() => setStepIndex(REVIEW_INDEX)}>
                <span className="brief-stepper__num" aria-hidden="true">
                  9
                </span>
                <span className="brief-stepper__name">ตรวจทานบรีฟ</span>
              </button>
            </li>
            <li>
              <button type="button" className={`brief-stepper__item${stepIndex === CONFIRM_INDEX ? " is-current" : ""}`} onClick={() => setStepIndex(CONFIRM_INDEX)}>
                <span className="brief-stepper__num" aria-hidden="true">
                  10
                </span>
                <span className="brief-stepper__name">ยืนยันและสร้าง</span>
              </button>
            </li>
          </ol>
        </nav>

        <main className="brief-main">
          <p className="brief-progress" aria-live="polite">
            ขั้นตอนที่ {stepIndex + 1} จาก {TOTAL_STEPS}
            {brief ? ` · ${brief.readiness_label}` : ""}
          </p>

          {currentStep ? (
            <section aria-labelledby="brief-step-heading">
              <h2 className="brief-step-title" id="brief-step-heading" tabIndex={-1} ref={headingRef}>
                {currentStep.title}
              </h2>
              <p className="brief-step-lead">{currentStep.lead}</p>
              {sectionState?.blocking ? (
                <p className="brief-blocker" role="alert">
                  {sectionState.detail || sectionState.why_it_matters} — วิธีแก้: {sectionState.how_to_resolve}
                </p>
              ) : null}
              <BriefQuestionCards
                step={currentStep}
                answers={answers}
                onAnswer={setAnswer}
                recommendations={brief?.recommendations ?? []}
                rightsAnswers={rights}
                privacyAnswers={privacy}
                onRights={(k, v) => {
                  setRights((p) => ({ ...p, [k]: v }));
                  setSaveState("IDLE");
                }}
                onPrivacy={(k, v) => {
                  setPrivacy((p) => ({ ...p, [k]: v }));
                  setSaveState("IDLE");
                }}
                assetNames={brief?.assets.names ?? []}
                assetSummaryText={assetSummaryText}
                onRefreshAssets={onRefreshAssets}
                assetBusy={busy}
              />
              {currentStep.id === "rights" ? (
                <div className="brief-field">
                  <p className="brief-field__hint">เมื่อได้รับคำอนุญาตจากเจ้าของงานแล้ว ให้ยืนยันความยินยอมเพื่อปลดล็อกการสร้างโปรเจกต์</p>
                  <button type="button" className="brief-button brief-button--secondary" onClick={onConfirmConsent} disabled={busy || !draftId}>
                    ยืนยันว่าได้รับความยินยอมแล้ว
                  </button>
                </div>
              ) : null}
            </section>
          ) : null}

          {stepIndex === REVIEW_INDEX ? (
            <section aria-labelledby="brief-step-heading">
              <h2 className="brief-step-title" id="brief-step-heading" tabIndex={-1} ref={headingRef}>
                ตรวจทานบรีฟ
              </h2>
              <p className="brief-step-lead">อ่านทวนอีกครั้ง กดที่หัวข้อใดก็ได้เพื่อกลับไปแก้</p>
              {brief ? (
                <div className="brief-review">
                  {brief.sections.map((s) => (
                    <div className="brief-review__row" key={s.id}>
                      <button type="button" className="brief-review__edit" onClick={() => jumpTo(s.id)}>
                        {REVIEW_SECTION_TITLES[s.id] ?? s.heading} · แก้ไข
                      </button>
                      <span className={`brief-review__state brief-review__state--${s.state.toLowerCase()}`}>{STATE_LABEL[s.state] ?? s.state}</span>
                      {s.blocking ? <span className="brief-review__detail">{s.detail || s.how_to_resolve}</span> : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="brief-field__hint">ยังไม่มีข้อมูลให้ตรวจทาน</p>
              )}
            </section>
          ) : null}

          {stepIndex === CONFIRM_INDEX ? (
            <section aria-labelledby="brief-step-heading">
              <h2 className="brief-step-title" id="brief-step-heading" tabIndex={-1} ref={headingRef}>
                {created ? "สร้างโปรเจกต์เรียบร้อยแล้ว" : "ยืนยันและสร้างโปรเจกต์"}
              </h2>
              {created ? (
                <div className="brief-created">
                  <p>ระบบสร้างโปรเจกต์ให้เรียบร้อยแล้ว และเก็บหลักฐานการอนุมัติไว้ในเครื่องนี้</p>
                  <p className="brief-summary__line">
                    <span className="brief-summary__key">ชื่อโปรเจกต์</span>
                    <span className="brief-summary__value">{created.project}</span>
                  </p>
                  <p className="brief-field__hint">ระบบยังไม่เรนเดอร์วิดีโอ ยังไม่ส่งงาน และยังไม่แจ้งลูกค้า จนกว่าผู้ดูแลจะสั่ง</p>
                </div>
              ) : (
                <>
                  <p className="brief-step-lead">ก่อนกดยืนยัน โปรดอ่านสรุปนี้</p>
                  <div className="brief-confirm">
                    <h3>สิ่งที่จะเกิดขึ้น</h3>
                    <ul>
                      <li>ระบบจะสร้างโปรเจกต์หนึ่งรายการจากบรีฟนี้</li>
                      <li>ระบบจะเก็บหลักฐานการอนุมัติไว้ในเครื่องนี้เท่านั้น</li>
                    </ul>
                    <h3>สิ่งที่ยังติดอยู่</h3>
                    {brief && brief.sections.some((s) => s.blocking) ? (
                      <ul>
                        {brief.sections
                          .filter((s) => s.blocking)
                          .map((s) => (
                            <li key={s.id}>
                              {REVIEW_SECTION_TITLES[s.id] ?? s.heading} — {s.detail || s.how_to_resolve}
                            </li>
                          ))}
                      </ul>
                    ) : (
                      <p className="brief-field__hint">ไม่มีรายการที่ติดอยู่</p>
                    )}
                    <h3>สิ่งที่เป็นเพียงคำแนะนำ</h3>
                    {brief && brief.recommendations.length > 0 ? (
                      <ul>
                        {brief.recommendations.map((r) => (
                          <li key={r.field}>
                            {r.value} — {r.label}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="brief-field__hint">ไม่มี</p>
                    )}
                    <h3>สิ่งที่ระบบจะไม่ทำ</h3>
                    <ul>
                      {(brief?.will_not_do ?? []).map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </div>
                  <button type="button" className="brief-button brief-button--primary" onClick={onCreate} disabled={!canCreate || busy}>
                    ยืนยันบรีฟและสร้างโปรเจกต์
                  </button>
                  {!canCreate ? <p className="brief-field__hint">ปุ่มนี้จะกดได้เมื่อทุกส่วนผ่านเงื่อนไขแล้ว</p> : null}
                </>
              )}
            </section>
          ) : null}
        </main>

        <BriefSummaryPanel brief={brief} onJump={jumpTo} showAdvanced={showAdvanced} onToggleAdvanced={() => setShowAdvanced((v) => !v)} />
      </div>

      <footer className="brief-bottombar">
        <button type="button" className="brief-button brief-button--secondary" onClick={goBack} disabled={stepIndex === 0 || busy}>
          ย้อนกลับ
        </button>
        <button type="button" className="brief-button brief-button--secondary" onClick={saveAndExit} disabled={busy || stepIndex > BRIEF_STEPS.length - 1}>
          บันทึกและออก
        </button>
        <button type="button" className="brief-button brief-button--primary" onClick={goNext} disabled={busy || stepIndex === CONFIRM_INDEX}>
          ถัดไป
        </button>
      </footer>
    </div>
  );
}
