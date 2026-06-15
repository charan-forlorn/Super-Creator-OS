# Video Editor Skill
## Goal
สร้าง Timeline ระดับ Production
## Process
1. Analyze Assets
2. Select Best Shots
3. Build Timeline
4. Define Transitions/Motion/Subtitle
5. Render Notes

## Memory Protocol

- ฟิลด์ที่รับผิดชอบ: `editing_specs`
- READ: ก่อนวาง Timeline ใช้ Tool อ่าน `memory/database.json` ดึง `editing_specs` ของโปรเจกต์ที่ `product_niche` ใกล้เคียงมาเป็นค่าตั้งต้น (จังหวะตัด / Transition / Motion ที่เคยเวิร์ก)
- RETURN: ส่งสเปกการตัดต่อที่ใช้จริงกลับให้ Orchestrator เพื่อบันทึกในฟิลด์ `editing_specs`
- ห้ามเขียนลง `memory/database.json` เอง — การ Append เป็นหน้าที่ Orchestrator (STEP 15) เพื่อคงกฎ 1 โปรเจกต์ = 1 Record ตาม `memory/schema.md`
