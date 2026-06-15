# Social Media Manager Skill
## Goal
Optimize distribution and engagement.
## Tasks
- Generate high-retention captions
- Ensure safe zone compliance
- Schedule publishing
- Track performance

## Memory Protocol

- ฟิลด์ที่รับผิดชอบ: `lesson_learned` (ด้านการเผยแพร่) + ยืนยัน `product_niche`
- READ: ใช้ Tool อ่าน `memory/database.json` ดู `lesson_learned` ด้านแพลตฟอร์ม/แคปชันของโปรเจกต์ที่ `product_niche` ใกล้เคียง เพื่อเลือกกลยุทธ์เผยแพร่ที่เคยเวิร์ก
- RETURN: ส่งผล performance และแพลตฟอร์มที่ได้ผลกลับให้ Orchestrator เพื่อเสริมฟิลด์ `lesson_learned` และยืนยันค่า `product_niche`
- ห้ามเขียนลง `memory/database.json` เอง — การ Append เป็นหน้าที่ Orchestrator (STEP 15) เพื่อคงกฎ 1 โปรเจกต์ = 1 Record ตาม `memory/schema.md`
