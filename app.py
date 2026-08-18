"""SolarPlus RAG Chatbot (S3) — เดิมคือ MilkLab RAG

Run locally: streamlit run app.py
Deploy: push to GitHub then Actions deploys to HuggingFace Space

pivot: knowledge base เปลี่ยนจาก menu_kb.md -> solar_kb.md
และเพิ่มการฉีดผลคำนวณจาก solar_calc เข้า context เมื่อผู้ใช้ระบุค่าไฟมาในคำถาม
เพราะเลขขนาดระบบ/ราคา/คืนทุน ห้ามให้ LLM คิดเอง
"""

import os
import re

import faiss
import numpy as np
import streamlit as st
from google import genai
from sentence_transformers import SentenceTransformer

import solar_calc

KB_PATH = "solar_kb.md"


@st.cache_resource
def load_index():
    """โหลด solar_kb.md, split เป็น chunk, encode, สร้าง faiss index

    Cache เพราะโหลด model ครั้งแรกใช้เวลาประมาณ 30 วินาที
    Returns: (model, index, chunks_list)
    """
    with open(KB_PATH, "r", encoding="utf-8") as f:
        document = f.read()

    # แบ่งเป็น chunks ตามย่อหน้า
    chunks = [c.strip() for c in document.split("\n\n") if c.strip()]

    # โหลด embedding model (multilingual รองรับภาษาไทย)
    model = SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    embeddings = model.encode(chunks, convert_to_numpy=True).astype(np.float32)

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    return model, index, chunks


def retrieve_top_k(query: str, model, index, chunks: list[str], k: int = 3) -> list[str]:
    """encode query, search index, return top-k chunks"""
    query_embedding = model.encode([query], convert_to_numpy=True).astype(np.float32)
    _, indices = index.search(query_embedding, k)
    return [chunks[i] for i in indices[0]]


def detect_monthly_bill(query: str) -> float | None:
    """ดึงค่าไฟต่อเดือนจากประโยคไทย ถ้าหาไม่เจอคืน None

    ทำด้วย regex ไม่ใช่ LLM เพราะเป็นการอ่านตัวเลขตรงๆ ไม่ต้องตีความ
    ต้องมีคำบ่งชี้บริบทค่าไฟในประโยคก่อน ไม่งั้น "ระบบ 5 kW ราคา 165,000"
    จะถูกอ่านเป็นค่าไฟผิดๆ
    เลขที่ตามด้วย "บาท" มาก่อน เพราะแม่นกว่าเลขลอยๆ ที่อาจเป็น kW หรือจำนวนปี
    """
    if not re.search(r"ค่าไฟ|บิลไฟ|ค่าไฟฟ้า|ใช้ไฟ|เดือนละ", query):
        return None

    baht_first = re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*บาท", query)
    matches = baht_first + re.findall(r"(\d[\d,]*(?:\.\d+)?)", query)
    for raw in matches:
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        # ค่าไฟบ้านที่สมเหตุสมผล — กันไปหยิบเลข kW หรือปี พ.ศ. มาใช้
        if solar_calc.MIN_BILL <= value <= solar_calc.MAX_BILL:
            return value
    return None


def build_calc_context(query: str) -> str | None:
    """ถ้าคำถามมีค่าไฟ ให้คำนวณด้วย Python แล้วแนบผลเข้า context

    LLM จะได้แค่ "เรียบเรียง" ตัวเลขที่คำนวณมาแล้ว ไม่ใช่คิดเลขเอง
    """
    bill = detect_monthly_bill(query)
    if bill is None:
        return None
    try:
        result = solar_calc.estimate(bill)
    except solar_calc.EstimateError:
        return None
    return "ผลการคำนวณจากระบบ (ใช้ตัวเลขชุดนี้ตอบเท่านั้น ห้ามคำนวณใหม่):\n" + solar_calc.format_th(result)


def generate_answer(query: str, context_chunks: list[str], calc_context: str | None = None) -> str:
    """ส่ง query + context ไป Gemini, return answer"""
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    context = "\n\n".join(context_chunks)
    if calc_context:
        context = f"{context}\n\n{calc_context}"

    prompt = f"""คุณคือผู้ช่วยของร้านโซลาร์พลัส ร้านรับติดตั้งโซลาร์เซลล์
หน้าที่คือตอบคำถามลูกค้าเบื้องต้นแทนเจ้าของร้านที่ไม่ว่างรับสาย

กฎการตอบ:
- ตอบจากข้อมูลใน Context ต่อไปนี้เท่านั้น
- ถ้าไม่มีข้อมูลใน Context ให้ตอบว่า "ขออภัยครับ ข้อมูลส่วนนี้ผมยังตอบแทนไม่ได้ ขอให้ทางร้านติดต่อกลับนะครับ"
- ห้ามคิดเลขเอง ถ้ามีผลการคำนวณจากระบบมาให้แล้ว ให้ใช้ตัวเลขชุดนั้นเท่านั้น
- ถ้าลูกค้ายังไม่ได้บอกค่าไฟต่อเดือน ให้ถามกลับก่อน จะได้ประเมินขนาดระบบให้ได้
- ตอบสุภาพ กระชับ ลงท้ายด้วยครับ
- ย้ำเสมอว่าเป็นการประเมินเบื้องต้น ราคาจริงต้องสำรวจหน้างานก่อน

Context:
{context}

คำถามลูกค้า:
{query}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text


def render_sidebar():
    """เครื่องคำนวณเบื้องต้นแบบกรอกเอง — ไม่ผ่าน LLM เลย ผลลัพธ์เชื่อถือได้ 100%"""
    with st.sidebar:
        st.header("ประเมินเบื้องต้น")
        bill = st.number_input(
            "ค่าไฟเฉลี่ยต่อเดือน (บาท)",
            min_value=float(solar_calc.MIN_BILL),
            max_value=float(solar_calc.MAX_BILL),
            value=3000.0,
            step=500.0,
        )
        usage_label = st.selectbox(
            "ลักษณะการใช้ไฟ",
            list(solar_calc.DAYTIME_RATIO_PRESETS.keys()),
            index=1,
        )
        if st.button("คำนวณ", use_container_width=True):
            ratio = solar_calc.DAYTIME_RATIO_PRESETS[usage_label]
            try:
                result = solar_calc.estimate(bill, ratio)
            except solar_calc.EstimateError as exc:
                st.error(str(exc))
                return
            st.metric("ขนาดที่แนะนำ", f"{result['recommended_kw']} kW")
            st.metric("ราคาประเมิน", f"{result['price']:,} บาท")
            st.metric("คืนทุนประมาณ", f"{result['payback_years']} ปี")
            st.caption(
                f"ประหยัดประมาณ {result['monthly_saving']:,.0f} บาท/เดือน "
                "เป็นการประเมินเบื้องต้น ต้องสำรวจหน้างานก่อนติดตั้ง"
            )


def main():
    st.set_page_config(page_title="โซลาร์พลัส ผู้ช่วยตอบคำถาม", page_icon="☀️")
    st.title("โซลาร์พลัส — ผู้ช่วยให้คำปรึกษาโซลาร์เซลล์")
    st.caption("ถามเรื่องการติดตั้ง ขนาดระบบ ราคา และการคืนทุนได้ ตอบจาก solar_kb.md")

    try:
        model, index, chunks = load_index()
    except FileNotFoundError:
        st.error(f"ไม่พบไฟล์ {KB_PATH} — ต้องวางไว้ในโฟลเดอร์เดียวกับ app.py")
        st.stop()

    render_sidebar()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("เช่น ค่าไฟเดือนละ 3000 ควรติดกี่ kW"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("กำลังค้นข้อมูล..."):
                context = retrieve_top_k(prompt, model, index, chunks)
                calc_context = build_calc_context(prompt)
                answer = generate_answer(prompt, context, calc_context)
            st.write(answer)
            with st.expander("แหล่งข้อมูลที่ใช้ตอบ"):
                for i, c in enumerate(context, 1):
                    st.markdown(f"**[{i}]** {c}")
                if calc_context:
                    st.markdown("**[calc]** ผลคำนวณจาก solar_calc.py")
                    st.code(calc_context)
        st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()