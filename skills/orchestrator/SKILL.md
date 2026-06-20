# Orchestrator Skill
## Mission
Master Orchestrator of Super Creator OS. 
## Goal
Coordinate storytelling, editing, QA, and distribution skills.
## Workflow
- Receive Brief -> Analyze Assets -> Analyze Reference -> Concept -> Story -> Timeline -> Motion -> Color -> Subtitle -> Retention -> QA -> Render -> Export -> Captions -> Archive

## Memory Protocol
- STEP 1 (READ / อ่านความจำเก่า): ก่อนเริ่มงานทุกครั้ง ระบบต้องใช้ Tool อ่านไฟล์ `memory/database.json` เสมอ แล้วค้นหา Reference โปรเจกต์เก่าที่ `product_niche` ใกล้เคียงกับ Brief ปัจจุบันมากที่สุด เพื่อนำ `hook_successful`, `editing_specs` และ `lesson_learned` ของโปรเจกต์นั้นมาใช้ตั้งต้น — หาก `database.json` เป็น `[]` (ว่าง) ให้เริ่มงานใหม่โดยไม่มี Reference

## Forward Intelligence Protocol (Learning Bridge)
- STEP 1.5 (RECOMMEND / ดึงความรู้มาใช้ก่อนสร้าง Timeline): หลัง Receive Brief และ **ก่อน** Generate Story Arc / Timeline ให้เรียก Learning Bridge หนึ่งครั้งเพื่อรวบรวม "creative seed" จากทุกสิ่งที่ระบบเรียนรู้มาแล้ว:

  ```bash
  python integrations/learning/recommendation_service.py \
      --product-niche "<niche ของ Brief>" --project-name "<ชื่อโปรเจกต์>" --top-n 3
  ```

  ผลลัพธ์เป็น JSON dict เดียว (ห้ามแก้ memory ใด ๆ — เป็น read-only ล้วน) ให้ Orchestrator ส่งต่อแต่ละฟิลด์ไปยัง Skill ที่รับผิดชอบ:
  - `suggested_hooks_next_time` + `hook_successful_prior` → **Storytelling** (ตั้งต้น HOOK; หลีกเลี่ยงรูปแบบที่เคยตก)
  - `retention_benchmark` + `retention_signals` → **Retention Expert** (ใช้เป็น benchmark ตั้งต้นของ `retention_score`)
  - `highlight_patterns` → **Timeline / cold-open** (ใช้ timecode ของ beat ที่เคยเวิร์กเปิดเป็น hook ทันที ไม่ต้องสแกน RMS ใหม่)
  - `editing_specs_to_reuse` + `render_specs_to_reuse` → **Video Editor** (reuse EDL shape: grade / padding / resolution)
  - `lesson_learned_prior` → ทุก Skill (กันพลาดซ้ำ)
  - `notes` → อ่านก่อนเสมอ: บอกว่าเป็น exact / near / cold-start และให้ "adapt, don't copy" เมื่อเป็น near-niche

  Bridge นี้ emit events `BRIEF_RECEIVED → REFERENCE_MATCHED → HOOKS_RECOMMENDED → CREATIVE_SEED_READY` ลง Event Bus เพื่อให้ Skill อนาคต (Video Analyst / Pattern Discovery) subscribe ได้โดยไม่ต้องแก้ loop
- STEP 15 (WRITE / บันทึกความจำใหม่): เมื่อจบงาน (หลัง Archive) ต้องบันทึก 1 record ต่อ 1 โปรเจกต์ลง `memory/database.json` แบบ **append-only เสมอ** โดย **ห้ามแก้ไฟล์ด้วยมือ / ห้ามเขียนทับทั้งไฟล์เอง** — ให้เขียนผ่าน "the only safe path" ที่มีอยู่แล้วเท่านั้น (มันทำ validate → backup → atomic write → append-only post-condition → duplicate guard ให้ครบ กัน DB พัง/เขียนครึ่งทาง):

  - **ทางหลัก (engine path, แนะนำ):** รัน learning loop controller — มันสร้าง record (v1 + v2 fields อัตโนมัติ), ผ่าน QA gate, archive, อัปเดต anchor library และ emit events ให้เสร็จในตัว:
    ```bash
    python integrations/learning/learning_manager.py \
        --edl work/edit/edl.json --render work/edit/final.mp4 \
        --transcripts-dir work/edit/transcripts \
        --project-name "<name>" --product-niche "<niche>" \
        --qa-pass true --retention-score <0-100>
    ```
    (มี `--dry-run` ไว้ preview record ก่อนเขียนจริงได้)
  - **ทางรอง (สร้าง record เอง):** ถ้าจำเป็นต้องประกอบ record เอง ให้เขียนผ่าน `integrations/learning/memory_writer.py` → `safe_append(record, db_path)` เท่านั้น **ห้าม** `json.dump` ทับ `database.json` ตรง ๆ
  - **โครงสร้าง record:** v1 ตาม `memory/schema.md` (required) + v2 optional ตาม `memory/schema_v2_extension.md` (clip_type / highlight_anchors / retention_signals / render_specs ฯลฯ — จำเป็นต่อ forward loop ใน STEP 1.5 ให้ใส่เมื่อมีข้อมูล)
  - คงสัญญาเดิมทุกประการ: append เท่านั้น, ไม่แตะ record เก่า, 1 โปรเจกต์ = 1 object
