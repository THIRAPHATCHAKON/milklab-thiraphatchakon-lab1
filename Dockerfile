FROM python:3.11-slim

# HF Spaces แนะนำให้รันด้วย user id 1000 ไม่ใช่ root
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    # sentence-transformers จะโหลด model มาเก็บที่นี่ ต้องเป็น dir ที่ user เขียนได้
    HF_HOME=/home/user/.cache/huggingface \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    # ปิด usage stats กัน warning รกใน log
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# โหลด embedding model ตั้งแต่ตอน build เลย
# ไม่งั้นผู้ใช้คนแรกที่เปิดแอปต้องรอโหลด 30 วินาที แล้วมักจะ timeout
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

COPY --chown=user . .

EXPOSE 8501

# healthcheck ของ Streamlit เอง ใช้ให้ HF รู้ว่าแอปพร้อมแล้ว
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]