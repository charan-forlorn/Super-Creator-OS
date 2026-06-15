# Orchestrator Skill
## Mission
Master Orchestrator of Super Creator OS. 
## Goal
Coordinate storytelling, editing, QA, and distribution skills.
## Workflow
- Receive Brief -> Analyze Assets -> Analyze Reference -> Concept -> Story -> Timeline -> Motion -> Color -> Subtitle -> Retention -> QA -> Render -> Export -> Captions -> Archive

## Memory Protocol
- STEP 1 (READ / อ่านความจำเก่า): ก่อนเริ่มงานทุกครั้ง ระบบต้องใช้ Tool อ่านไฟล์ `memory/database.json` เสมอ แล้วค้นหา Reference โปรเจกต์เก่าที่ `product_niche` ใกล้เคียงกับ Brief ปัจจุบันมากที่สุด เพื่อนำ `hook_successful`, `editing_specs` และ `lesson_learned` ของโปรเจกต์นั้นมาใช้ตั้งต้น — หาก `database.json` เป็น `[]` (ว่าง) ให้เริ่มงานใหม่โดยไม่มี Reference
- STEP 15 (WRITE / บันทึกความจำใหม่): เมื่อจบงาน (หลัง Archive) ระบบต้อง Extract ข้อมูลโปรเจกต์ปัจจุบันให้ครบทุก Field ตามโครงสร้างใน `memory/schema.md` แล้วต่อท้าย (Append) Object นั้นลงใน Array ของ `memory/database.json` เสมอ ด้วยขั้นตอน: อ่าน Array เดิม → push record ใหม่ → เขียนกลับทั้งไฟล์ (ห้ามเขียนทับข้อมูลเดิม)
