# Learning Buddy di Hugging Face Space (SDK Docker, hardware GPU 1x L4 24 GB).
# Berkas ini diunggah ke repo Space oleh deploy/hf/unggah_hf.py, bersama mulai.sh dan
# requirements. Kode program TIDAK ikut ke repo Space (Space publik, isinya terlihat orang):
# mulai.sh mengunduhnya dari repo dataset private saat Space menyala.
FROM python:3.11-slim

# HF menjalankan container sebagai uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt requirements-gpu.txt ./
# torch dipatok sama dengan Pegasus (2.8.0 CUDA 12.6) agar pip tidak menggantinya;
# transformers >= 4.51 dibutuhkan Qwen3-Embedding.
RUN pip install --user "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu126 && \
    pip install --user -r requirements.txt -r requirements-gpu.txt "torch==2.8.0" \
        "transformers>=4.51" "huggingface_hub>=0.34"

COPY --chown=user mulai.sh ./
EXPOSE 7860
CMD ["bash", "mulai.sh"]
