"""SolarPlus RAG Chatbot (S3).

Run locally: streamlit run app.py
Deploy: push to GitHub then Actions deploys to HuggingFace Space (Docker SDK)

RAG จาก solar_kb.md + คำนวณขนาด/ราคา/คืนทุนด้วย solar_calc.py
เลขทุกตัวมาจาก Python ไม่ให้ LLM คิดเอง
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

# แกนของงานออกแบบ: กลางวัน = ช่วงที่โซลาร์ช่วยได้ / กลางคืน = ช่วงที่ช่วยไม่ได้
# ลูกค้าเข้าใจผิดเรื่องนี้มากที่สุด เลยให้สีสองตัวนี้เป็นตัวเล่าเรื่องทั้งหน้า
INK = "#1C2438"        # น้ำเงินกรมท่า — กลางคืน, ตัวอักษร
SUN = "#E08A1E"        # เหลืองอำพัน — ช่วงที่โซลาร์ทำงาน
SUN_SOFT = "#F5C877"   # อำพันอ่อน — ส่วนกลางวันที่ยังไม่ถูกครอบคลุม
LINE = "#DED5C6"
MUTED = "#6B7385"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bai+Jamjuree:wght@500;600;700&family=IBM+Plex+Sans+Thai:wght@400;500;600&display=swap');

html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans Thai', sans-serif;
}}

/* ซ่อน chrome ของ Streamlit ที่ทำให้ดูเหมือนงาน demo */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding-top: 2.2rem; max-width: 780px; }}

h1, h2, h3, .sp-display {{
    font-family: 'Bai Jamjuree', sans-serif;
    letter-spacing: -0.01em;
}}

/* หัวเรื่อง */
.sp-head {{
    border-bottom: 1px solid {LINE};
    padding-bottom: 1.1rem;
    margin-bottom: 1.6rem;
}}
.sp-eyebrow {{
    font-family: 'Bai Jamjuree', sans-serif;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    color: {SUN};
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}}
.sp-title {{
    font-family: 'Bai Jamjuree', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: {INK};
    line-height: 1.15;
    margin: 0;
}}
.sp-sub {{
    color: {MUTED};
    font-size: 0.92rem;
    margin-top: 0.45rem;
}}

/* signature: แถบสัดส่วนกลางวัน/กลางคืน
   เล่าสิ่งที่ตารางตัวเลขเล่าไม่ได้ — ทำไมติดใหญ่เกินถึงไม่คุ้ม */
.sp-bar {{
    display: flex;
    height: 42px;
    border-radius: 3px;
    overflow: hidden;
    border: 1px solid {LINE};
    margin: 0.5rem 0 0.4rem;
}}
.sp-seg {{
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Bai Jamjuree', sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
}}
.sp-seg-covered {{ background: {SUN}; }}
.sp-seg-gap     {{ background: {SUN_SOFT}; color: {INK}; }}
.sp-seg-night   {{ background: {INK}; }}
.sp-legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.85rem;
    font-size: 0.72rem;
    color: {MUTED};
    margin-bottom: 1rem;
}}
.sp-dot {{
    display: inline-block; width: 9px; height: 9px;
    border-radius: 2px; margin-right: 5px;
}}

/* ตัวเลขผลลัพธ์ */
.sp-figure {{
    border-top: 1px solid {LINE};
    padding: 0.7rem 0 0.15rem;
}}
.sp-figure-label {{
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: {MUTED};
}}
.sp-figure-value {{
    font-family: 'Bai Jamjuree', sans-serif;
    font-size: 1.65rem;
    font-weight: 700;
    color: {INK};
    line-height: 1.2;
}}
.sp-figure-value small {{
    font-size: 0.85rem;
    font-weight: 500;
    color: {MUTED};
    margin-left: 3px;
}}

.sp-note {{
    font-size: 0.78rem;
    color: {MUTED};
    border-left: 2px solid {LINE};
    padding-left: 0.7rem;
    margin-top: 1rem;
    line-height: 1.6;
}}

/* chat */
[data-testid="stChatMessage"] {{
    background: transparent;
    padding: 0.35rem 0;
}}
.stChatInput textarea {{ font-family: 'IBM Plex Sans Thai', sans-serif; }}

/* ปุ่มคำถามตัวอย่าง */
div[data-testid="stButton"] > button {{
    font-family: 'IBM Plex Sans Thai', sans-serif;
    font-size: 0.82rem;
    font-weight: 400;
    color: {INK};
    background: transparent;
    border: 1px solid {LINE};
    border-radius: 999px;
    padding: 0.32rem 0.9rem;
    transition: border-color 0.15s ease, color 0.15s ease;
}}
div[data-testid="stButton"] > button:hover {{
    border-color: {SUN};
    color: {SUN};
}}
div[data-testid="stButton"] > button:focus-visible {{
    outline: 2px solid {SUN};
    outline-offset: 2px;
}}

@media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; animation: none !important; }}
}}
@media (max-width: 640px) {{
    .sp-title {{ font-size: 1.55rem; }}
    .block-container {{ padding-top: 1.4rem; }}
}}
</style>
"""

SAMPLE_QUESTIONS = [
    "ค่าไฟเดือนละ 3000 ควรติดกี่ kW",
    "ไฟดับแล้วโซลาร์ยังใช้ได้ไหม",
    "ติดตั้งใช้เวลากี่วัน",
    "ต้องเตรียมเอกสารอะไรบ้าง",
]


@st.cache_resource
def load_index():
    """โหลด solar_kb.md, split เป็น chunk, encode, สร้าง faiss index

    Cache เพราะโหลด model ครั้งแรกใช้เวลาประมาณ 30 วินาที
    Returns: (model, index, chunks_list)
    """
    with open(KB_PATH, "r", encoding="utf-8") as f:
        document = f.read()

    chunks = [c.strip() for c in document.split("\n\n") if c.strip()]

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
    return (
        "ผลการคำนวณจากระบบ (ใช้ตัวเลขชุดนี้ตอบเท่านั้น ห้ามคำนวณใหม่):\n"
        + solar_calc.format_th(result)
    )


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

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


def daylight_bar(result: dict) -> str:
    """Signature element — แถบสัดส่วนไฟกลางวัน/กลางคืน

    ส่วนสีเข้ม (กลางคืน) คือไฟที่ระบบ On-Grid แตะไม่ถึงไม่ว่าจะติดกี่ kW
    เป็นเหตุผลว่าทำไมขนาดที่แนะนำถึงไม่ได้ปัดขึ้นตามค่าไฟทั้งก้อน
    """
    total = result["monthly_units"]
    daytime = result["daytime_units"]
    covered = min(result["produced_units"], daytime)
    gap = max(daytime - covered, 0)
    night = max(total - daytime, 0)

    def pct(v):
        return (v / total * 100) if total else 0

    segments = [
        ("covered", pct(covered), f"{covered:,.0f} หน่วย"),
        ("gap", pct(gap), f"{gap:,.0f}" if pct(gap) > 8 else ""),
        ("night", pct(night), f"{night:,.0f} หน่วย"),
    ]
    bar = "".join(
        f'<div class="sp-seg sp-seg-{name}" style="width:{width}%">{label}</div>'
        for name, width, label in segments
        if width > 0
    )

    return f"""
<div class="sp-bar">{bar}</div>
<div class="sp-legend">
  <span><span class="sp-dot" style="background:{SUN}"></span>โซลาร์ครอบคลุม</span>
  <span><span class="sp-dot" style="background:{SUN_SOFT}"></span>กลางวันที่เหลือ</span>
  <span><span class="sp-dot" style="background:{INK}"></span>กลางคืน</span>
</div>
"""


def figure(label: str, value: str, unit: str = "") -> str:
    unit_html = f"<small>{unit}</small>" if unit else ""
    return (
        f'<div class="sp-figure"><div class="sp-figure-label">{label}</div>'
        f'<div class="sp-figure-value">{value}{unit_html}</div></div>'
    )


def render_sidebar():
    """เครื่องคำนวณแบบกรอกเอง — ไม่ผ่าน LLM เลย ผลลัพธ์ตรวจสอบได้ 100%"""
    with st.sidebar:
        st.markdown(
            '<div class="sp-eyebrow">ประเมินเบื้องต้น</div>'
            '<div class="sp-display" style="font-size:1.15rem;font-weight:600;'
            f'color:{INK};margin-bottom:0.9rem">คิดขนาดระบบจากค่าไฟ</div>',
            unsafe_allow_html=True,
        )

        bill = st.number_input(
            "ค่าไฟเฉลี่ยต่อเดือน (บาท)",
            min_value=float(solar_calc.MIN_BILL),
            max_value=float(solar_calc.MAX_BILL),
            value=3000.0,
            step=500.0,
        )
        usage_label = st.selectbox(
            "ใครอยู่บ้านช่วงกลางวัน",
            list(solar_calc.DAYTIME_RATIO_PRESETS.keys()),
            index=1,
        )

        ratio = solar_calc.DAYTIME_RATIO_PRESETS[usage_label]
        try:
            result = solar_calc.estimate(bill, ratio)
        except solar_calc.EstimateError as exc:
            st.warning(str(exc))
            return

        st.markdown(daylight_bar(result), unsafe_allow_html=True)
        st.markdown(
            figure("ขนาดที่แนะนำ", f"{result['recommended_kw']}", " kW")
            + figure("ราคาประเมิน", f"{result['price']:,}", " บาท")
            + figure("คืนทุนประมาณ", f"{result['payback_years']}", " ปี")
            + figure("ประหยัดต่อเดือน", f"{result['monthly_saving']:,.0f}", " บาท"),
            unsafe_allow_html=True,
        )

        if not result["worthwhile"]:
            st.markdown(
                '<div class="sp-note">ค่าไฟระดับนี้ทำให้คืนทุนนานกว่า 10 ปี '
                'ปรึกษาทางร้านก่อนตัดสินใจจะดีกว่า</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="sp-note">เป็นการประเมินเบื้องต้นจากค่าไฟอย่างเดียว '
            'ขนาดและราคาจริงต้องสำรวจหลังคาหน้างานก่อน</div>',
            unsafe_allow_html=True,
        )


def render_header():
    st.markdown(
        '<div class="sp-head">'
        '<div class="sp-eyebrow">โซลาร์พลัส</div>'
        '<h1 class="sp-title">ถามเรื่องโซลาร์เซลล์<br>ก่อนโทรหาทางร้าน</h1>'
        '<div class="sp-sub">ขนาดระบบ ราคา ระยะคืนทุน เอกสาร และการรับประกัน '
        'ตอบได้ทันทีตลอดเวลา</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def answer_and_store(prompt, model, index, chunks):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("กำลังค้นข้อมูล"):
            context = retrieve_top_k(prompt, model, index, chunks)
            calc_context = build_calc_context(prompt)
            answer = generate_answer(prompt, context, calc_context)
        st.write(answer)
        with st.expander("ข้อมูลที่ใช้ตอบ"):
            for i, c in enumerate(context, 1):
                st.markdown(f"**{i}.** {c}")
            if calc_context:
                st.markdown("**คำนวณโดย** `solar_calc.py`")
                st.code(calc_context)
    st.session_state.messages.append({"role": "assistant", "content": answer})


def main():
    st.set_page_config(
        page_title="โซลาร์พลัส — ปรึกษาโซลาร์เซลล์",
        page_icon="☀️",
        layout="centered",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    try:
        model, index, chunks = load_index()
    except FileNotFoundError:
        st.error(f"ไม่พบไฟล์ {KB_PATH} วางไว้ในโฟลเดอร์เดียวกับ app.py แล้วรีสตาร์ท")
        st.stop()

    render_header()
    render_sidebar()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # หน้าว่างคือคำเชิญให้เริ่ม ไม่ใช่ที่ว่างเปล่า — เสนอคำถามที่ลูกค้าถามจริง
    if not st.session_state.messages:
        st.markdown(
            f'<div style="font-size:0.82rem;color:{MUTED};margin-bottom:0.5rem">'
            'เริ่มจากคำถามที่ลูกค้าถามบ่อย</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, q in enumerate(SAMPLE_QUESTIONS):
            if cols[i % 2].button(q, key=f"q{i}", use_container_width=True):
                answer_and_store(q, model, index, chunks)
                st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("พิมพ์คำถาม เช่น ค่าไฟเดือนละ 3000 ควรติดกี่ kW"):
        answer_and_store(prompt, model, index, chunks)


if __name__ == "__main__":
    main()