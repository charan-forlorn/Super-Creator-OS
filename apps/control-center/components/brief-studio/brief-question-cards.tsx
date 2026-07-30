"use client";

// Cohort 10K — presentational question cards for the Brief Studio.
// Pure rendering: no fetch, no storage, no authority. Every value comes from
// the parent orchestrator, which in turn reflects authoritative state.

import type { BriefField, BriefStepDef } from "@/lib/brief-studio-model";
import { PRIVACY_QUESTIONS, RIGHTS_QUESTIONS, UNSURE } from "@/lib/brief-studio-model";
import type { BriefRecommendation } from "@/lib/paid-pilot-intake-types";

function Chips({
  field,
  value,
  onChange,
}: Readonly<{ field: BriefField; value: string; onChange: (v: string) => void }>) {
  return (
    <div className="brief-chips" role="radiogroup" aria-label={field.label}>
      {(field.options ?? []).map((opt) => (
        <button
          key={opt}
          type="button"
          role="radio"
          aria-checked={value === opt}
          className={`brief-chip${value === opt ? " is-selected" : ""}${opt === UNSURE ? " brief-chip--unsure" : ""}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function FieldBlock({
  field,
  value,
  onChange,
  recommendation,
}: Readonly<{
  field: BriefField;
  value: string;
  onChange: (v: string) => void;
  recommendation?: BriefRecommendation;
}>) {
  const id = `brief-field-${field.key}`;
  const describedBy = `${id}-hint`;
  return (
    <div className="brief-field">
      <label className="brief-field__label" htmlFor={id}>
        {field.label}
        {field.required ? <span className="brief-field__required"> · จำเป็น</span> : <span className="brief-field__optional"> · ไม่บังคับ</span>}
      </label>
      <p className="brief-field__hint" id={describedBy}>
        {field.hint}
        {field.example ? ` — ${field.example}` : ""}
      </p>
      {field.kind === "chips" ? (
        <>
          <input type="hidden" id={id} value={value} readOnly />
          <Chips field={field} value={value} onChange={onChange} />
        </>
      ) : null}
      {field.kind === "text" ? (
        <input id={id} className="brief-input" type="text" value={value} aria-describedby={describedBy} onChange={(e) => onChange(e.target.value)} />
      ) : null}
      {field.kind === "date" ? (
        <input id={id} className="brief-input" type="date" value={value} aria-describedby={describedBy} onChange={(e) => onChange(e.target.value)} />
      ) : null}
      {field.kind === "textarea" ? (
        <textarea id={id} className="brief-input brief-input--area" rows={3} value={value} aria-describedby={describedBy} onChange={(e) => onChange(e.target.value)} />
      ) : null}
      {recommendation ? (
        <p className="brief-recommendation">
          <span className="brief-recommendation__badge">{recommendation.label}</span>
          <span>
            {" "}
            ระบบเลือก “{recommendation.value}” ให้ก่อน — {recommendation.reason}
          </span>
        </p>
      ) : null}
    </div>
  );
}

export function BriefQuestionCards({
  step,
  answers,
  onAnswer,
  recommendations,
  rightsAnswers,
  privacyAnswers,
  onRights,
  onPrivacy,
  assetNames,
  assetSummaryText,
  onRefreshAssets,
  assetBusy,
}: Readonly<{
  step: BriefStepDef;
  answers: Record<string, string>;
  onAnswer: (key: string, value: string) => void;
  recommendations: BriefRecommendation[];
  rightsAnswers: Record<string, string>;
  privacyAnswers: Record<string, string>;
  onRights: (key: string, value: string) => void;
  onPrivacy: (key: string, value: string) => void;
  assetNames: string[];
  assetSummaryText: string;
  onRefreshAssets: () => void;
  assetBusy: boolean;
}>) {
  const recFor = (key: string) => recommendations.find((r) => r.field === key);
  return (
    <div className="brief-cards">
      {step.fields.map((f) => (
        <FieldBlock key={f.key} field={f} value={answers[f.key] ?? ""} onChange={(v) => onAnswer(f.key, v)} recommendation={recFor(f.key)} />
      ))}

      {step.id === "assets" ? (
        <div className="brief-field">
          <p className="brief-field__label">ไฟล์ที่ระบบตรวจพบ</p>
          <p className="brief-asset-summary">{assetSummaryText}</p>
          {assetNames.length > 0 ? (
            <ul className="brief-asset-list">
              {assetNames.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : (
            <p className="brief-field__hint">ยังไม่มีไฟล์ที่พร้อมใช้งาน</p>
          )}
          <button type="button" className="brief-button brief-button--secondary" onClick={onRefreshAssets} disabled={assetBusy}>
            {assetBusy ? "กำลังตรวจสอบไฟล์…" : "ตรวจสอบไฟล์อีกครั้ง"}
          </button>
        </div>
      ) : null}

      {step.id === "rights" ? (
        <div className="brief-rights">
          {RIGHTS_QUESTIONS.map((q) => (
            <fieldset key={q.key} className="brief-fieldset">
              <legend className="brief-field__label">{q.label}</legend>
              <p className="brief-field__hint">{q.hint}</p>
              <div className="brief-chips" role="radiogroup" aria-label={q.label}>
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    role="radio"
                    aria-checked={rightsAnswers[q.key] === opt}
                    className={`brief-chip${rightsAnswers[q.key] === opt ? " is-selected" : ""}${opt === "Not sure" ? " brief-chip--unsure" : ""}`}
                    onClick={() => onRights(q.key, opt)}
                  >
                    {opt === "Not sure" ? UNSURE : opt}
                  </button>
                ))}
              </div>
              {rightsAnswers[q.key] === "Not sure" ? (
                <p className="brief-blocker" role="alert">
                  ข้อนี้ตอบว่ายังไม่แน่ใจไม่ได้ — ระบบจะไม่สร้างโปรเจกต์จนกว่าจะตอบชัดเจน กรุณาตรวจสอบกับเจ้าของงานก่อน
                </p>
              ) : null}
            </fieldset>
          ))}
          {PRIVACY_QUESTIONS.map((q) => (
            <fieldset key={q.key} className="brief-fieldset">
              <legend className="brief-field__label">{q.label}</legend>
              <p className="brief-field__hint">{q.hint}</p>
              <div className="brief-chips" role="radiogroup" aria-label={q.label}>
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    role="radio"
                    aria-checked={privacyAnswers[q.key] === opt}
                    className={`brief-chip${privacyAnswers[q.key] === opt ? " is-selected" : ""}${opt === "Not sure" ? " brief-chip--unsure" : ""}`}
                    onClick={() => onPrivacy(q.key, opt)}
                  >
                    {opt === "Not sure" ? UNSURE : opt}
                  </button>
                ))}
              </div>
              {privacyAnswers[q.key] === "Not sure" ? (
                <p className="brief-blocker" role="alert">
                  ข้อนี้ตอบว่ายังไม่แน่ใจไม่ได้ — ต้องตรวจสอบให้แน่ชัดก่อน เพื่อไม่ให้ละเมิดความเป็นส่วนตัว
                </p>
              ) : null}
            </fieldset>
          ))}
        </div>
      ) : null}
    </div>
  );
}
