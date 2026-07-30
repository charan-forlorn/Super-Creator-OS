"use client";

// Cohort 10K — plain-language brief summary panel.
// Pure projection of authoritative state. No fetch, no storage, no JSON/YAML.

import { REVIEW_SECTION_TITLES, STATE_GLYPH, STATE_LABEL } from "@/lib/brief-studio-model";
import type { BriefProjection } from "@/lib/paid-pilot-intake-types";

function line(label: string, value: string) {
  return (
    <p className="brief-summary__line" key={label}>
      <span className="brief-summary__key">{label}</span>
      <span className="brief-summary__value">{value.trim() ? value : "ยังไม่ได้ระบุ"}</span>
    </p>
  );
}

export function BriefSummaryPanel({
  brief,
  onJump,
  showAdvanced,
  onToggleAdvanced,
}: Readonly<{
  brief: BriefProjection | null;
  onJump: (sectionId: string) => void;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
}>) {
  if (!brief) {
    return (
      <aside className="brief-summary" aria-label="สรุปบรีฟ">
        <h2 className="brief-summary__title">สรุปบรีฟ</h2>
        <p className="brief-summary__empty">ยังไม่มีข้อมูล เริ่มตอบคำถามด้านซ้ายได้เลย</p>
      </aside>
    );
  }
  const a = brief.answers;
  const blockers = brief.sections.filter((s) => s.blocking);
  return (
    <aside className="brief-summary" aria-label="สรุปบรีฟ">
      <h2 className="brief-summary__title">สรุปบรีฟ</h2>

      <p className="brief-readiness" role="status" aria-live="polite">
        <span className="brief-readiness__count">{brief.readiness_label}</span>
      </p>

      <ul className="brief-checklist">
        {brief.sections.map((s) => (
          <li key={s.id} className={`brief-checklist__item brief-checklist__item--${s.state.toLowerCase()}`}>
            <button type="button" className="brief-checklist__jump" onClick={() => onJump(s.id)}>
              <span className="brief-checklist__glyph" aria-hidden="true">
                {STATE_GLYPH[s.state] ?? "!"}
              </span>
              <span className="brief-checklist__name">{REVIEW_SECTION_TITLES[s.id] ?? s.heading}</span>
              <span className="brief-checklist__state">{STATE_LABEL[s.state] ?? s.state}</span>
            </button>
          </li>
        ))}
      </ul>

      <section className="brief-summary__block">
        <h3>เนื้อหาที่บันทึกไว้</h3>
        {line("เป้าหมายของงาน", a.goal ?? "")}
        {line("กลุ่มผู้ชม", a.audience ?? "")}
        {line("ข้อความหลัก", a.main_point ?? "")}
        {line("สไตล์", a.style_tone ?? "")}
        {line("ช่องทาง", a.channel ?? "")}
        {line("กำหนดเวลา", a.deadline ?? "")}
      </section>

      <section className="brief-summary__block">
        <h3>ไฟล์ที่มี</h3>
        <p className="brief-summary__line">
          <span className="brief-summary__key">พร้อมใช้งาน</span>
          <span className="brief-summary__value">{brief.assets.available} ไฟล์</span>
        </p>
        {brief.assets.needs_review > 0 ? (
          <p className="brief-summary__line">
            <span className="brief-summary__key">ต้องตรวจสอบ</span>
            <span className="brief-summary__value">{brief.assets.needs_review} ไฟล์</span>
          </p>
        ) : null}
        {brief.assets.unsupported > 0 ? (
          <p className="brief-summary__line">
            <span className="brief-summary__key">ใช้ไม่ได้</span>
            <span className="brief-summary__value">{brief.assets.unsupported} ไฟล์</span>
          </p>
        ) : null}
        {brief.assets.available === 0 ? <p className="brief-summary__value">ยังไม่มีไฟล์ที่พร้อมใช้งาน</p> : null}
      </section>

      {blockers.length > 0 ? (
        <section className="brief-summary__block" aria-live="polite">
          <h3>สิ่งที่ยังติดอยู่</h3>
          {blockers.map((s) => (
            <div className="brief-blocker" role="alert" key={s.id}>
              <strong>{REVIEW_SECTION_TITLES[s.id] ?? s.heading}</strong>
              <span> — {s.detail || s.why_it_matters}</span>
              <span className="brief-blocker__how"> วิธีแก้: {s.how_to_resolve}</span>
            </div>
          ))}
        </section>
      ) : null}

      {brief.recommendations.length > 0 ? (
        <section className="brief-summary__block">
          <h3>คำแนะนำของระบบ</h3>
          {brief.recommendations.map((r) => (
            <p className="brief-summary__line" key={r.field}>
              <span className="brief-recommendation__badge">{r.label}</span>
              <span className="brief-summary__value"> {r.value}</span>
            </p>
          ))}
        </section>
      ) : null}

      <section className="brief-summary__block">
        <h3>สิ่งที่ระบบจะไม่ทำอัตโนมัติ</h3>
        <ul className="brief-notdo">
          {brief.will_not_do.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </section>

      <section className="brief-summary__block">
        <button type="button" className="brief-advanced-toggle" aria-expanded={showAdvanced} onClick={onToggleAdvanced}>
          รายละเอียดเพิ่มเติม
        </button>
        {showAdvanced ? (
          <div className="brief-advanced">
            <p className="brief-field__hint">ส่วนนี้เป็นข้อมูลอ่านอย่างเดียว ระบบเลือกให้จากช่องทางที่คุณเลือก</p>
            {line("รูปแบบงาน", brief.resolved_output.selected_template)}
            {line("ช่องทางปลายทาง", brief.resolved_output.target_platform)}
            {line("สัดส่วนภาพ", brief.resolved_output.output_profile)}
            {line("ความยาวโดยประมาณ", brief.resolved_output.duration)}
          </div>
        ) : null}
      </section>
    </aside>
  );
}
