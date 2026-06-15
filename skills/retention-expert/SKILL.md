# Retention Expert Skill
## Goal
เพิ่ม Average Watch Time
## Scoring
- Hook (0-10)
- Retention (0-10)
- Emotion (0-10)
- Story (0-10)
- Rewatchability (0-10)

## Memory Protocol

- ฟิลด์ที่รับผิดชอบ: `retention_score`
- READ: ใช้ Tool อ่าน `memory/database.json` ดึง `retention_score` ของโปรเจกต์ที่ `product_niche` ใกล้เคียงมาเป็น Benchmark ตั้งต้น
- RETURN: ส่ง `retention_score` กลับให้ Orchestrator โดยรวมคะแนน 5 หมวด (หมวดละ 0–10 = 0–50) แล้วคูณ 2 ให้เป็นสเกล **0–100** ตาม `memory/schema.md` พร้อมโน้ตจุดที่ฉุด Retention เพื่อเสริม `lesson_learned`
- ห้ามเขียนลง `memory/database.json` เอง — การ Append เป็นหน้าที่ Orchestrator (STEP 15) เพื่อคงกฎ 1 โปรเจกต์ = 1 Record
