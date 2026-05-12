# MindRead V3 — API + Frontend in one container
#
# CPU-only build (no CUDA). For GPU support, see the optional `cuda` stage at
# the bottom. The CPU image still ships with llama-cpp-python so customers
# with no LLM service can run the local Qwen path if they have models on disk.
#
# Build:    docker compose build api
# Standalone build: docker build -t mindread:v3 .

FROM python:3.12-slim AS base

# Build deps for llama-cpp-python (it compiles a small C++ extension on install),
# plus curl for the container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so docker cache survives code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code (engine + frontend + ontology)
COPY api_v3.py ./
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY frontend/ ./frontend/

# Data directory (JSONL, logs) is a mount point — empty at build time
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QDRANT_HOST=qdrant \
    QDRANT_PORT=6333 \
    QDRANT_COLLECTION_V3=mindread_v3 \
    EMBEDDING_MODEL=intfloat/e5-large-v2 \
    EMBEDDING_DEVICE=auto \
    HF_HOME=/cache/huggingface \
    TRANSFORMERS_CACHE=/cache/huggingface

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fs http://localhost:8000/api/health | grep -q healthy || exit 1

CMD ["uvicorn", "api_v3:app", "--host", "0.0.0.0", "--port", "8000"]


# ─── Optional CUDA stage ──────────────────────────────────────────────────
# For customers with GPU. Build with:
#   docker build --target cuda -t mindread:v3-cuda .
# Requires nvidia-container-toolkit on the host.
#
# FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS cuda
# RUN apt-get update && apt-get install -y --no-install-recommends \
#         python3.12 python3.12-venv python3-pip build-essential cmake git curl
# # ... mirror the base stage steps, but install with:
# # CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-cache-dir llama-cpp-python
# # and PyTorch with cu124 wheel.
