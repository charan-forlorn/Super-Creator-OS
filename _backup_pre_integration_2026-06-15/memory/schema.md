# Memory Schema

โครงสร้างข้อมูลที่ต้องจดจำสำหรับแต่ละโปรเจกต์:

- project_name: ชื่อโปรเจกต์
- product_niche: ประเภทสินค้า
- hook_successful: โครงเรื่อง Hook ที่ผ่าน QA
- editing_specs: สเปกการตัดต่อที่ใช้
- retention_score: คะแนนจาก Retention Expert
- lesson_learned: สิ่งที่เรียนรู้จากโปรเจกต์นี้

## รูปแบบการจัดเก็บ (Storage Format)

- `memory/database.json` เก็บเป็น **JSON Array** โดย 1 โปรเจกต์ = 1 Object
- ฐานข้อมูลว่างเริ่มต้น = `[]`
- การบันทึกใหม่ใช้วิธี **Append** (อ่าน Array เดิม → push record ใหม่ → เขียนกลับทั้งไฟล์) — ห้ามเขียนทับข้อมูลเดิม

## โครงสร้าง Record (1 โปรเจกต์)

```json
{
  "project_name": "",
  "product_niche": "",
  "hook_successful": "",
  "editing_specs": "",
  "retention_score": 0,
  "lesson_learned": "",
  "created_at": ""
}
```

- `retention_score` เป็นตัวเลข (0–100) จาก Retention Expert
- `created_at` เป็น ISO timestamp (เช่น `2026-06-15T12:00:00Z`) ใช้อ้างอิงลำดับเวลาเพื่อหาโปรเจกต์ล่าสุดที่ใกล้เคียง
