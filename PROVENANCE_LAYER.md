# Provenance Layer — Super Creator OS

> สถานะ: **ติดตั้งแล้ว + ทดสอบผ่าน** (exact / near / cold_start, dry-run + real-write,
> append-only verified, backward-compat verified)
>
> เป้าหมาย: ทุก Memory Record ตอบได้ว่า **"ผลลัพธ์นี้เกิดจากคำแนะนำใด"**
> โดยเชื่อม forward loop (`recommendation_service`) เข้ากับ record ที่ backward loop เขียน
>
> ข้อกำหนดที่ยึด: Additive only · ไม่แก้ `V1_REQUIRED` · v3 optional · ไม่แตะ `database.json` contract

---

## 1. Architecture

```
STEP 1.5  recommendation_service.recommend()  ──▶  creative_seed
                                                      │  (exact | near | cold_start)
   storytelling/editor ตัดสินใจจริง                   │
   hooks_actually_used / reused_editing_specs ────────┤
                                                      ▼
STEP 15   learning_manager.process_project()
              │  rsvc.build_provenance(seed, decisions) ──▶ provenance/v3 block
              ▼
          render_to_memory.build_record(..., provenance=)   ← stamps schema_version=v3 + provenance
              ▼
          memory_writer.safe_append()
              │  validate_record (V1, ไม่เปลี่ยน) + validate_provenance (ใหม่, optional)
              ▼
          memory/database.json   (APPEND-ONLY — record เก่าไม่ถูกแตะ)
```

หลักการ: provenance ถูก**ประกอบจาก seed ที่มีอยู่แล้ว** ไม่มีการเก็บข้อมูลใหม่จากที่อื่น
adapter (`render_to_memory`) **ไม่ผูกกับ** `recommendation_service` — มันแค่รับ dict ที่ประกอบเสร็จแล้ว
(decoupled; provenance ถูกสร้างใน learning layer ที่ import rsvc อยู่แล้ว)

---

## 2. Schema — `provenance/v3` (optional block บน record)

```jsonc
{
  // ...v1 (required, ไม่เปลี่ยน) + v2 (optional) เดิมทั้งหมด...
  "schema_version": "v3",            // stamp เฉพาะเมื่อมี provenance
  "provenance": {
    "schema": "provenance/v3",
    "loop_run_id": "<created_at>::<slug(project_name)>",   // join key: seed ↔ record ↔ telemetry
    "recommended": {                  // มาจาก creative_seed
      "reference_project": "MOBA Pentakill — Hype Flex Edit (RoV)" | null,
      "match_quality": "exact" | "near" | "cold_start",
      "match_score": 1.0,             // 0..1 (Jaccard); cold_start = 0.0
      "suggested_hooks": ["Double Kill", "Triple Kill"],
      "retention_benchmark": 84 | null,
      "reused_editing_specs_source": "<editing_specs ที่ seed เสนอ>" | null
    },
    "decided": {                      // มาจากการตัดสินใจจริงของ storytelling/editor
      "hooks_actually_used": ["Double Kill"] | null,
      "hook_adoption": "adopted" | "partial" | "rejected" | "none_suggested" | "unrecorded",
      "reused_editing_specs": true | false | null,
      "storytelling_decision": "<free text: เลือก arc ไหน / ทำไม deviate>" | null
    },
    "linkage": {
      "recommendation_available": true | false,
      "is_cold_start": false | true
    }
  }
}
```

**`hook_adoption` derivation** (`classify_hook_adoption`, normalize lowercase/strip punct):

| เงื่อนไข | ค่า |
|---|---|
| ไม่มี suggested hooks | `none_suggested` |
| `hooks_actually_used = None` (ไม่บันทึก) | `unrecorded` |
| used ว่าง / ไม่ตรง suggested เลย | `rejected` |
| used ⊆ suggested (และมีอย่างน้อย 1) | `adopted` |
| used ∩ suggested ≠ ∅ แต่ไม่ subset | `partial` |

> `suggested` vs `hooks_actually_used` คือแกนที่ตอบว่า "คำแนะนำถูก adopt หรือถูกปฏิเสธ" —
> เมื่อมี observed telemetry (Phase ถัดไป) จะ correlate ได้ว่า adopt แล้วผลดีขึ้นจริงไหม

---

## 3. Reference Tracking — exact / near / cold_start

ทั้งสามกรณีผ่าน path เดียวกัน (`build_provenance` รับ seed ใด ๆ หรือ `None`):

| กรณี | `recommended.reference_project` | `match_quality` | `match_score` | `is_cold_start` |
|------|------|------|------|------|
| **exact** | ชื่อโปรเจกต์ niche ตรงกัน | `exact` | 1.0 | false |
| **near** | nearest niche (token overlap) | `near` | 0 < s < 1 | false |
| **cold_start** | `null` (บังคับ) | `cold_start` | 0.0 | true |

> `recommendation_service` คืน `match_quality="none"` สำหรับ cold start —
> `build_provenance` normalize `none → cold_start` ให้ตรง vocab ที่ validator บังคับ
> และ **บังคับ `reference_project=null`** เมื่อ cold_start (validator reject ถ้าฝืน)

---

## 4. Validation Rules (`validators.validate_provenance`)

- เรียกใน `memory_writer.safe_append` **หลัง** `validate_record` (V1) — block การเขียนถ้า provenance ที่ "มีอยู่" ผิดรูป
- `validate_provenance(None) == []` → record ที่ไม่มี provenance ผ่านปกติ (backward compat)
- กฎที่บังคับ:
  - `match_quality ∈ {exact, near, cold_start}`
  - `cold_start` ห้ามมี `reference_project`
  - `hook_adoption ∈ {adopted, partial, rejected, none_suggested, unrecorded}`
  - `suggested_hooks` / `hooks_actually_used` ต้องเป็น list (ถ้ามี)
- **`V1_REQUIRED` ไม่ถูกแตะ** — provenance ไม่อยู่ใน required ตลอดไป

---

## 5. Backward Compatibility

| สิ่ง | ผล |
|------|----|
| record เก่า (v1/v2) ไม่มี `provenance` | valid 100% — `validate_provenance(None)=[]`, `validate_db` เช็คแค่ V1 |
| `build_record(...)` เรียกแบบเดิม (ไม่ส่ง `provenance`) | record ออกมา**เหมือน v2 เป๊ะ** (ไม่มี `schema_version`/`provenance`) |
| `process_project(...)` เรียกแบบเดิม (ไม่ส่ง `seed`) | ได้ provenance แบบ `cold_start` (additive, informative) |
| record เก่าใน `database.json` | survive byte-for-byte ตอน append (ทดสอบแล้ว: `new[:len(old)]==old`) |

---

## 6. Data Flow (pseudocode)

```python
# STEP 1.5 — forward
seed = recommend(product_niche, project_name)        # exact | near | cold_start

# ... storytelling/editor ทำงาน, เก็บการตัดสินใจ ...
hooks_used        = ["Double Kill"]                  # หรือ None ถ้าไม่บันทึก
reused_specs      = True
story_decision    = "cold-open Double Kill, build from first teamfight"

# STEP 15 — backward (ภายใน process_project, หลัง QA PASS)
resolved_created  = created_at or now_utc()          # ผูก timestamp เดียวกับ loop_run_id
provenance = build_provenance(
    seed,
    hooks_actually_used = hooks_used,
    reused_editing_specs = reused_specs,
    storytelling_decision = story_decision,
    created_at = resolved_created,
    project_name = project_name,
)                                                    # -> provenance/v3 dict
record = build_record(ns, edl, transcripts, render, qa, provenance=provenance)
ok, info = safe_append(record)                       # validate V1 + provenance, append-only, atomic
emit("PROJECT_COMPLETE", pid, {loop_run_id, match_quality, hook_adoption, ...})
```

**CLI** (สำหรับ run จริงจาก orchestrator):
```bash
python integrations/learning/learning_manager.py \
  --edl work/edit/edl.json --render work/edit/final.mp4 \
  --project-name "<name>" --product-niche "<niche>" --qa-pass true --retention-score 85 \
  --seed-json <seed.json> --hooks-used "Double Kill,Ace" \
  --reused-editing-specs true --storytelling-decision "<note>"
```
> `--seed-json` = ไฟล์ที่ได้จาก `recommendation_service` (STEP 1.5). ถ้าไม่ใส่ = cold_start provenance.

---

## 7. Validation Plan (ที่รันแล้ว ✓)

| Test | ผล |
|------|----|
| `classify_hook_adoption` 6 เคส | ✓ ครบ (adopted/partial/rejected/unrecorded/none_suggested) |
| `build_provenance` exact / near / cold_start | ✓ `validate_provenance` PASS ทั้งสาม |
| validator reject `match_quality="fuzzy"` | ✓ reject |
| validator reject `cold_start` + reference | ✓ reject |
| `validate_provenance(None)` | ✓ `[]` (backward compat) |
| dry-run end-to-end ผ่าน learning_manager | ✓ record มี schema_version=v3 + provenance |
| real-write ลง temp DB | ✓ append #3 + backup |
| record เก่า survive byte-for-byte | ✓ `new[:2]==old` |
| record เก่าไม่มี provenance หลัง append | ✓ untouched |
| 7 modules compile + import (no circular) | ✓ |

---

## 8. Rollback Plan

ทุกการเปลี่ยนเป็น additive → rollback ปลอดภัยเป็นชั้น:

1. **ปิดการใช้งานทันที (ไม่ revert โค้ด):** เรียก `process_project(...)` / `build_record(...)`
   โดย**ไม่ส่ง provenance/seed** → record กลับเป็น v2 ทันที (provenance เป็น optional param)
2. **revert โค้ด:** `git checkout -- integrations/learning/{validators,memory_writer,learning_manager}.py
   integrations/adapter/render_to_memory.py` — โค้ดกลับ v2, record เดิมในไฟล์ยัง valid
   (validator เก่าไม่รู้จัก `provenance` ก็ไม่เป็นไร เพราะมันเช็คแค่ V1)
3. **ข้อมูลที่เขียนไปแล้ว:** `provenance` เป็น optional field — ปล่อยไว้ได้ ไม่กระทบ V1 contract
   ถ้าต้องการลบ: ใช้ backup ใน `memory/_db_backups/` (สร้างทุกครั้งก่อนเขียน)
4. **ไม่มี migration ให้ย้อน** — ไม่ได้แตะ record เก่าตั้งแต่แรก (ดู §9)

---

## 9. Migration Plan

**ไม่มี migration แบบ rewrite.** เป็น forward-only:

- record เก่า (2 ตัวปัจจุบัน) **คงไว้ตามเดิม** — ไม่ backfill, ไม่แตะ (เคารพ append-only)
- record ใหม่ทุกตัวตั้งแต่ติดตั้งนี้ = มี `provenance` อัตโนมัติ
- การ join ข้ามยุค: ใช้ `loop_run_id` ถ้ามี, fallback เป็น `(project_name, created_at)`
- record เก่าที่ไม่มี provenance → ถือเป็น `recommendation_available=false` โดยปริยายตอนวิเคราะห์

> เหตุผลที่ไม่ backfill: record เก่าถูกสร้างก่อนมี forward loop จริง → ไม่มี seed ให้ระบุที่มา
> การเดา provenance ย้อนหลัง = ปลอม causal data = อันตรายต่อ Video Analyst มากกว่าไม่มี

---

## 10. Recommended Implementation Order (ที่ทำไปแล้ว ✓ / ถัดไป)

1. ✓ `validators.validate_provenance` + constants (additive)
2. ✓ wire validation เข้า `memory_writer.safe_append` (block เฉพาะเมื่อ malformed)
3. ✓ `recommendation_service.build_provenance` + `make_loop_run_id` + `classify_hook_adoption`
4. ✓ `build_record(..., provenance=None)` — stamp `schema_version=v3` เฉพาะเมื่อมี
5. ✓ thread ผ่าน `process_project` + CLI flags (`--seed-json`, `--hooks-used`, ...)
6. ✓ emit `loop_run_id` / `match_quality` / `hook_adoption` ใน `PROJECT_COMPLETE`
7. **(ถัดไป)** ให้ Orchestrator STEP 1.5 เซฟ seed เป็นไฟล์ แล้วส่ง `--seed-json` ตอน STEP 15
   (ปิด human gap สุดท้าย — ตอนนี้ pipeline พร้อมรับแล้ว)
8. **(ถัดไป, ตาม DATA_ACCUMULATION_PHASE)** `memory/telemetry.json` sidecar join บน `loop_run_id`
   → ครบ causal chain: recommendation → decision → predicted → **observed**

---

## ภาคผนวก — ไฟล์ที่แตะ (ยืนยันขอบเขต)

| ไฟล์ | การเปลี่ยน | ประเภท |
|------|-----------|--------|
| `integrations/learning/validators.py` | + `validate_provenance` + 2 const set | additive |
| `integrations/learning/memory_writer.py` | + เรียก validate_provenance (1 บรรทัด) | additive guard |
| `integrations/learning/recommendation_service.py` | + builder/helpers (provenance) | additive |
| `integrations/adapter/render_to_memory.py` | `build_record` รับ `provenance=None` | additive param |
| `integrations/learning/learning_manager.py` | thread seed→provenance + CLI flags | additive |

`V1_REQUIRED` ไม่เปลี่ยน · `database.json` contract เดิม · ไม่มี core ถูกแก้
