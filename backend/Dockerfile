# Python 3.12 in-container avoids host-side wheel issues on newer interpreters.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (from PyTorch's CPU wheel index) so sentence-transformers
# doesn't drag in the multi-GB CUDA build. Must precede requirements.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image: first request is instant and the
# container needs no network at runtime to embed.
ENV HF_HOME=/srv/.hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000
# Railway (and most PaaS) inject $PORT; fall back to 8000 for plain `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
