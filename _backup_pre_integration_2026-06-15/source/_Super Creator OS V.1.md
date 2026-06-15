นี่คือชุดไฟล์หลักที่ผมแนะนำให้คุณสร้างก่อนเป็นเวอร์ชัน V1 ของ **Super Creator OS** โดยเน้นให้ Claude Code / Claude Desktop โหลดใช้งานได้จริง และต่อยอดเป็น MCP \+ Automation ได้ภายหลัง

## **ลำดับการสร้างไฟล์**

1\. project.md  
2\. config/editing-standards.md  
3\. config/output-presets.md  
4\. skills/orchestrator/SKILL.md  
5\. skills/storytelling/SKILL.md  
6\. skills/video-editor/SKILL.md  
7\. skills/qa-reviewer/SKILL.md  
8\. skills/social-media-manager/SKILL.md  
9\. skills/retention-expert/SKILL.md  
10\. workflow-map.md

---

## **project.md**

# **Super Creator OS**

## **Mission**

สร้าง AI Creative Studio ที่สามารถ:

* วิเคราะห์ Brief  
* วิเคราะห์ Assets  
* วิเคราะห์ Reference  
* วาง Story  
* ตัดต่อวิดีโอ  
* ทำ Subtitle  
* Color Grade  
* ตรวจคุณภาพ  
* สร้าง Caption  
* Export หลาย Platform

โดยมีคุณภาพใกล้เคียง Human Editor

---

## **Core Principle**

Claude ไม่ใช่ Video Editor

Claude คือ

Creative Director  
Storyteller  
Editor Supervisor  
QA Reviewer

ส่วนการ Render จริงใช้

* FFmpeg  
* Remotion  
* CapCut Automation  
* DaVinci Resolve Automation

---

## **Success Criteria**

Video ต้อง

* หยุดการเลื่อนภายใน 2 วินาที  
* มี Emotional Arc ชัดเจน  
* ดูจบง่าย  
* มี Save Trigger  
* มี Share Trigger  
* เหมาะกับ Mobile First

---

## **Current Platforms**

* TikTok  
* Instagram Reel  
* Instagram Story

---

## **Creative Philosophy**

Human First

AI Assisted

Emotion Driven

Story Before Effects

Retention Before Beauty

---

## **Active Workflow**

Brief  
→ Concept  
→ Story  
→ Timeline  
→ Edit  
→ Motion  
→ Color  
→ Subtitle  
→ QA  
→ Export

---

## **config/editing-standards.md**

# **Editing Standards**

## **Hook**

ต้องดึงความสนใจภายใน 1-2 วินาที

---

## **Pacing**

Short Form

ไม่มี Dead Air

ไม่มีช่วงนิ่งเกิน 2 วินาที

---

## **Story Structure**

1. Hook  
2. Build  
3. Emotional Peak  
4. Resolution

---

## **Motion Rules**

ใช้

* Slow Push-In  
* Pan  
* Parallax  
* Subtle Zoom

หลีกเลี่ยง

* Spin  
* Flashy Effects  
* Distracting Motion

---

## **Transition Rules**

Preferred

* Cross Dissolve  
* Match Cut  
* Light Leak  
* Motion Blur Cut

Avoid

* Random Glitch  
* Heavy Zoom Transition

---

## **Subtitle Rules**

ไม่เกิน 2 บรรทัด

ไม่เกิน 7 คำต่อบรรทัด

ต้องอ่านได้บนมือถือ

---

## **Audio Rules**

ตัดตามอารมณ์ก่อน Beat

Beat เป็นตัวช่วย

Emotion เป็นตัวนำ

---

## **Human Editing Rules**

ทุก Cut ต้องมีเหตุผล

ทุก Motion ต้องมีเหตุผล

ทุก Text ต้องมีเหตุผล

ห้ามใส่ Effect เพียงเพราะทำได้

---

## **skills/storytelling/SKILL.md**

---

## **name: storytelling**

## **description: Build emotional story arc for short form videos**

# **Goal**

สร้าง Story Arc ที่ทำให้ผู้ชมดูจนจบ

# **Framework**

HOOK

หยุดการเลื่อน

↓

BUILD

สร้างความสนใจ

↓

EMOTIONAL PEAK

ช่วงที่อารมณ์สูงสุด

↓

RESOLUTION

จบอย่างน่าจดจำ

# **Rules**

ต้องมี Emotional Journey

ต้องมี Narrative Direction

ต้องมี Payoff

# **Output**

* Story Arc  
* Scene Order  
* Emotional Beats  
* Hook Ideas  
* Ending Ideas

# **Fail Conditions**

เปิดเรื่องช้า

ไม่มี Peak

จบไม่มี Impact

---

## **skills/video-editor/SKILL.md**

---

## **name: video-editor**

## **description: Convert story arc into editing instructions**

# **Goal**

สร้าง Timeline ระดับ Production

# **Process**

1. Analyze Assets  
2. Select Best Shots  
3. Remove Weak Footage  
4. Build Timeline  
5. Define Transitions  
6. Define Motion  
7. Define Subtitle Timing  
8. Create Render Notes

# **Timeline Format**

00:00-00:03

Hook

Asset: A001

Motion: Push In

Transition: None

Emotion: Curiosity

---

00:03-00:08

Asset: B004

Motion: Slow Pan

Transition: Cross Dissolve

Emotion: Warmth

# **Output**

* EDL  
* Timeline  
* Shot List  
* Render Instructions

---

## **skills/retention-expert/SKILL.md**

---

## **name: retention-expert**

## **description: Analyze retention risk**

# **Goal**

เพิ่ม Average Watch Time

# **Review Areas**

Hook

Pacing

Emotion

Curiosity

Payoff

Ending

# **Scoring**

Hook  
0-10

Retention  
0-10

Emotion  
0-10

Story  
0-10

Rewatchability  
0-10

# **Output**

Retention Score

Drop-Off Risk

Fix Suggestions

Re-Hook Ideas

---

## **skills/qa-reviewer/SKILL.md**

---

## **name: qa-reviewer**

## **description: Final quality assurance**

# **Goal**

จับปัญหาก่อน Export

# **Checklist**

Story

✓ มี Hook

✓ มี Build

✓ มี Peak

✓ มี Resolution

Visual

✓ Motion สอดคล้อง

✓ Transition สอดคล้อง

✓ ไม่มี Cut แปลก

Audio

✓ ไม่มี Pop

✓ ไม่มี Clip

✓ ระดับเสียงคงที่

Subtitle

✓ อ่านง่าย

✓ ไม่บัง Subject

Platform

✓ Safe Zone

✓ Resolution ถูกต้อง

# **Result**

PASS

or

FAIL

พร้อมเหตุผล

---

## **workflow-map.md**

# **Super Creator Workflow**

STEP 1

Receive Brief

↓

STEP 2

Analyze Assets

↓

STEP 3

Analyze References

↓

STEP 4

Creator Director

Generate Concept

↓

STEP 5

Storytelling

Generate Story Arc

↓

STEP 6

Video Editor

Generate Timeline

↓

STEP 7

Motion Designer

Generate Motion Plan

↓

STEP 8

Color Grading

Generate Look Direction

↓

STEP 9

Subtitle Editor

Generate Subtitle Plan

↓

STEP 10

Retention Expert

Analyze Risks

↓

STEP 11

QA Reviewer

Pass / Fail

↓

STEP 12

Render

↓

STEP 13

Export

TikTok

Instagram Reel

Instagram Story

↓

STEP 14

Generate Captions

↓

STEP 15

Archive Project

### **หลังจากสร้างไฟล์ชุดนี้เสร็จ**

Roadmap ที่ผมแนะนำสำหรับ AutoNEX Creative OS คือ

Phase 1  
Skill System  
(ตอนนี้)

↓

Phase 2  
Project Memory

↓

Phase 3  
Video Analysis MCP

↓

Phase 4  
FFmpeg Render Engine

↓

Phase 5  
Browser/Computer Control

↓

Phase 6  
Self-Improving Creator Brain

↓

Phase 7  
Fully Autonomous Creator Agent

จุดที่สำคัญที่สุดตอนนี้คือ **ยังไม่ต้องรีบทำ Browser Control** ให้รีบสร้าง **Skill Library \+ Creator Memory \+ Reference Database** ก่อน เพราะนั่นคือสิ่งที่จะทำให้ Claude "ตัดสินใจเหมือน Creative Director" ได้จริง ส่วน Browser และ Computer Use เป็นเพียงแขนขาที่มาทีหลังเท่านั้น.

