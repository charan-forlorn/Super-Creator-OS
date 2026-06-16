# Data Infrastructure Phase — Super Creator OS

> สถานะ: **ติดตั้งแล้ว + ทดสอบ end-to-end ด้วย environment isolation** (production git-clean)
> ปิด Human Gap (STEP 1.5→15), แยก Anchor Library ออกจาก production, สร้าง Telemetry Sidecar,
> และต่อ Causal Chain ครบ recommendation → decision → execution → predicted → **observed**
>
> ข้อกำหนดที่ยึด: Additive only · ไม่แก้ `V1_REQUIRED` · ไม่แก้ Memory Contract · ไม่แตะ core · Windows-safe · Rollback ได้

---

## 1. Executive Summary

เฟสนี้เติม **data infrastructure 3 ชิ้น** บนระบบที่ปิด loop แล้ว โดยไม่เพิ่ม product feature:

| ชิ้น | ปัญหาเดิม | ที่แก้ |
|------|----------|--------|
| **Seed Persistence** | ต้องส่ง `--seed-json` ด้วยมือระหว่าง STEP 1.5 → 15 | `seed_store.py` — STEP 1.5 persist อัตโนมัติ, STEP 15 auto-resolve by project name |
| **Anchor Library Isolation** | path hardcoded → test แตะ production | `resolve_lib_path()` + `$SCOS_ANCHOR_LIB` + `--lib-path` (ทุก write point มี env isolation) |
| **Telemetry Sidecar** | มีแต่ predicted outcome ไม่มี observed | `telemetry.py` + `memory/telemetry.json` แยกจาก database.json โดยสมบูรณ์ |

ผลรวม: ทุก record ตอบได้ว่า "ผลลัพธ์นี้เกิดจากคำแนะนำใด **และให้ผลจริงเท่าไร**" — พร้อมป้อน Video Analyst

**ไฟล์ใหม่:** `seed_store.py`, `telemetry.py`
**ไฟล์ที่แก้ (additive):** `recommendation_service.py`, `learning_manager.py`, `anchor_library.py`, `archive_manager.py`, `event_bus.py`, `validators.py`, `render_to_memory.py`, `.gitignore`

---

## 2. Seed Persistence Architecture

ปิด Human Gap ด้วย **inter-step buffer** ที่ key ด้วย slug(project_name):

```
STEP 1.5  recommendation_service --persist (default)
              │  seed += recommendation_id + recommendation_timestamp
              ▼
          seed_store.persist_seed()  ──▶  work/seeds/<slug>.json   (atomic, overwrite-latest)
              │
   ...สร้างจริง...
              ▼
STEP 15   learning_manager  (ไม่ต้องใส่ --seed-json)
              │  seed_store.resolve_seed(project_name)   ◀── auto-load
              ▼
          build_provenance(seed, ...)  ──▶  record.provenance.recommended.recommendation_id
              │  (consumed seed -> work/seeds/_consumed/<slug>.<ts>.json  = audit)
              ▼
          memory/database.json   (APPEND-ONLY)
```

**Resolution order (seed source):** `--seed-json` > auto `resolve_seed(project_name)` > none (cold_start)
**ทดสอบแล้ว:** STEP 1.5 persist → STEP 15 auto-load โดยไม่มี `--seed-json` →
`recommendation_id` ไหลเข้า provenance → seed ถูก consume เข้า `_consumed/`

### Fields ที่ persist (ครบตาม requirement)
`recommendation_id` · `recommendation_timestamp` · `reference_project` · `match_quality` ·
`match_score` · `suggested_hooks_next_time` · `retention_benchmark` ·
`editing_specs_to_reuse` (= editing_specs_reference)
> `loop_run_id` ไม่อยู่ใน seed — มันถูกสร้างที่ STEP 15 (`created_at::slug`) แล้ว freeze ลง provenance
> คู่กับ `recommendation_id` (seed ไม่รู้ created_at ของ record ล่วงหน้า)

---

## 3. Anchor Library Isolation Design

แก้บั๊กจริง: `anchor_library.LIB_PATH` hardcoded → smoke test เคย bump counter ของ production

**Resolution order (ทุก write/read point):** explicit arg > `$SCOS_<X>` env > production default

```python
# anchor_library.py
ENV_LIB = "SCOS_ANCHOR_LIB"
def resolve_lib_path(explicit=None):
    if explicit: return Path(explicit)
    return Path(os.environ[ENV_LIB]) if os.environ.get(ENV_LIB) else LIB_PATH
# suggest_hooks(path=) และ record_project_anchors(path=) เรียกผ่าน resolve_lib_path(path)
```

CLI design — รองรับ 4 environments ด้วยกลไกเดียว:

| Environment | วิธีตั้ง |
|-------------|---------|
| **production** | ไม่ตั้งอะไร (ใช้ default) |
| **staging** | `export SCOS_ANCHOR_LIB=.../staging/lib.json` (ทั้ง session) |
| **test (CI)** | `SCOS_ANCHOR_LIB=$TMP/lib.json python ...` (per-command) |
| **temp sandbox** | `--lib-path /sandbox/lib.json` (override สูงสุด, ตรงจุด) |

`--lib-path` ถูก thread เข้า `recommendation_service` และ `learning_manager.process_project` ครบ
**Validation:** ถ้า lib ที่ชี้ไปมีอยู่แต่ schema เสีย → `validate_anchor_library` reject ก่อนเขียน (เหมือนเดิม)

> **ขอบเขต env isolation ครบทุก write point:** `$SCOS_ANCHOR_LIB` (anchor), `$SCOS_SEEDS_DIR` (seeds),
> `$SCOS_TELEMETRY` (telemetry), `$SCOS_EVENTS` (event log), `$SCOS_ARCHIVE` (archive). + `--db` เดิม
> ⇒ ทดสอบแล้ว: 1 sandbox + env 5 ตัว → production database.json + anchor lib **git-clean 100%**

---

## 4. Telemetry Sidecar Architecture

```
                memory/database.json        memory/telemetry.json   ◀── ไฟล์แยก
                (predicted + provenance)     (observed outcome)
                          │                          │
                 loop_run_id ◀══════ join key ══════▶ loop_run_id
                          └────────────┬─────────────┘
                          telemetry.join_causal_chain()  (read-only)
                                       ▼
                          dataset สำหรับ Video Analyst
```

- `memory/telemetry.json` = JSON **array**, 1 ไฟล์, แยกจาก database.json โดยสมบูรณ์
- **หลายแถวต่อโปรเจกต์ได้** (snapshot 24h / 72h / 7d) → key = `(loop_run_id, platform, collected_at)`
- write discipline เท่ากับ memory_writer: **validate → backup → append-only → atomic**
- รองรับ `tiktok` · `youtube_shorts` · `instagram_reels`
- `database.json` ไม่ถูกแตะแม้แต่ครั้งเดียว (ทดสอบ: record count คงที่, git-clean)

---

## 5. Telemetry Schema

```jsonc
{
  // --- required (join + identity) ---
  "loop_run_id": "2026-06-15T17:24:21.000Z::infra-smoke-rov",
  "project_name": "Infra Smoke RoV",
  "platform": "tiktok",                  // tiktok | youtube_shorts | instagram_reels
  "collected_at": "2026-06-18T20:30:00Z",
  // --- observed (optional, validated when present) ---
  "views": 18400,                        // ≥ 0
  "avg_watch_pct": 46,                   // 0..100
  "avg_watch_time_s": 11.2,              // ≥ 0
  "completion_rate": 19,                 // 0..100
  "rewatch_rate_pct": 8,                 // 0..100
  "ctr_pct": null,                       // 0..100 หรือ null ถ้าแพลตฟอร์มไม่ให้ (ห้ามเดา)
  "likes": 1230, "comments": 95, "shares": 220, "saves": 410,   // ≥ 0
  "source": "manual"                     // manual | api
}
```

### Additional Metrics — เสนอเพิ่ม เรียงตามมูลค่า

**1. High Value** (ทุกอันต้อง correlate กับสิ่งเหล่านี้ ไม่งั้นเรียนรู้ไม่ได้)
- `avg_watch_pct`, `completion_rate` — ground truth ของ retention (มีใน schema แล้ว)
- `rewatch_rate_pct` — สัญญาณ "ดูซ้ำ" = hook/loop ดีมาก (rewatchability ที่ retention-expert เดา)
- `saves` — intent signal แรงสุดต่อ value-content (สูงกว่า likes ในเชิงทำนาย reach)

**2. Medium Value**
- `ctr_pct` (ถ้ามี) — แยกคุณภาพ thumbnail/cold-open ออกจากคุณภาพเนื้อ
- `shares` — virality coefficient; `comments` — discussion/controversy signal
- `follows_from_video` — conversion ปลายทาง (ถ้าแพลตฟอร์มให้)

**3. Optional**
- `traffic_source_pct` (fyp/follow/search), `audience_retention_curve[]` (per-second),
  `peak_drop_off_s` — มูลค่าสูงแต่เก็บยาก/แพลตฟอร์มจำกัด → เก็บเมื่อทำได้
- `posted_hour` — timing pattern (ซ้ำกับ lesson_learned เดิม, optional)

> เหตุผลจัดลำดับ: High = correlate กับ "ดูจริงนานแค่ไหน/อยากเก็บไหม" ตรง ๆ;
> Medium = แยกแยะสาเหตุ (thumbnail vs เนื้อ); Optional = ลึกแต่ availability ต่ำ

---

## 6. Data Correlation Model

join key เดียว = **`loop_run_id`** (`created_at::slug(project_name)`) เชื่อม 4 แหล่ง:

```
recommendation history   provenance.recommended.recommendation_id
        │                          │
        └──────────┐               │
                   ▼               ▼
   database.json record  ──loop_run_id──  telemetry.json rows
   (predicted + decided)                   (observed, 1..n snapshots)
```

`join_causal_chain()` (read-only) คืนต่อ record:
```jsonc
{
  "loop_run_id", "project_name", "product_niche",
  "recommended": { recommendation_id, match_quality, suggested_hooks, ... },
  "decided":     { hooks_actually_used, hook_adoption, reused_editing_specs },
  "predicted_retention_score": 85,
  "retention_signals": { ... },
  "observed": [ { avg_watch_pct, views, ... } ],   // telemetry rows
  "has_observed": true
}
```
**ทดสอบแล้ว** join ออกมาครบ chain: `rec_id → suggested → used/adoption → predicted 85 → observed 46%/18400`

---

## 7. Causal Chain Design — ตอบ 5 คำถามได้จาก data architecture เพียงอย่างเดียว

| # | คำถาม | ตอบจาก |
|---|-------|--------|
| 1 | Hook ไหน **ถูกแนะนำ** | `provenance.recommended.suggested_hooks` (per record) + anchor library |
| 2 | Hook ไหน **ถูกใช้จริง** | `provenance.decided.hooks_actually_used` + `hook_adoption` |
| 3 | Hook ไหน **ให้ผลดีสุด** | join `hooks_actually_used` × `observed.avg_watch_pct` → avg ต่อ hook |
| 4 | Recommendation ไหน **success rate สูงสุด** | group by `recommendation_id`/`reference_project` × outcome_label (hit ถ้า observed ≥ niche p75) |
| 5 | Niche ไหนตอบสนอง hook แบบใด | group by `product_niche` × hook × `observed` |

ทุกคำถามตอบได้ด้วย **GROUP BY บนผล join** — ไม่ต้องมี logic ใหม่นอกจาก aggregate
(Video Analyst = ตัว aggregate; data model พร้อมรองรับแล้ว)

> เงื่อนไขที่ทำให้ตอบได้: (a) provenance มี `hooks_actually_used` (Provenance Layer ✓)
> (b) telemetry มี observed join บน loop_run_id (เฟสนี้ ✓) (c) ปริมาณพอ (ดู Milestones)

---

## 8. Folder Structure

```
memory/
  database.json              # v1+v2+v3 records (APPEND-ONLY, contract เดิม)
  telemetry.json             # ◀ ใหม่: observed outcome (array, sidecar)
  highlight_anchor_library.json
  _db_backups/               # auto-backup (gitignored)
  _telemetry_backups/        # ◀ ใหม่: auto-backup (gitignored)
work/
  seeds/                     # ◀ ใหม่: seed handoff buffer (gitignored)
    <slug>.json              #   pending seed (STEP 15 อ่าน)
    _consumed/<slug>.<ts>.json  #   audit ของ seed ที่ใช้แล้ว
integrations/learning/
  seed_store.py              # ◀ ใหม่
  telemetry.py               # ◀ ใหม่
  recommendation_service.py  # +persist, +recommendation_id, +--lib-path
  learning_manager.py        # +auto-seed, +--lib-path, +consume
  anchor_library.py          # +resolve_lib_path / $SCOS_ANCHOR_LIB
  archive_manager.py         # +resolve_archive_root / $SCOS_ARCHIVE
  event_bus.py               # +$SCOS_EVENTS
  validators.py              # +validate_telemetry(_store)
  events.jsonl               # runtime audit (gitignored)
  archive/                   # runtime audit (gitignored)
```

---

## 9. Validation Rules

| จุด | กฎ | ผล |
|-----|----|----|
| **record** | `validate_record` (V1) — ไม่เปลี่ยน | BLOCK |
| **provenance** | `validate_provenance` (optional block) | BLOCK ถ้า present+malformed |
| **telemetry row** | `loop_run_id/project_name/platform/collected_at` required; platform ∈ 3 ค่า | BLOCK |
| **telemetry numeric** | pct fields 0..100; counts/seconds ≥ 0 (เมื่อ present) | BLOCK |
| **telemetry store** | root ต้องเป็น array, ทุกแถว valid | BLOCK ก่อนเขียน |
| **telemetry dedup** | ห้าม `(loop_run_id, platform, collected_at)` ซ้ำ | BLOCK |
| **anchor library** | `validate_anchor_library` (schema) | BLOCK |
| **seed** | resolve คืน `None` ถ้า parse ไม่ได้ (ไม่ crash) | graceful |

ทดสอบ negative: bad platform `myspace` → reject; `avg_watch_pct=150` → reject; dup key → reject ✓

---

## 10. Safety Design (ทุกจุดที่เขียนข้อมูล)

| Guarantee | database.json | telemetry.json | anchor lib | seeds |
|-----------|:---:|:---:|:---:|:---:|
| Append-only | ✓ (`new[:n]==old`) | ✓ (`new[:n]==old`) | ✓ (merge counters) | overwrite-latest* |
| Atomic write (tmp→replace) | ✓ | ✓ | ✓ | ✓ |
| Auto backup | ✓ `_db_backups` | ✓ `_telemetry_backups` | ✓ `_db_backups` | _consumed (audit) |
| Schema validation | ✓ | ✓ | ✓ | resolve-safe |
| Provenance validation | ✓ | — | — | — |
| Environment isolation | `--db` | `$SCOS_TELEMETRY` | `$SCOS_ANCHOR_LIB`/`--lib-path` | `$SCOS_SEEDS_DIR` |

\* seeds เป็น handoff buffer (ไม่ใช่ system of record) — durable copy คือ provenance ใน record
event log: `$SCOS_EVENTS` · archive: `$SCOS_ARCHIVE` (ทั้งคู่ isolate ได้)

---

## 11. Milestones

| | Seed Persistence | Telemetry | Data Quality | Video Analyst | Pattern Discovery |
|--|---|---|---|---|---|
| **M0** | ✓ ติดตั้ง + auto-resolve | ✓ sidecar + validate | DQ rules นิยามแล้ว | — | — |
| **M1** | seed→record link ≥ 95% (มี recommendation_id) | observed ≥ 10 rows | coverage 100% (ทุก render มี terminal event) | — | — |
| **M2** | — | ≥ 30 record/niche มี observed (hit≥5, flop≥5) | DQ pass ≥ 95% | **เปิดได้** (1 niche M2 + provenance ≥ 80%) | — |
| **M3** | — | ≥ 3 niche ผ่าน M2 | niche canonical นิ่ง | running | **เปิดได้** (cross-niche) |
| **M4** | — | observed fill-rate ≥ 80% ทุก active niche | prediction_error tracked | self-tuning | weekly_patterns.json |

> สถานะตอนนี้: **M0 ครบทั้ง 3 คอลัมน์แรก** (ติดตั้ง+ทดสอบแล้ว) → เริ่มสะสมเข้า M1

---

## 12. Acceptance Criteria

- [x] **AC-1** STEP 1.5 persist seed อัตโนมัติ (`work/seeds/<slug>.json`)
- [x] **AC-2** STEP 15 auto-resolve seed **โดยไม่ต้องใส่ `--seed-json`** → provenance ได้ recommendation_id
- [x] **AC-3** seed ถูก consume เข้า `_consumed/` หลังเขียน memory สำเร็จ (audit)
- [x] **AC-4** `--lib-path`/`$SCOS_ANCHOR_LIB` redirect ได้ → **production lib git-clean หลัง test**
- [x] **AC-5** `memory/telemetry.json` แยกจาก database.json; **database.json record count คงที่**
- [x] **AC-6** telemetry รองรับ tiktok/youtube_shorts/instagram_reels + validate (reject ของผิด)
- [x] **AC-7** telemetry dedup บน (loop_run_id, platform, collected_at)
- [x] **AC-8** `join_causal_chain` ตอบครบ recommendation→decision→predicted→observed
- [x] **AC-9** ทุก write point มี atomic + backup + env isolation
- [x] **AC-10** `V1_REQUIRED` ไม่เปลี่ยน · Memory Contract เดิม · ไม่แตะ core · 9 modules compile/import
- [ ] **AC-11** (รอข้อมูลจริง) observed fill-rate + DQ report ผ่านเกณฑ์ M1→M2

---

## 13. Rollback Plan

ทุกการเปลี่ยนเป็น additive → rollback เป็นชั้น:

1. **ปิดทันทีไม่ revert:** เรียก learning_manager ด้วย `--no-auto-seed` → กลับเป็น manual seed (หรือ cold_start)
   telemetry แค่หยุดเรียก `telemetry.py` — ไม่มีใคร depend on it ตอนเขียน record
2. **revert ไฟล์:** `git checkout -- integrations/learning/{recommendation_service,learning_manager,anchor_library,archive_manager,event_bus,validators}.py`
   + `rm integrations/learning/{seed_store,telemetry}.py` → ระบบกลับสถานะก่อนเฟสนี้
3. **ข้อมูลที่เขียนไปแล้ว:** `telemetry.json`/`work/seeds/` เป็นไฟล์แยก — ลบได้โดยไม่กระทบ memory
   `provenance.recommendation_id` เป็น optional field — คงไว้ได้ ไม่ละเมิด V1
4. **กู้จาก backup:** `_db_backups/`, `_telemetry_backups/` มี snapshot ทุกครั้งก่อนเขียน
5. **ไม่มี migration ให้ย้อน** — ไม่ได้แตะ record/contract เดิม (forward-only)

---

## 14. Recommended Implementation Order

1. ✓ `validators.validate_telemetry(_store)` (additive)
2. ✓ `seed_store.py` (persist / resolve / consume / cleanup, atomic, env-isolated)
3. ✓ `recommendation_service`: +`recommendation_id`/`timestamp`, `--persist` (default on), `--lib-path`
4. ✓ `anchor_library.resolve_lib_path` + `$SCOS_ANCHOR_LIB`; route suggest/record ผ่านมัน
5. ✓ `learning_manager`: auto-resolve seed, `--lib-path`, consume seed, emit loop_run_id
6. ✓ `telemetry.py`: safe append + `join_causal_chain` + CLI + `$SCOS_TELEMETRY`
7. ✓ env isolation ที่เหลือ: `archive_manager`($SCOS_ARCHIVE), `event_bus`($SCOS_EVENTS)
8. ✓ `.gitignore` ครอบ transient/backups; ทดสอบ isolated end-to-end
9. **(ถัดไป)** Orchestrator: STEP 1.5 รัน recommendation_service (persist), STEP 15 รัน learning_manager (auto) — ปิด gap ในตัว workflow
10. **(ถัดไป)** read-only DQ report (Panel 1–6 จาก DATA_ACCUMULATION_PHASE §8) อ่านจาก join
11. **(M2)** Video Analyst subscribe `PROJECT_COMPLETE`/`HIGHLIGHT_PATTERN_DISCOVERED` → aggregate join → `weekly_patterns.json`

---

## ภาคผนวก — ไฟล์ที่แตะ (ยืนยันขอบเขต)

| ไฟล์ | การเปลี่ยน | core? | contract? |
|------|-----------|:---:|:---:|
| `seed_store.py` *(ใหม่)* | handoff buffer | ✗ | ✗ |
| `telemetry.py` *(ใหม่)* | observed sidecar + join | ✗ | ✗ |
| `recommendation_service.py` | +id/timestamp, persist, lib-path | ✗ | ✗ |
| `learning_manager.py` | auto-seed, lib-path, consume | ✗ | ✗ |
| `anchor_library.py` | resolve_lib_path + env | ✗ | ✗ |
| `archive_manager.py` | resolve_archive_root + env | ✗ | ✗ |
| `event_bus.py` | $SCOS_EVENTS | ✗ | ✗ |
| `validators.py` | +validate_telemetry(_store) | ✗ | ✗ (V1 คงเดิม) |
| `render_to_memory.py` | (provenance param จากเฟสก่อน) | ✗ | ✗ |

ไม่มี product feature · ไม่แตะ core · Memory Contract เดิม · `V1_REQUIRED` ไม่เปลี่ยน · Additive ทั้งหมด
