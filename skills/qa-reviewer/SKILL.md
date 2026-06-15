# QA Reviewer Skill
## Goal
จับปัญหาก่อน Export
## Checklist
- Story: Hook, Build, Peak, Resolution
- Visual: Motion, Transitions
- Audio: No pop/clip, consistent volume
- Subtitle: Readable, No overlap
- Platform: Safe Zone, Resolution

## Memory Protocol

- ฟิลด์ที่รับผิดชอบ: Gate (Pass/Fail) + `lesson_learned`
- READ: ก่อนรีวิว ใช้ Tool อ่าน `memory/database.json` ดู `lesson_learned` ของโปรเจกต์ที่ `product_niche` ใกล้เคียง เพื่อโฟกัสจุดที่เคยพลาดบ่อย
- RETURN: ส่งผลกลับให้ Orchestrator — สถานะ Pass/Fail เป็น **Gate** ว่าจะให้บันทึกลงความจำหรือไม่ (บันทึกเฉพาะโปรเจกต์ที่ Pass) และสรุปประเด็นที่เจอ/แก้ ลงในฟิลด์ `lesson_learned`
- ห้ามเขียนลง `memory/database.json` เอง — การ Append เป็นหน้าที่ Orchestrator (STEP 15) เพื่อคงกฎ 1 โปรเจกต์ = 1 Record ตาม `memory/schema.md`
