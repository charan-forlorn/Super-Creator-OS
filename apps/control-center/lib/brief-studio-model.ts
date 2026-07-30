// Cohort 10K — plain-language Brief Studio copy model.
//
// Deterministic Thai-first question/preset model. This module is PURE:
// no network, no browser storage, no randomness, no authority. Every
// readiness state and recommended default is computed by the Python
// authority and arrives through the brief projection; this file only
// supplies the words the operator reads.

export type BriefFieldKind = "chips" | "text" | "textarea" | "date";

export interface BriefField {
  readonly key: string;
  readonly kind: BriefFieldKind;
  readonly label: string;
  readonly hint: string;
  readonly example?: string;
  readonly options?: readonly string[];
  readonly required?: boolean;
  readonly allowUnsure?: boolean;
}

export interface BriefStepDef {
  readonly id: string;
  readonly title: string;
  readonly lead: string;
  readonly fields: readonly BriefField[];
}

export const UNSURE = "ยังไม่แน่ใจ";

export const GOAL_OPTIONS = [
  "วิดีโอโปรโมตสินค้า",
  "วิดีโอให้ความรู้",
  "วิดีโอรีวิว",
  "วิดีโอประกาศโปรโมชั่น",
  "คอนเทนต์โซเชียล",
  "อื่น ๆ",
] as const;

export const STYLE_OPTIONS = [
  "เรียบง่ายและน่าเชื่อถือ",
  "ทันสมัย",
  "เป็นกันเอง",
  "พรีเมียม",
  "สนุกและรวดเร็ว",
  "ให้ความรู้",
  UNSURE,
] as const;

export const CHANNEL_OPTIONS = [
  "TikTok / Reels / Shorts",
  "Facebook / Instagram feed",
  "YouTube",
  "เว็บไซต์",
  "นำเสนอในร้าน",
  UNSURE,
] as const;

export const RIGHTS_QUESTIONS = [
  { key: "asset_owner", label: "ภาพและวิดีโอที่จะใช้ เป็นของใคร", hint: "ถ้าไม่ใช่ของคุณเอง ต้องมีสิทธิ์ใช้งานที่ชัดเจน", options: ["Owned", "Licensed", "Not sure"] },
  { key: "identifiable_person", label: "มีคนที่จำหน้าได้อยู่ในงานหรือไม่", hint: "ถ้ามี ต้องได้รับความยินยอมจากเจ้าตัวก่อน", options: ["No", "Yes", "Not sure"] },
  { key: "voice_used", label: "ใช้เสียงของคนจริงหรือไม่", hint: "เสียงคนจริงถือเป็นข้อมูลส่วนบุคคล", options: ["Not used", "Used with consent", "Not sure"] },
  { key: "music_used", label: "ใช้เพลงหรือดนตรีประกอบหรือไม่", hint: "เพลงที่ไม่มีสิทธิ์ใช้งานอาจถูกลบหรือถูกฟ้องภายหลัง", options: ["Not used", "Licensed", "Not sure"] },
  { key: "font_policy", label: "ฟอนต์ที่จะใช้มีสิทธิ์ใช้งานเชิงพาณิชย์หรือไม่", hint: "ฟอนต์ฟรีบางตัวห้ามใช้เชิงพาณิชย์", options: ["Licensed", "Open source", "Not sure"] },
] as const;

export const PRIVACY_QUESTIONS = [
  { key: "health_data", label: "มีข้อมูลสุขภาพของบุคคลหรือไม่", hint: "ข้อมูลสุขภาพเป็นข้อมูลอ่อนไหวสูง", options: ["No", "Yes", "Not sure"] },
  { key: "financial_data", label: "มีข้อมูลการเงินส่วนบุคคลหรือไม่", hint: "เช่น เลขบัญชี ยอดหนี้ รายได้ของบุคคล", options: ["No", "Yes", "Not sure"] },
  { key: "government_identifiers", label: "มีเลขบัตรประชาชนหรือเอกสารราชการหรือไม่", hint: "ห้ามนำมาใช้ในงานประเภทนี้", options: ["No", "Yes", "Not sure"] },
  { key: "child_information", label: "มีข้อมูลของเด็กหรือไม่", hint: "ข้อมูลเด็กต้องได้รับความยินยอมจากผู้ปกครอง", options: ["No", "Yes", "Not sure"] },
] as const;

export const RIGHTS_UNSURE_VALUE = "Not sure";

export const BRIEF_STEPS: readonly BriefStepDef[] = [
  {
    id: "goal",
    title: "คุณอยากสร้างอะไร",
    lead: "เลือกแบบที่ใกล้เคียงที่สุด หรือพิมพ์อธิบายด้วยคำพูดของคุณเองก็ได้",
    fields: [
      { key: "goal", kind: "chips", label: "ประเภทงานที่ต้องการ", hint: "เลือกหนึ่งข้อ", options: GOAL_OPTIONS, required: true },
      { key: "goal_detail", kind: "textarea", label: "อยากเล่าเพิ่มไหม", hint: "ไม่บังคับ", example: "เช่น อยากได้คลิปสั้นแนะนำน้ำสมุนไพรขวดใหม่ของร้าน" },
    ],
  },
  {
    id: "audience",
    title: "ใครควรได้เห็นงานนี้",
    lead: "บอกสั้น ๆ ด้วยภาษาปกติ ไม่ต้องใช้ศัพท์การตลาด",
    fields: [
      { key: "audience", kind: "text", label: "คนดูคือใคร", hint: "บอกเป็นคำพูดธรรมดา", example: "เช่น แม่บ้านวัย 30-45 ปีที่ซื้อของออนไลน์", required: true },
      { key: "audience_problem", kind: "textarea", label: "เขามีปัญหาอะไรอยู่", hint: "ไม่บังคับ", example: "เช่น หาของกินเพื่อสุขภาพที่รสชาติดีไม่ได้" },
      { key: "audience_feeling", kind: "text", label: "อยากให้คนดูรู้สึกอย่างไร", hint: "ไม่บังคับ", example: "เช่น รู้สึกว่าน่าลอง และเชื่อถือได้" },
      { key: "audience_next_step", kind: "text", label: "ดูจบแล้วอยากให้เขาทำอะไรต่อ", hint: "ไม่บังคับ", example: "เช่น ทักแชทมาสั่งซื้อ" },
    ],
  },
  {
    id: "message",
    title: "ข้อความหลักคืออะไร",
    lead: "เขียนสิ่งที่อยากให้คนดูจำให้ได้แม้ดูแค่ครั้งเดียว",
    fields: [
      { key: "main_point", kind: "textarea", label: "ประโยคหลักที่อยากให้จำ", hint: "หนึ่งประโยคก็พอ", example: "เช่น ชาสมุนไพรสูตรใหม่ หวานน้อย ดื่มง่ายทุกวัน", required: true },
      { key: "offer", kind: "text", label: "มีโปรโมชั่นหรือข้อมูลสำคัญไหม", hint: "ไม่บังคับ", example: "เช่น ซื้อ 2 แถม 1 ถึงสิ้นเดือน" },
      { key: "call_to_action", kind: "text", label: "อยากให้ปิดท้ายด้วยประโยคอะไร", hint: "ไม่บังคับ", example: "เช่น ทักแชทเลยวันนี้" },
      { key: "required_wording", kind: "textarea", label: "มีคำที่ต้องใช้ตรงตัวไหม", hint: "ไม่บังคับ", example: "เช่น ชื่อแบรนด์เต็ม" },
      { key: "avoid_wording", kind: "textarea", label: "มีคำหรือคำกล่าวอ้างที่ห้ามใช้ไหม", hint: "ไม่บังคับ", example: "เช่น ห้ามบอกว่ารักษาโรคได้" },
    ],
  },
  {
    id: "style",
    title: "อยากให้งานออกมาแนวไหน",
    lead: "ถ้ายังไม่แน่ใจ เลือก “ยังไม่แน่ใจ” ได้ ระบบจะแนะนำแนวที่ปลอดภัยให้ก่อน",
    fields: [
      { key: "style_tone", kind: "chips", label: "อารมณ์ของงาน", hint: "เลือกหนึ่งข้อ", options: STYLE_OPTIONS, allowUnsure: true },
      { key: "style_colors", kind: "text", label: "มีสีที่อยากให้ใช้ไหม", hint: "ไม่บังคับ พิมพ์ชื่อสีธรรมดาได้", example: "เช่น เขียวอ่อนกับขาว" },
      { key: "style_font_feel", kind: "text", label: "อยากให้ตัวหนังสือดูแบบไหน", hint: "ไม่บังคับ", example: "เช่น อ่านง่าย ดูสะอาด" },
      { key: "style_reference", kind: "textarea", label: "มีงานที่ชอบเป็นตัวอย่างไหม", hint: "ไม่บังคับ เล่าเป็นคำพูดได้", example: "เช่น แบบคลิปรีวิวที่พูดตรง ๆ ไม่ตัดเร็วเกินไป" },
      { key: "style_avoid", kind: "textarea", label: "มีแบบที่ไม่อยากได้ไหม", hint: "ไม่บังคับ", example: "เช่น ไม่อยากได้เพลงดังจนกลบเสียงพูด" },
    ],
  },
  {
    id: "channel",
    title: "จะเอาไปใช้ที่ไหน",
    lead: "ระบบจะเลือกสัดส่วนภาพและความยาวที่เหมาะสมให้เอง",
    fields: [
      { key: "channel", kind: "chips", label: "ช่องทางที่จะใช้", hint: "เลือกหนึ่งข้อ", options: CHANNEL_OPTIONS, required: true, allowUnsure: true },
    ],
  },
  {
    id: "assets",
    title: "ไฟล์และวัตถุดิบที่มี",
    lead: "ระบบจะแสดงเฉพาะชื่อไฟล์แบบปลอดภัย ไม่แสดงที่อยู่ไฟล์ในเครื่อง",
    fields: [
      { key: "asset_notes", kind: "textarea", label: "อยากบอกอะไรเกี่ยวกับไฟล์ไหม", hint: "ไม่บังคับ", example: "เช่น โลโก้อยู่ในโฟลเดอร์ที่ผู้ดูแลเตรียมไว้แล้ว" },
    ],
  },
  {
    id: "schedule",
    title: "กำหนดเวลาและเงื่อนไข",
    lead: "บอกวันที่ต้องการให้งานเสร็จ เพื่อให้วางลำดับงานได้",
    fields: [
      { key: "deadline", kind: "date", label: "อยากให้เสร็จวันไหน", hint: "จำเป็นต้องระบุ", required: true },
      { key: "campaign_date", kind: "date", label: "มีวันสำคัญของแคมเปญไหม", hint: "ไม่บังคับ" },
      { key: "max_duration", kind: "text", label: "อยากให้ยาวไม่เกินเท่าไร", hint: "ไม่บังคับ", example: "เช่น ไม่เกิน 30 วินาที" },
      { key: "revision_note", kind: "text", label: "คาดว่าจะขอแก้กี่รอบ", hint: "ไม่บังคับ", example: "เช่น ประมาณ 2 รอบ" },
      { key: "special_instruction", kind: "textarea", label: "มีข้อกำหนดพิเศษไหม", hint: "ไม่บังคับ" },
    ],
  },
  {
    id: "rights",
    title: "สิทธิ์ ความยินยอม และความเป็นส่วนตัว",
    lead: "ส่วนนี้ตอบว่า “ยังไม่แน่ใจ” ไม่ได้ ระบบจะไม่สร้างโปรเจกต์จนกว่าคำตอบจะชัดเจน เพื่อป้องกันปัญหาทางกฎหมาย",
    fields: [],
  },
];

export const REVIEW_SECTION_TITLES: Readonly<Record<string, string>> = {
  goal: "เป้าหมายของงาน",
  audience: "กลุ่มผู้ชม",
  message: "ข้อความหลัก",
  style: "สไตล์",
  channel: "ช่องทางและรูปแบบ",
  assets: "ไฟล์ที่มี",
  schedule: "กำหนดเวลา",
  rights: "สิทธิ์และความเป็นส่วนตัว",
};

export const STATE_LABEL: Readonly<Record<string, string>> = {
  READY: "พร้อมแล้ว",
  NEEDS_INFORMATION: "ต้องการข้อมูลเพิ่ม",
  BLOCKED_FOR_RIGHTS: "ติดเรื่องสิทธิ์",
  BLOCKED_FOR_PRIVACY: "ติดเรื่องความเป็นส่วนตัว",
  BLOCKED_FOR_ASSETS: "ติดเรื่องไฟล์",
  CREATED: "สร้างแล้ว",
  CREATION_OUTCOME_UNKNOWN: "ผลการสร้างยังไม่แน่ชัด",
};

export const STATE_GLYPH: Readonly<Record<string, string>> = {
  READY: "✓",
  NEEDS_INFORMATION: "!",
  BLOCKED_FOR_RIGHTS: "✕",
  BLOCKED_FOR_PRIVACY: "✕",
  BLOCKED_FOR_ASSETS: "✕",
  CREATED: "★",
  CREATION_OUTCOME_UNKNOWN: "?",
};

/** Browser-safe, plain-language mapping of authoritative error codes. */
export function safeErrorMessage(code: string | null): string {
  switch (code) {
    case "DRAFT_NOT_FOUND":
      return "ไม่พบบรีฟนี้ อาจถูกลบไปแล้ว หรือลิงก์ไม่ถูกต้อง กรุณาเริ่มบรีฟใหม่";
    case "CONFLICTING_REPLAY_REJECTED":
      return "บรีฟนี้ถูกสร้างเป็นโปรเจกต์ไปแล้วด้วยคำสั่งอื่น ระบบจึงไม่สร้างซ้ำ";
    case "ADMISSION_BLOCKED":
      return "ยังมีบางส่วนที่ยังไม่ผ่านเงื่อนไข ระบบจึงยังไม่สร้างโปรเจกต์ให้";
    case "CREATION_OUTCOME_UNKNOWN":
      return "ผลการสร้างยังไม่แน่ชัด กรุณาแจ้งผู้ดูแลให้ตรวจสอบก่อนกดสร้างอีกครั้ง";
    case "REQUEST_TOO_LARGE":
      return "ข้อมูลที่กรอกยาวเกินไป กรุณาย่อข้อความลงแล้วลองใหม่";
    case "REQUEST_FAILED":
    case "BRIDGE_SPAWN_FAILED":
    case "BRIDGE_TIMEOUT":
    case "BRIDGE_OUTPUT_TOO_LARGE":
    case "BRIDGE_INVALID_RESPONSE":
      return "ตอนนี้ระบบเบื้องหลังไม่ตอบสนอง ข้อมูลล่าสุดยังไม่ถูกบันทึก กรุณาลองกดบันทึกอีกครั้ง";
    default:
      return "ทำรายการไม่สำเร็จ กรุณาลองอีกครั้ง หากยังไม่ได้ให้แจ้งผู้ดูแล";
  }
}
