# Super Creator Workflow Map

1. Receive Brief — **READ** `memory/database.json`: หา Reference โปรเจกต์เก่าที่ `product_niche` ใกล้เคียงที่สุดมาตั้งต้น (ถ้าเป็น `[]` = ไม่มี Reference ให้เริ่มใหม่)
1.5. Learning Bridge (RECOMMEND) — หลัง Receive Brief และ **ก่อน** Generate Story Arc / Timeline ให้เรียก Learning Bridge หนึ่งครั้งเพื่อรวบรวม "creative seed" จากทุกสิ่งที่ระบบเรียนรู้มาแล้ว:

   ```bash
   python integrations/learning/recommendation_service.py \
       --product-niche "<niche ของ Brief>" --project-name "<ชื่อโปรเจกต์>" --top-n 3
   ```

   ผลลัพธ์เป็น JSON dict เดียว (read-only ล้วน ห้ามแก้ memory):
   - `suggested_hooks_next_time` + `hook_successful_prior` → **Storytelling** (ตั้งต้น HOOK)
   - `retention_benchmark` + `retention_signals` → **Retention Expert** (benchmark ตั้งต้น)
   - `highlight_patterns` → **Timeline / cold-open** (timecode ของ beat ที่เคยเวิร์ก)
   - `editing_specs_to_reuse` + `render_specs_to_reuse` → **Video Editor** (reuse EDL shape)
   - `lesson_learned_prior` → ทุก Skill (กันพลาดซ้ำ)
   - `notes` → อ่านก่อนเสมอ: exact / near / cold-start

   หากไม่มี seed (cold-start) → ข้ามไปตามปกติ ไม่มีการบังคับใช้
2. Analyze Assets
3. Analyze References
4. Generate Concept
5. Generate Story Arc
6. Generate Timeline
7. Generate Motion Plan
8. Generate Look Direction
9. Generate Subtitle Plan
10. Analyze Risks (Retention)
11. QA Review (Pass/Fail)
12. Render
13. Export
14. Generate Captions
15. Archive Project — **WRITE** `memory/database.json`: Append record ใหม่ตามโครงสร้างใน `memory/schema.md` (อ่าน Array เดิม → push → เขียนกลับ ห้ามเขียนทับ) โดยเขียนผ่าน learning_manager เท่านั้น:

   ```bash
   python integrations/learning/learning_manager.py \
       --edl work/edit/edl.json --render work/edit/final.mp4 \
       --transcripts-dir work/edit/transcripts \
       --project-name "<name>" --product-niche "<niche>" \
       --qa-pass true --retention-score <0-100>
   ```

   - หาก recommendation_service เคยรันพร้อม `--persist` → learning_manager จะ auto-resolve seed โดยไม่ต้องส่ง `--seed-json`
   - record จะถูก stamp ด้วย provenance (loop_run_id, recommendation_id) อัตโนมัติ
   - ห้ามเขียนทับ `database.json` ด้วยมือ — ใช้ `learning_manager` หรือ `memory_writer.safe_append()` เท่านั้น
