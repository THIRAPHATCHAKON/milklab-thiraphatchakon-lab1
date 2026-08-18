---
title: SolarPlus RAG Chatbot
emoji: ☀️
colorFrom: yellow
colorTo: blue
sdk: docker
app_port: 8501
pinned: false
---

# โซลาร์พลัส — ผู้ช่วยให้คำปรึกษาโซลาร์เซลล์

Chatbot ตอบคำถามลูกค้าเรื่องการติดตั้งโซลาร์เซลล์ (ขนาดระบบ, ราคา, การคืนทุน,
เอกสาร, การรับประกัน) โดยใช้ RAG จากไฟล์ `solar_kb.md`
ส่วนการคำนวณขนาด/ราคา/คืนทุนทำด้วย `solar_calc.py` ไม่ให้ LLM คิดเลขเอง

## Stack

- Streamlit — chat UI (รันบน Docker SDK)
- sentence-transformers (multilingual-MiniLM) — embedding ภาษาไทย
- FAISS — vector search
- Gemini — LLM สำหรับเรียบเรียงคำตอบ

## ไฟล์หลัก

| ไฟล์ | Session | คำอธิบาย |
|---|---|---|
| `caption_generator.py` | S1 | สร้างแคปชั่นโพสต์โซเชียลของร้าน |
| `lead_logger.py` | S2 | บันทึกลีดลูกค้าลง Google Sheets |
| `lead_report.py` | S2 | สรุปลีดรายวันส่ง Telegram |
| `agent_harness.py` | S2 | รับคำสั่งภาษาไทย เรียก tool |
| `agent_tools.py` | S2 | tool registry + validation |
| `solar_calc.py` | — | คำนวณขนาด/ราคา/คืนทุน (Python ล้วน) |
| `app.py` | S3 | Streamlit RAG chatbot |

## รันในเครื่อง

```bash
pip install -r requirements.txt
streamlit run app.py
```

หรือรันแบบเดียวกับที่ deploy จริง:

```bash
docker build -t solarplus-rag .
docker run -p 8501:8501 -e GOOGLE_API_KEY=xxx solarplus-rag
```

> ตัวเลขราคาและสเปกใน `solar_kb.md` และ `solar_calc.py` เป็นค่าตั้งต้น
> ต้องแก้ให้ตรงกับราคาจริงของร้านก่อนใช้งานจริง

รายละเอียดการ pivot จาก MilkLab ดูที่ `README_PIVOT.md`