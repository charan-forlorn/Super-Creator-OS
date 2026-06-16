# Data Accumulation Phase — Super Creator OS

> สถานะ: Closed Loop ทำงานแล้ว (forward + backward) · Video Analyst ยังไม่สร้าง
> เป้าหมายของเฟสนี้: **สะสมข้อมูลคุณภาพสูงจากงานจริง** จนถึงจุดที่ Video Analyst
> เปิดใช้แล้วเจอ pattern จริง ไม่ใช่ noise
>
> ข้อกำหนด: **ห้ามเพิ่ม feature ใหม่ · ห้ามแก้ core architecture** — ทุกอย่างใน
> เอกสารนี้เป็น *additive schema* + *กฎ* + *แผน* บนสิ่งที่มีอยู่แล้ว

---

## 0. Architectural Insight ที่กำหนดทั้งเฟส

ระบบตอนนี้ปิด loop บน **predicted retention** เท่านั้น:

```
retention_score (0–100)  =  Retention Expert เดา ก่อนโพสต์
```

แต่ไม่มี **observed retention** (ของจริงหลังโพสต์: avg watch time, completion rate, ยอดวิว)
และ record ไม่ได้จำว่า **มันใช้ recommendation ตัวไหน** จาก forward loop

> ผลคือ: Video Analyst จะ correlate ไม่ได้ว่า *"ทำแบบไหน → retention จริงเท่าไร"*
> มันเห็นแค่ *"เราเดาว่าเท่าไร"*

เฟสนี้จึงเติม 2 สิ่งที่ขาด โดยไม่แตะ core:

1. **Provenance** — record จำได้ว่าใช้ reference / hook ตัวไหนจาก `recommendation_service`
2. **Observed telemetry** — outcome จริงจากแพลตฟอร์ม เก็บใน sidecar คู่ขนาน (`memory/telemetry.json`)

ทั้งสองอย่างคือสิ่งที่ทำให้เกิด **causal chain เรียนรู้ได้**:

```
seed (hook/ref ที่แนะนำ) → decision (ที่ทำจริง) → predicted score → OBSERVED outcome
```

---

## 1. Data Collection Architecture

### 1.1 หลักการ — One Funnel, Append-Only, Sidecar for Outcomes

```
                         ┌─────────────────────────────┐
   STEP 1.5  ───────────▶│  recommendation_service     │  (forward)
   (brief)               │  → creative_seed            │
                         └──────────────┬──────────────┘
                                        │ seed ถูกถือไว้ตลอด job (provenance)
                                        ▼
   STEP 2–14  ──────────▶  สร้างจริง (story/timeline/render/QA)
                                        │
   STEP 12–15 ──────────▶┌─────────────────────────────┐
                         │  learning_manager           │  (backward)
                         │  → build_record (predicted) │
                         │  → safe_append database.json│  ◀── APPEND-ONLY (ห้ามแก้)
                         │  → events.jsonl             │
                         └──────────────┬──────────────┘
                                        │
   หลังโพสต์ 24–72 ชม. ─▶┌─────────────────────────────┐
                         │  telemetry.json (sidecar)   │  ◀── OBSERVED outcome
                         │  join key: project_name+created_at
                         └─────────────────────────────┘
```

### 1.2 กฎเหล็ก 3 ข้อ (รับประกัน "100% ผ่าน loop")

| # | กฎ | ทำไม / บังคับด้วยอะไร |
|---|----|----|
| **C-1** | ทุกโปรเจกต์ที่มี EDL+render **ต้องจบผ่าน `learning_manager.process_project`** เท่านั้น ห้าม append `database.json` ด้วยมือ | เป็นทางเดียวที่ผลิต v2 fields + emit events ครบ |
| **C-2** | ทุกโปรเจกต์ต้อง emit **terminal event อย่างใดอย่างหนึ่ง**: `PROJECT_COMPLETE` (ผ่าน) หรือ `PROJECT_QA_FAILED` (ตก) | ทำให้ reconcile ได้ว่ามีงานไหน "หลุด loop" |
| **C-3** | `creative_seed` จาก STEP 1.5 ต้องถูกแนบกลับมาที่ STEP 15 เป็น `provenance` (ดู §2.2) | สร้าง causal link ระหว่าง decision กับ outcome |

> **100% coverage วัดได้** = จำนวน render ใน `output/` ที่มี `PROJECT_COMPLETE`/`PROJECT_QA_FAILED`
> ใน `events.jsonl` ตรงกัน (ดู DQ-1 และ Dashboard §8)

### 1.3 ทำไมใช้ sidecar ไม่ใช่แก้ record

`database.json` เป็น **append-only, 1 โปรเจกต์ = 1 record** (กฎใน `schema.md`).
Observed metrics มาทีหลัง 24–72 ชม. → ถ้าจะเขียนกลับเข้า record เดิมต้อง "แก้ของเก่า" = ผิดกฎ + เสี่ยง corrupt.
**คำตอบ:** เก็บ observed ใน `memory/telemetry.json` แยก, join ตอนวิเคราะห์.
core architecture ไม่ถูกแตะเลย, v1/v2 contract ยังคงเดิม 100%.

---

## 2. Telemetry Schema (v2 → v3)

### 2.1 หลัก schema evolution

- **v3 = v2 + ทุกฟิลด์ใหม่เป็น OPTIONAL** (เหมือนหลักการ `schema_v2_extension.md`)
- record เก่า (v1/v2) ที่ไม่มีฟิลด์ v3 → ยัง valid 100%, อ่านด้วย `.get(field, default)`
- เพิ่ม `schema_version: "v3"` เป็น marker (ถ้าไม่มี = ถือเป็น ≤ v2)
- `validators.V1_REQUIRED` **ไม่เปลี่ยน** → contract เดิมยังถูกบังคับเหมือนเดิม

### 2.2 ฟิลด์ใหม่ใน record (`database.json`) — provenance (เขียนตอน STEP 15)

ทั้งหมด optional, มาจาก `creative_seed` ที่ forward loop คืนให้:

```jsonc
{
  // ...v2 fields เดิมทั้งหมด...
  "schema_version": "v3",
  "provenance": {
    "reference_project": "MOBA Pentakill — Hype Flex Edit (RoV)", // seed.reference_project
    "match_quality": "exact",            // exact | near | none — มาจาก seed.match_quality
    "match_score": 1.0,                  // seed.match_score
    "suggested_hooks": ["Double Kill"],  // phrase ที่ seed แนะนำ (suggested_hooks_next_time)
    "hooks_actually_used": ["Double Kill"], // hook ที่ใช้จริง (จาก storytelling)
    "reused_editing_specs": true,        // เอา editing_specs_to_reuse มาใช้จริงไหม
    "loop_run_id": "2026-06-15T12:25:50.000Z::moba-pentakill" // = created_at::slug (join key)
  }
}
```

> **`hooks_actually_used` vs `suggested_hooks` คือหัวใจ** — บอกว่าคำแนะนำถูก *adopt* หรือถูก *ปฏิเสธ*
> เมื่อมี observed outcome แล้ว จะตอบได้ว่า "ทำตามคำแนะนำ → ผลดีขึ้นไหม"

### 2.3 Sidecar ใหม่ `memory/telemetry.json` — observed outcome (เขียนหลังโพสต์)

โครงสร้าง: array ของ object, join กับ record ด้วย `loop_run_id` (หรือ `project_name`+`created_at`):

```jsonc
[
  {
    "loop_run_id": "2026-06-15T12:25:50.000Z::moba-pentakill",
    "project_name": "MOBA Pentakill — Hype Flex Edit (RoV)",
    "platform": "tiktok",                 // tiktok | reels | shorts | youtube
    "posted_at": "2026-06-15T20:30:00Z",
    "measured_at": "2026-06-18T20:30:00Z", // วัดเมื่อไร (snapshot)
    "window_h": 72,                        // เก็บที่กี่ชั่วโมงหลังโพสต์
    "observed": {
      "views": 18400,
      "avg_watch_time_s": 11.2,
      "avg_watch_pct": 46,                 // = avg_watch_time_s / output_duration_s
      "completion_rate_pct": 19,           // % ที่ดูจนจบ
      "rewatch_rate_pct": 8,
      "likes": 1230, "saves": 410, "shares": 220, "comments": 95,
      "ctr_pct": null                      // ถ้าแพลตฟอร์มไม่ให้ = null (อย่าเดา)
    },
    "outcome_label": "hit",                // hit | normal | flop — derived (ดู §3.4)
    "source": "manual"                     // manual | api — provenance ของ telemetry เอง
  }
]
```

> **ทำไมแยกไฟล์:** observed มาทีหลัง + อาจวัดหลายครั้ง (24h, 72h, 7d) → array ต่อโปรเจกต์ได้
> โดยไม่ละเมิดกฎ "1 record / โปรเจกต์" ของ `database.json`

---

## 3. Metrics ที่ต้องเก็บต่อโปรเจกต์

แบ่ง 4 ชั้น — ชั้น A/B/C มีอยู่/กึ่งมีแล้ว, ชั้น D คือสิ่งที่เฟสนี้เพิ่ม:

### 3.1 A — Identity & Provenance (ใหม่บางส่วน, §2.2)
`project_name, product_niche, created_at, loop_run_id, schema_version, engine, clip_type,
reference_project, match_quality, suggested_hooks, hooks_actually_used`

### 3.2 B — Process / Decision (มีแล้วใน v2)
`grade_used, cut_padding_ms, subtitle_style, render_specs{resolution,fps,output_duration_s},
edl_path, transcribed`

### 3.3 C — Predicted & Structural (มีแล้วใน v2)
`retention_score (predicted), qa_pass, render_success,
retention_signals{num_segments, avg_segment_s, kept_speech_s, source_total_s,
kept_ratio_pct, output_duration_s, has_cold_open},
highlight_anchors[{t,label,kind}]`

### 3.4 D — Observed Outcome (ใหม่, sidecar §2.3)
`views, avg_watch_time_s, avg_watch_pct, completion_rate_pct, rewatch_rate_pct,
likes, saves, shares, comments, outcome_label`

**Derived (คำนวณตอนวิเคราะห์ ไม่เก็บซ้ำ):**
- `prediction_error = retention_score − avg_watch_pct` → จูน Retention Expert
- `outcome_label`: `hit` ถ้า `avg_watch_pct ≥ niche_p75`, `flop` ถ้า `≤ niche_p25`, ที่เหลือ `normal`
- `hook_adoption = hooks_actually_used ⊆ suggested_hooks ?`

---

## 4. Data Quality Rules

บังคับ/ตรวจได้ด้วยของที่มีอยู่ (`validators.py`, `events.jsonl`, dry-run) — ไม่ต้องเขียน feature ใหม่:

| ID | กฎ | ระดับ | ตรวจด้วย |
|----|----|------|---------|
| **DQ-1** | ทุก render ใน `output/` มี `PROJECT_COMPLETE` หรือ `PROJECT_QA_FAILED` ใน `events.jsonl` | **BLOCK** | reconcile output/ ↔ event log |
| **DQ-2** | record ผ่าน `validators.validate_record` (v1 ครบ, `retention_score` int 0–100) | **BLOCK** | มีแล้วใน `safe_append` |
| **DQ-3** | `render_success=true` **ก่อน** ยอมเขียน memory (FAIL → ไม่เขียน) | **BLOCK** | มีแล้วใน learning_manager |
| **DQ-4** | ถ้า `clip_type=gaming_*` → ต้องมี `highlight_anchors` ≥ 1 (callout) | **WARN** | DQ report |
| **DQ-5** | `retention_signals.kept_ratio_pct` อยู่ใน 5–95 (นอกช่วง = น่าจะ extract ผิด) | **WARN** | DQ report |
| **DQ-6** | `avg_watch_pct` ใน telemetry อยู่ 0–100 และ `output_duration_s>0` | **BLOCK telemetry** | DQ report |
| **DQ-7** | `provenance.suggested_hooks` ที่ไม่ว่าง → ต้องมี `hooks_actually_used` (adopt หรือ reject ก็ได้ แต่ต้องบันทึก) | **WARN** | DQ report |
| **DQ-8** | ไม่มี `loop_run_id` ซ้ำใน `database.json` (กัน record ซ้ำจาก re-run) | **BLOCK** | DQ report |
| **DQ-9** | telemetry ทุกแถว join กับ record ได้ (ไม่มี orphan) | **WARN** | DQ report |
| **DQ-10** | `product_niche` สะกดตรงกับ niche canonical list (กัน "Gaming(MOBA)" vs "Gaming (MOBA)") | **WARN** | DQ report |

> **DQ-10 สำคัญต่อ pattern mining** — niche ที่สะกดเพี้ยนทำให้ข้อมูลกระจัดกระจาย
> ควรมี **canonical niche list** (เริ่มจาก key ใน `highlight_anchor_library.json`)

---

## 5. Dataset Milestones

วัดเป็น **record ที่ render_success + มี observed telemetry** (ไม่ใช่แค่จำนวน append):

| Milestone | เกณฑ์ | ปลดล็อกอะไร |
|-----------|------|-------------|
| **M0 — Instrumented** | v3 provenance + sidecar เริ่มเก็บครบทุกงานใหม่ | เริ่มนับเวลาสะสมจริง |
| **M1 — First Signal** | ≥ **10** โปรเจกต์/niche เดียว มี observed | เห็น distribution retention ของ niche เดียว |
| **M2 — Niche Viable** | ≥ **30** โปรเจกต์ใน niche เดียว (มี hit & flop ทั้งคู่ ≥ 5 อย่างละ) | คำนวณ p25/p75 → `outcome_label` เชื่อถือได้ |
| **M3 — Cross-Niche** | ≥ **3 niche** ผ่าน M2 | เทียบ pattern ข้าม niche ได้ |
| **M4 — Analyst-Ready** | M2 อย่างน้อย 1 niche + DQ pass-rate ≥ 95% + prediction_error วัดได้ | **เปิด Video Analyst** (ดู §6) |

> ตัวเลข 30/niche มาจาก: ต้องการ ≥ 5 hit + ≥ 5 flop ต่อ niche เพื่อให้ correlation ของ
> hook/grade/segment มี signal เหนือ noise (rule-of-thumb น้อยสุดต่อ subgroup)

---

## 6. Readiness Criteria for Video Analyst

Video Analyst เปิดได้เมื่อ **ครบทุกข้อ** (gate):

- [ ] **R-1 Coverage:** DQ-1 pass-rate = 100% ใน 30 งานล่าสุด (ทุกงานผ่าน loop จริง)
- [ ] **R-2 Volume:** ≥ 1 niche ผ่าน **M2** (30 โปรเจกต์, มี hit&flop)
- [ ] **R-3 Ground truth:** ≥ 80% ของ record ใน niche นั้นมี observed telemetry (ไม่ใช่แค่ predicted)
- [ ] **R-4 Provenance:** ≥ 80% ของ record มี `provenance.hooks_actually_used` (ไม่งั้น correlate ไม่ได้)
- [ ] **R-5 Quality:** DQ-2..DQ-10 รวม pass-rate ≥ 95%
- [ ] **R-6 Niche hygiene:** canonical niche list นิ่ง (DQ-10 = 0 violation)

> ถ้า R-2/R-3 ยังไม่ถึง → Video Analyst จะ output pattern ที่ overfit กับ 2–3 ตัวอย่าง = อันตรายกว่าไม่มี
> Video Analyst subscribe `HIGHLIGHT_PATTERN_DISCOVERED` + `PROJECT_COMPLETE` (มีใน Event Bus แล้ว) — ไม่ต้องแก้ loop

---

## 7. ข้อมูลมูลค่าสูงสุดต่อการค้นหา Retention Patterns

เรียงตาม signal-to-effort (เก็บอันบนสุดให้ครบก่อน):

| อันดับ | ข้อมูล | ทำไมมูลค่าสูง |
|-------|--------|---------------|
| **1** | `observed.avg_watch_pct` + `completion_rate_pct` | **ground truth เดียว** ที่บอกว่า "ดูจริงนานแค่ไหน" — ทุก pattern ต้อง correlate กับตัวนี้ |
| **2** | `provenance.hooks_actually_used` ↔ outcome | ตอบคำถามแกน: hook แบบไหนทำให้คนดูต่อ ในแต่ละ niche |
| **3** | `retention_signals.has_cold_open` + `avg_segment_s` ↔ outcome | โครงสร้างตัดต่อ (cold-open?, จังหวะตัด) vs retention — actionable ที่สุด |
| **4** | `highlight_anchors` (t, label, kind) ↔ outcome | จังหวะ beat ไหน = peak จริง → reuse เป็น cold-open รอบหน้า |
| **5** | `grade_used` / `subtitle_style` ↔ outcome | look/subtitle มีผลรองแต่ทำซ้ำได้ง่าย |
| **6** | `prediction_error` (predicted − observed) | จูน Retention Expert ให้แม่นขึ้น (meta-learning) |
| **7** | `posted_at` (ชั่วโมงโพสต์) ↔ views | timing pattern ต่อ niche (สอดคล้อง lesson_learned เดิม) |

> สังเกต: ทุกอันมูลค่าสูง **เพราะมันถูก correlate กับ observed outcome (อันดับ 1)** — ถ้าไม่มี
> ground truth, อันดับ 2–7 กลายเป็นแค่ descriptive ที่เรียนรู้ไม่ได้ ⇒ ยืนยัน insight §0

---

## 8. Data Quality Dashboard / Report

รายงานเดียว (อ่านจาก `database.json` + `telemetry.json` + `events.jsonl`, read-only) แสดง:

### Panel 1 — Loop Coverage (DQ-1)
```
Renders in output/ : 32
PROJECT_COMPLETE   : 30   PROJECT_QA_FAILED : 1
⚠ Orphan renders   : 1   ← งานที่ "หลุด loop" ต้องตามเก็บ
Coverage           : 96.9%   (target 100%)
```

### Panel 2 — Quality Scorecard (DQ-2..DQ-10)
ตาราง DQ-id × pass/warn/fail count + pass-rate รวม (เกณฑ์ ≥95%)

### Panel 3 — Niche Progress (vs Milestones)
```
niche              | records | w/ observed | hits | flops | milestone
Gaming (MOBA)      |   14    |    11       |  4   |   3   | → M1, ขาด 16 ถึง M2
Pet Accessories    |    6    |     5       |  2   |   1   | → M1
...
```

### Panel 4 — Ground Truth Fill-Rate
`% record ที่มี observed telemetry` (target ≥80% ต่อ active niche) — ตัวเลขที่บอกว่า "พร้อมเปิด Analyst ไหม"

### Panel 5 — Prediction Calibration
scatter/aggregate `retention_score (predicted)` vs `avg_watch_pct (observed)` + mean abs error ต่อ niche

### Panel 6 — Hook Adoption
`% งานที่ adopt suggested hook` และ adopt แล้ว hit-rate เทียบ reject — feedback ว่า recommendation มีประโยชน์จริงไหม

> สร้างได้ภายหลังเป็น read-only report script (ไม่ใช่ feature ของ OS, ไม่แตะ loop) เมื่อถึง M0

---

## 9. Recommended Next 30 Projects Plan

เป้า: ดัน **1 niche ให้ถึง M2 (30 records) เร็วที่สุด** + เก็บ breadth พอให้ M3 เริ่มได้
เลือก **Gaming (MOBA)** เป็น niche หลัก (มี reference ดีสุดแล้ว: retention 84, มี anchor library, มี clip_type เฉพาะ)

| ช่วง | จำนวน | Niche | จุดประสงค์ |
|------|------|-------|-----------|
| 1–18 | 18 | **Gaming (MOBA)** | ดันให้ใกล้ M2 (รวมของเดิม → ~20+) เก็บ hit/flop จริง ทดสอบ reuse editing_specs |
| 19–24 | 6 | **Gaming (FPS)** | ทดสอบ near-match (forward loop fuzzy) ข้าม sub-niche |
| 25–30 | 6 | 2nd niche (เช่น Podcast/Finance ที่มี hooks ใน library) | เริ่มสะสมไปสู่ M3 cross-niche |

### กฎระหว่างเก็บ 30 งาน (เพื่อให้ได้ "ข้อมูลคุณภาพสูง" ไม่ใช่แค่จำนวน)

1. **ทุกงานจบผ่าน `learning_manager`** (C-1) — ไม่มีข้อยกเว้น
2. **บันทึก `hooks_actually_used` ทุกครั้ง** ว่า adopt หรือ reject seed (C-3)
3. **เก็บ observed telemetry ที่ 72 ชม.** ลง `telemetry.json` ทุกงาน (ขาดข้อนี้ = งานนั้นเรียนรู้ไม่ได้)
4. **จงใจสร้าง variance:** อย่าทำเหมือนกันทั้ง 18 งาน — สลับ has_cold_open / avg_segment_s /
   hook ต่างกัน เพื่อให้มี contrast ให้ Analyst เห็น (ข้อมูลที่เหมือนกันหมด = เรียนรู้อะไรไม่ได้)
5. **รัน DQ report ทุก 5 งาน** — แก้ niche สะกดเพี้ยน/orphan ทันที ก่อนสะสมหนี้คุณภาพ

### Definition of Done ของเฟส
ครบ 30 งานแล้ว Gaming (MOBA) ผ่าน **M2** + **R-1..R-6 = pass** → **เปิด Video Analyst (Phase 3)**

---

## ภาคผนวก — สรุปสิ่งที่ "เพิ่ม" ในเฟสนี้ (ยืนยันว่าไม่ละเมิดข้อกำหนด)

| สิ่งที่เพิ่ม | ประเภท | แตะ core ไหม |
|-------------|--------|-------------|
| `schema_version`, `provenance{}` ใน record | optional field (additive) | ไม่ — `V1_REQUIRED` คงเดิม |
| `memory/telemetry.json` | sidecar file ใหม่ | ไม่ — `database.json` ไม่ถูกแก้ |
| DQ rules, milestones, readiness, dashboard | กฎ/เอกสาร/รายงาน read-only | ไม่ |
| 4 forward events | (เพิ่มไปแล้วในงานก่อนหน้า) | ไม่ |

ไม่มี feature ใหม่ใน OS · ไม่มีการแก้ loop · เน้นสะสม ground-truth + provenance จากงานจริง
