# Data Quality Report System — Super Creator OS

> สถานะ: **ติดตั้งแล้ว + ทดสอบกับข้อมูลจริง + sandbox** · READ-ONLY ยืนยันแล้ว (db/lib checksum ไม่เปลี่ยน)
> ไฟล์: [integrations/learning/dq_report.py](integrations/learning/dq_report.py)
>
> ภารกิจ: วัดความพร้อมของข้อมูลก่อนสร้าง Video Analyst — โดย **ไม่แก้ข้อมูลใด ๆ**

---

## 1. Executive Summary

`dq_report.py` เป็นเครื่องมือ **read-only** ตัวเดียว อ่าน `database.json` · `telemetry.json` ·
`events.jsonl` · anchor library แล้วคำนวณ **9 มิติคุณภาพ** + คำตัดสิน **Video Analyst Readiness**
พร้อม exit code (0=READY, 1=NOT READY) สำหรับ gate CI

หลักประกัน read-only (by construction):
- เปิดทุกไฟล์ข้อมูลแบบอ่านอย่างเดียว — ไม่มี write/append/atomic path ไปยังไฟล์ข้อมูล
- **ไม่ import** `memory_writer` / `safe_append` / `append_telemetry` / `record_project_anchors`
- สิ่งเดียวที่เขียนได้คือ derived artifact ผ่าน `--json-out` (ไฟล์ที่ผู้ใช้ตั้งชื่อเอง) และมี guard
  ปฏิเสธถ้า path ชน `database.json`/`telemetry.json`

ทดสอบกับข้อมูลจริง (2 records v1): รายงาน **NOT READY** ถูกต้อง, blockers ชัด, db+lib checksum ไม่เปลี่ยน

---

## 2. DQ Architecture

```
   database.json ─┐
   telemetry.json ┼──READ──▶  dq_report.build_report()  ──▶  report dict
   events.jsonl  ─┤              │  (pure functions, no side effects)
   anchor lib    ─┘              ├──▶ render_text()  ──▶ stdout
                                 └──▶ --json-out (derived artifact, guarded)

   reuse (read-only): telemetry.join_causal_chain(), telemetry.load_telemetry(),
                      validators.validate_{record,provenance,telemetry}(),
                      anchor_library.resolve_lib_path()
```

- ทุก dimension เป็น pure function รับ list → คืน dict (testable, ไม่มี state)
- join บน `loop_run_id` ใช้ `join_causal_chain` ตัวเดิม (ไม่เขียน logic join ซ้ำ)
- exit code = readiness → ใช้เป็น CI gate ได้ (`dq_report.py --quiet; echo $?`)

---

## 3. Metrics Definition (9 มิติ)

| # | Dimension | นิยาม |
|---|-----------|-------|
| 1 | **Coverage** | จาก events: `coverage_pct = (complete ∪ qa_failed) ∩ rendered / rendered`; `orphan_rendered` = render แล้วไม่ถึง terminal event; `records_with_loop_run_id` |
| 2 | **Provenance Quality** | `with_provenance_pct`, `provenance_valid_pct` (ผ่าน `validate_provenance`), `with_recommendation_id_pct`, distribution ของ `match_quality` |
| 3 | **Hook Adoption** | distribution ของ `hook_adoption`; `adoption_rate = adopted/(adopted+partial+rejected)`; `recorded_pct` (ไม่ใช่ `unrecorded`) |
| 4 | **Ground Truth Fill** | `fill_rate = records-with-observed / joinable-records` รวม + แยกต่อ niche — **metric หลักของความพร้อม** |
| 5 | **Prediction Calibration** | `MAE = mean(|retention_score − observed avg_watch_pct|)` บน record ที่มีทั้งคู่ (สเกล 0..100 ทั้งคู่) |
| 6 | **Niche Distribution** | records ต่อ niche; `canonical_violations` (สะกดต่างแต่ token เดียวกัน = DQ-10); hit/flop ต่อ niche (p25/p75 เมื่อ observed ≥ 8) |
| 7 | **Telemetry Health** | `total_rows`, `valid_pct`, by_platform, `orphan_loop_run_ids` (join ไม่ติด record), `duplicate_keys` (ควร []), `max_snapshots_per_run` |
| 8 | **Dataset Growth** | records/telemetry ต่อวัน (bucket จาก `created_at`/`collected_at`) |
| 9 | **Readiness** | gates รวม → READY/NOT READY + blockers + niche ที่ถึง M2 |

---

## 4. Validation Rules (อ้างอิงจริงในรายงาน)

ใช้ validator เดิมทั้งหมด (ไม่นิยามซ้ำ):
- `validate_record` → นับ record ที่ละเมิด V1
- `validate_provenance` → นับ provenance block ที่ผิดรูป (เฉพาะที่มี)
- `validate_telemetry` → นับ telemetry row ที่ผิดรูป
- `overall DQ pass-rate = (checked − bad) / checked` โดย checked = records + provenance blocks + telemetry rows

DQ id ที่ map กับ DATA_ACCUMULATION_PHASE §4:
- **DQ-1** Coverage (orphan_rendered) · **DQ-7** hooks recorded · **DQ-8** dup loop_run_id (telemetry duplicate_keys)
- **DQ-9** orphan telemetry · **DQ-10** canonical_violations

---

## 5. Readiness Gates

| Gate | เกณฑ์ผ่าน |
|------|----------|
| `coverage_100` | `coverage_pct ≥ 100` หรือไม่มี orphan (และไม่มี events = ยังไม่เริ่ม) |
| `provenance_ok` | `with_provenance_pct ≥ 95` |
| `hooks_recorded` | `recorded_pct ≥ 80` |
| `ground_truth_fill` | `fill_rate_pct ≥ 80` |
| `dq_pass` | `dq_pass_pct ≥ 95` |
| `niche_hygiene` | `canonical_violations == []` |
| `niche_at_M2` | มี ≥ 1 niche: records ≥ 30 **และ** hits ≥ 5 **และ** flops ≥ 5 |

`ready = all(gates)`. `blockers` = gate ที่ FAIL. exit code = 0 ถ้า ready, 1 ถ้าไม่

---

## 6. Report Format

- ค่าเริ่มต้น: text report ไป stdout (9 sections + readiness banner)
- `--json-out <path>`: dump report dict ทั้งก้อน (derived artifact; guard กัน path ชนไฟล์ข้อมูล)
- `--quiet`: JSON เท่านั้น (สำหรับ pipe/CI)
- env isolation: `--db` · `--telemetry` (/`$SCOS_TELEMETRY`) · `--events` (/`$SCOS_EVENTS`) · `--lib-path` (/`$SCOS_ANCHOR_LIB`)

---

## 7. Example Output (ข้อมูลจริงปัจจุบัน, 2 records v1)

```
VIDEO ANALYST READINESS: NOT READY ⛔
  blockers: provenance_ok, hooks_recorded, ground_truth_fill, niche_at_M2

-- 1. Coverage --   records=2  rendered=0  coverage_pct=None  (no events.jsonl)
-- 2. Provenance -- with_provenance=0/2 (0.0%)  match_quality={}
-- 3. Hook Adoption-- {}  recorded=None%
-- 4. Ground Truth-- joinable=0  with_observed=0  fill_rate=None% (target >= 80%)
-- 5. Calibration -- pairs=0  MAE=None
-- 6. Niche ------- records_per_niche={'Pet Accessories':1,'Gaming (MOBA)':1}
-- 7. Telemetry --- rows=0  orphan=[]  duplicate_keys=[]
-- 9. Gates ------- [PASS]coverage_100 [FAIL]provenance_ok [FAIL]hooks_recorded
                    [FAIL]ground_truth_fill [PASS]dq_pass [PASS]niche_hygiene [FAIL]niche_at_M2
                    overall DQ pass-rate = 100.0%
```

Sandbox (1 record w/ provenance + 1 telemetry row) — พิสูจน์ว่า metric ติด:
```
with_provenance=1/1 (100%)  valid=100%  rec_id=100%   match_quality={'exact':1}
hook_adoption={'adopted':1}  adoption_rate=100%
ground_truth fill_rate=100%
calibration: pairs=1  MAE=39.0  (predicted 85 vs observed 46 → จับ over-prediction ได้)
telemetry: rows=1 valid=100% by_platform={'tiktok':1} orphan=[] dup=[]
blockers: niche_at_M2   (ต้อง 30 records + hits/flops)
```

---

## 8. Acceptance Criteria

- [x] **AC-1** ไม่มี write path ไปยัง `database.json` (checksum ไม่เปลี่ยนหลังรัน)
- [x] **AC-2** ไม่มี write path ไปยัง `telemetry.json` (ยืนยันด้วย sandbox + real)
- [x] **AC-3** ไม่ import โมดูล writer ใด ๆ; `--json-out` มี guard กัน path ชนไฟล์ข้อมูล
- [x] **AC-4** รองรับ env isolation (`$SCOS_TELEMETRY`/`$SCOS_EVENTS`/`$SCOS_ANCHOR_LIB` + flags)
- [x] **AC-5** ใช้กับข้อมูลจริงได้ (2 records → NOT READY ถูกต้อง, ไม่ crash บน empty/None)
- [x] **AC-6** ครบ 9 มิติ + readiness verdict + exit code (0/1)
- [x] **AC-7** reuse validators + join_causal_chain เดิม (ไม่ duplicate logic)
- [x] **AC-8** Additive — ไฟล์ใหม่ไฟล์เดียว, ไม่แก้ core, ไม่แก้ contract

---

## 9. Rollback Plan

- เป็นไฟล์ใหม่ไฟล์เดียว read-only → rollback = `rm integrations/learning/dq_report.py` (ไม่กระทบอะไร)
- ไม่มี state/migration/ข้อมูลที่ถูกเขียน → ไม่มีอะไรต้องกู้คืน
- `--json-out` artifact (ถ้าสร้าง) = ไฟล์ derived ลบทิ้งได้อิสระ
- ไม่แตะ writer ใด ๆ → ไม่มี side effect ให้ revert

---

## 10. Recommended Thresholds

```python
THRESHOLDS = {
  "coverage_pct": 100,            # ทุก render ต้องถึง terminal event
  "provenance_pct": 95,           # records ที่มี provenance block
  "hooks_recorded_pct": 80,       # decided.hook_adoption != 'unrecorded'
  "ground_truth_fill_pct": 80,    # records (มี loop_run_id) ที่มี observed
  "dq_pass_pct": 95,              # validators pass-rate
  "min_records_per_niche": 30,    # M2 volume
  "min_hits_per_niche": 5,
  "min_flops_per_niche": 5,
  "max_prediction_mae": 20.0,     # advisory — > นี้ = Retention Expert ควร recalibrate
  "min_observed_for_percentiles": 8,  # ต่ำกว่านี้ไม่คำนวณ p25/p75 (กัน overfit)
}
```

เหตุผลค่าเกณฑ์:
- **100% coverage** — งานที่หลุด loop = ข้อมูลหาย, ไม่ยอมให้มี
- **80% fill / hooks_recorded** — ต่ำกว่านี้ correlation มี selection bias สูง
- **30 records + hits≥5/flops≥5 ต่อ niche** — minimum subgroup ให้ p25/p75 มี signal เหนือ noise
- **MAE ≤ 20 (advisory)** — ไม่ block readiness แต่เป็นสัญญาณว่า predicted retention เชื่อได้แค่ไหน
- **min_observed_for_percentiles = 8** — ป้องกันการประกาศ hit/flop จาก 1–2 ตัวอย่าง

---

## ภาคผนวก — ขอบเขต

| ไฟล์ | การเปลี่ยน | core? | contract? | write data? |
|------|-----------|:---:|:---:|:---:|
| `dq_report.py` *(ใหม่)* | read-only report 9 มิติ + readiness | ✗ | ✗ | **✗ (read-only)** |

ไม่แก้ข้อมูล · ไม่เขียน database/telemetry · ไม่ขยาย feature · Additive ไฟล์เดียว
