# Storytelling Skill
## Goal
สร้าง Story Arc ที่ทำให้ผู้ชมดูจนจบ
## Framework
- HOOK (หยุดเลื่อน)
- BUILD (สร้างความสนใจ)
- EMOTIONAL PEAK (อารมณ์สูงสุด)
- RESOLUTION (จบน่าจดจำ)

## Memory Protocol

- ฟิลด์ที่รับผิดชอบ: `hook_successful`
- READ: ก่อนสร้าง Story Arc ใช้ Tool อ่าน `memory/database.json` ดึง `hook_successful` ของโปรเจกต์ที่ `product_niche` ใกล้เคียงมาเป็นแรงบันดาลใจ และหลีกเลี่ยงรูปแบบที่เคยตก
- RETURN: ส่งโครงเรื่อง Hook ที่เลือกใช้กลับให้ Orchestrator เพื่อบันทึกในฟิลด์ `hook_successful` (จะถูกยืนยันว่า "ผ่าน QA" ต่อเมื่อ qa-reviewer = Pass)
- ห้ามเขียนลง `memory/database.json` เอง — การ Append เป็นหน้าที่ Orchestrator (STEP 15) เพื่อคงกฎ 1 โปรเจกต์ = 1 Record ตาม `memory/schema.md`
