# Style Library — คลังลายเซ็นสไตล์อ้างอิง

> ใช้คู่กับ `memory/database.json` (ฐานโปรเจกต์) — ไฟล์นี้เก็บ "สไตล์/รูปแบบ" ที่ถอดจากคลิปอ้างอิงที่ผู้ใช้ส่งมาให้ศึกษา
> ผู้ใช้จะทยอยส่งคลิปหลายรูปแบบมาเรื่อยๆ → แต่ละ batch บันทึกเป็น section ใหม่ แล้วสรุป "pattern ร่วม" ไว้ท้ายไฟล์

---

## Batch 1 — RoV gameplay references (2026-06-15)
แหล่ง: `input/reference/` (3 คลิป)

| ไฟล์ | ขนาด | ยาว | fps | ประเภท | เสียง (mean/max dB) |
|---|---|---|---|---|---|
| Download.mp4 | 576×1024 (9:16) | 94s | 60 | คลิปโพสต์จริง (มี TikTok watermark) | −19.8 / −3.5 = มีเพลงคลอ |
| Download (1).mp4 | 1024×576 (16:9) | 119s | 30 | คลิปโพสต์จริง (watermark) | −13.4 / −0.1 = เพลงดัง normalize |
| การบันทึกหน้าจอ…230754.mp4 | 1744×982 | 54s | 30 | คลิปดิบ screen-rec | −30.8 / −14.4 = เสียงเกมล้วน |

### ลายเซ็นที่ถอดได้
- **เกม:** RoV (Arena of Valor / Garena) ทั้งหมด → niche หลักของผู้ใช้
- **ฟอร์แมตโพสต์:** ตั้ง 9:16, 60fps (ลื่น) สำหรับตัวที่โพสต์จริง
- **จังหวะตัด:** น้อยมาก (1–2 hard cut ต่อ 90 วิ) = **เล่นต่อเนื่อง ไม่ใช่ montage ตัดรัว**. scdet: vertical=2 cuts, screen-rec=20 (เป็น scene-change ธรรมชาติในเกม ไม่ใช่ editor cut)
- **เสียง:** ใส่เพลงคลอ + normalize ดัง ไม่ได้ตัด beat-sync
- **HUD:** โชว์เต็ม (minimap + ปุ่มสกิล) = สาย authentic
- **โทนสี:** น้ำเงิน-เทาเข้มของแมป, VFX สกิลเป็นตัวแต่งสี ไม่เกรดหนัก

### Insight
สไตล์ native ของฟีดสายนี้ **"ดิบ/ต่อเนื่อง"** กว่าการตัด montage แบบ hype (punch-in zoom + fast cut + slo-mo). 
เก็บไว้เป็น 2 เลน: **(A) Raw-continuous** ตามอ้างอิงนี้ vs **(B) Hype-montage** ที่เคยตัดให้ (โปรเจกต์ "MOBA Pentakill" ใน database.json) — รอผู้ใช้ชี้ว่าชอบเลนไหน หรือผสม

---

## Batch 2 — Multi-tone references (2026-06-16)
แหล่ง: `input/reference/` (5 คลิปใหม่ที่เพิ่งลง — เรียนรู้เฉพาะตัวใหม่, Batch 1 ไม่นับซ้ำ)
ผู้ใช้ระบุชัดว่า **คลิป MISTERBEAM ดีสุด** → ตั้งเป็น "เลนหลักที่อยากได้"

| ไฟล์ | สัดส่วน | ยาว | fps | codec | ประเภท | เสียง (mean/max dB) | scene-cut |
|---|---|---|---|---|---|---|---|
| ⭐ การบันทึกหน้าจอ…174547.mp4 | 1782×1004 (16:9) | 258s | 30 | h264 | screen-rec ของคลิป talking-head จริง | −30.8 / −13.1 (เสียงระบบ-เบา, พูดนำ) | 31 |
| Highlight คิวเลน…riarix.webm | 1080×1920 (9:16) | 29s | 30 | av1 | RoV highlight (RiarixChannel) | −25.4 / −6.3 | 0 = ใช้ทรานสิชันนุ่ม ไม่ใช่ hard cut |
| IT HURTS…vent #sad.webm | 1080×1920 (9:16) | 24s | 30 | av1 | 2D animation อารมณ์ | −12.1 / 0.0 (นอร์มัลไลซ์ดัง เพลงนำ) | 0 = ภาพต่อเนื่อง |
| Riley/Wox Editz…animation.webm | 1080×1080 (1:1) | 58s | 60 | av1 | sports edit เกรดจัด | −20.7 / 0.0 | 21 = ตัดตามบีต |
| ที่เที่ยวเชียงคาน…travel.webm | 720×1280 (9:16) | 16s | 30 | vp9 | travel vlog สั้น | −21.9 / −0.7 | 6 |

### ⭐ ลายเซ็นเด่น — MISTERBEAM (เลนหลักที่ผู้ใช้ชอบสุด)
> นี่คือไฟล์ screen-rec ที่อัดจอจากคลิป talking-head จริง ของครีเอเตอร์ "MISTERBEAM (Video Creator)" — เป็นคลิป **สอน/เล่าวิธีตัดต่อ** ภาษาไทย
- **ฟอร์แมต:** แนวนอน **16:9** (YouTube long-form/แนวนอน) — ไม่ใช่ 9:16 เหมือนเลนสั้น
- **โครงสร้าง:** **A-Roll (พูดหน้ากล้อง) + B-Roll แทรก** (โชว์หน้าจอ Final Cut Pro: bin footage + timeline) สลับกัน
- **ภาพ:** cinematic — โทนมืด-อบอุ่น, ฉากหลัง bokeh (สตูดิโอตัดต่อ มีคนตัดงานที่ Mac ด้านหลัง), DOF ตื้น, เกรดแบบ cine มีคอนทราสต์
- **โปรดักชัน:** ใส่ไมค์หนีบปกเสื้อ NANLITE, แสงสตูดิโอจัดเฟรม
- **ข้อความบนจอ (สำคัญ):** ซับ/คีย์เวิร์ด kinetic วางชิดซ้าย, ฟอนต์ sans-serif สะอาด, ขาว + ไฮไลต์คำสำคัญด้วย **สีเหลือง** เช่น "A-Roll / ดนตรีประกอบ", "Footage", "เวลา / งบประมาณ / ความซีเรียสของงาน"
- **จังหวะ:** พูดนำเป็นหลัก มีดนตรีคลอเบาๆใต้เสียงพูด (mean −30.8 จาก screen-rec; mix จริงน่าจะดังกว่านี้)
- **end card:** จอดำ "MISTERBEAM / Video Creator / Facebook · Youtube"
- **สรุปเลน:** "ครีเอเตอร์สอน/เล่าแบบโปร" = talking-head + B-roll + ซับคีย์เวิร์ดไฮไลต์เหลือง + เกรด cine แนวนอน

### ลายเซ็นอีก 4 คลิป (ความหลากหลายของโทน)
- **RoV Highlight (RiarixChannel):** เปิดด้วย **title card "Highlight" ตัวแดงใหญ่** + hook ข้อความไทยบนสุด ("นี่หรอความลับ คิวเลน") → เข้าเกมเพลย์ มี MVP badge/นับ kill. ทรานสิชันนุ่ม (0 hard cut). ← ยืนยัน niche RoV ของ Batch 1 แต่เพิ่ม pattern "title card + hook ค้างบนจอ"
- **IT HURTS:** 2D animation มินิมอล (ตัวกลมดำบนพื้นเทาไล่เฉด) + แคปชันอังกฤษอารมณ์ ("I HOPE YOU FEEL WHAT I FELT…") เพลงนำ ภาพต่อเนื่อง = สาย vent/อารมณ์
- **Riley / Wox Editz:** sports edit **จัตุรัส 1:1, 60fps** เกรดเขียว-ส้มจัด, ตัดตามบีต 21 จุด, มีลายน้ำ editor = สาย "edit montage" เน้นจังหวะ+สี
- **Travel เชียงคาน:** drone/B-roll ท่องเที่ยว + **location tag เหลือง-ดำตัวหนา** ("#SKYWALK CHIANGKHAN", "#วัดศรีคุณเมือง") = สาย travel vlog สั้น

### Insight (Batch 2)
ผู้ใช้กำลัง **ขยายจาก RoV ล้วน → หลายโทน**: gaming, animation อารมณ์, sports-edit, travel และโดยเฉพาะ **talking-head สอนแบบโปร (MISTERBEAM)**.
จุดร่วมที่เริ่มเห็น: ทุกคลิป **มีข้อความ/ซับบนจอเป็นพระเอก** (hook/คีย์เวิร์ด/location tag) และนิยม **ไฮไลต์คำด้วยสีเหลือง**.
แยกชัดเป็น 2 ตระกูล:
- **เลนสั้น 9:16/1:1** (gaming, anime, travel, sports) — ภาพ+เพลงนำ ตัดเร็ว/ทรานสิชัน ซับ hook
- **เลนยาว 16:9 talking-head (MISTERBEAM)** ⭐ — พูดนำ + B-roll + เกรด cine + ซับคีย์เวิร์ดเหลือง ← **เป้าหมายคุณภาพที่ผู้ใช้อยากได้**

---

## Batch 3 — Fake Phone-UI Lyric Edit (2026-06-16)
แหล่ง: `input/reference/ScreenRecording_06-16-2026 6-19-51 PM_1.mp4` (1 คลิปใหม่)

| คุณสมบัติ | ค่า |
|---|---|
| สัดส่วน | 920×1472 แนวตั้ง (≈9:16, อัดจอมือถือ/AE) | 
| ยาว / fps | 56s / **60fps** |
| เสียง | mean −16.6 / max −3.5 dB = **เพลงนำดัง** นอร์มัลไลซ์ |
| scene-cut | 0 = ภาพต่อเนื่อง ขยับด้วยอนิเมชัน ไม่ใช่ hard cut |
| รูปแบบไฟล์ | screen-rec จาก **After Effects** โชว์คู่ Wireframe(บน)/Result(ล่าง) |

### ลายเซ็นที่ถอดได้
- **ประเภท:** **"Fake Phone-UI Lyric Edit"** — lyric video ที่แทนแต่ละท่อนเนื้อเพลงด้วย **UI มือถือปลอม** ขยับตามบีต
- **องค์ประกอบ UI ที่ใช้แทนเนื้อร้อง:** แชต AI (Gemini "Hi Subhan…"), หน้าจอ power/lock ("Press and hold the power button"), to-do list (Todoist — เนื้อเพลงเป็นรายการ ขีดฆ่าเมื่อ "completed"), app icon grid (Spotify/Chess/Wi-Fi), notification stack (iMusic now playing + Tasks 09:00), การ์ดเพลง "Lumo/Subz Motion", story ranking + ปุ่ม "Share this story"
- **เพลงต้นฉบับในคลิป:** *Eenie Meenie — Sean Kingston & Justin Bieber* (เห็นจากท่อน "eenie meenie miney mo by" + การ์ด My World/Beautiful Girls)
- **โมชัน:** ป็อป/สเกล/สไลด์เข้าออกตามจังหวะ, ทุก element ลอยบนพื้นดำสนิท, จัดกลางจอ
- **ฟอนต์:** sans-serif ระบบ (SF/Helvetica) สะอาด เลียนแบบ UI iOS จริง
- **เครื่องมือ:** After Effects (มี wireframe/keyframe/bounding box โผล่ในครึ่งบน)

### Insight
เลนนี้คือ **motion-graphics edit สาย "aesthetic/fake-UI"** ต่างจากเลนอื่นทั้งหมด (gameplay/animation/talking-head/travel) — ไม่ใช้ฟุตเทจจริง แต่ **ออกแบบ UI การ์ดเองทั้งหมดแล้วอนิเมตให้ซิงก์เนื้อเพลง**. ทำได้ด้วยการสร้าง PNG การ์ด UI (Pillow) + overlay อนิเมชันตามเวลา (ffmpeg). คีย์ของความเท่ = ความเนียนของ UI + การซิงก์บีต + พื้นดำคอนทราสต์สูง.

### Deep-study (2026-06-16) — วัดจริงจากคลิป
- **Edit cadence ขึ้นกับเสียงร้อง:** verse สลับ UI เร็ว ~ทุก 0.5–1.0s (วัดได้ที่ 22.0/22.8/23.5/24.0/24.5/25.0/25.6/26.4s); ฮุก/ท่อนยาว hold element เดียว 3–8s แล้วอนิเมตภายในแทน (volume ขึ้น / bar เติม / shake คำ accent)
- **ทรานสิชัน:** เนียนล้วน (0 hard cut) = AE animate position+scale+rotate พร้อม overshoot (easy-ease)
- **Motion recipe:** entrance ~0.2s ease-out-back scale 0.8→1.0 + fade + slide; punch ตาม onset; beat-lock จาก amplitude envelope ของเพลง
- 📘 **Playbook เต็ม (วิธีตัดให้เหมือนเขา):** [`skills/video-editor/FAKE_UI_LYRIC_EDIT.md`](../skills/video-editor/FAKE_UI_LYRIC_EDIT.md)
- 🛠️ **Reference implementation ที่ทำได้จริง:** `work/uigen/build_lyric.py` + `transcribe.py` (hot girl bummer edit, output ใน `output/HOT_GIRL_BUMMER_uiedit.mp4`)

---

## Pattern ร่วม (อัปเดตเมื่อมี batch ใหม่)
- ยืนยันแล้ว: niche เดิม = **RoV/MOBA**, โพสต์เลนสั้น **9:16**
- เพิ่มจาก Batch 2: ผู้ใช้สนใจ **หลายโทน** (animation อารมณ์, sports-edit 1:1, travel) ไม่ใช่ RoV อย่างเดียว
- **สไตล์ที่ผู้ใช้ "ชอบจริง" (ระบุเอง):** เลน talking-head สอนแบบ **MISTERBEAM** — 16:9, A-roll+B-roll, เกรด cine, ซับคีย์เวิร์ดไฮไลต์ **เหลือง**
- ลายเซ็นข้ามทุกคลิป: **ข้อความบนจอคือพระเอก** (hook/คีย์เวิร์ด/location tag) + นิยม **ไฮไลต์คำสำคัญสีเหลือง**
- รอยืนยัน batch ถัดไป: โทนไหนจะตัดจริงบ่อยสุด, ความยาวที่เวิร์กของเลนยาว, แนวเพลงต่อโทน
