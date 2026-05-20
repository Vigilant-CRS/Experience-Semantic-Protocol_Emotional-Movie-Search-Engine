# Third-Party Notices

Vigilant ESP (Experience Semantic Protocol; engine codename MindRead V3)
bundles or depends on the following third-party software and data. Each
component is used under its own license. This document satisfies the
attribution requirements of those licenses. The Vigilant ESP proprietary
license (see `LICENSE`) does **not** override or restrict your rights
under any of the licenses below.

If you redistribute a binary, container image or appliance that contains
Vigilant ESP, you must redistribute this `THIRD_PARTY_NOTICES.md` file
alongside it.

---

## 1. Runtime infrastructure

### Qdrant (vector database)
- **Project:** Qdrant — https://github.com/qdrant/qdrant
- **Version shipped:** v1.14.1 (Docker image `qdrant/qdrant:v1.14.1`)
- **License:** Apache License 2.0 — https://github.com/qdrant/qdrant/blob/master/LICENSE
- **Use in Vigilant ESP:** vector store for `synopsis_dense`, `emotion_sparse`,
  `theme_sparse`, `subject_sparse` and the per-film payload. Container is
  pulled at deploy time; Vigilant ESP does not fork or modify the Qdrant
  source code.

### FastAPI
- **Project:** FastAPI — https://github.com/tiangolo/fastapi
- **License:** MIT — https://github.com/tiangolo/fastapi/blob/master/LICENSE
- **Use in Vigilant ESP:** HTTP/JSON API framework (`api_v3.py`).

### Uvicorn
- **Project:** Uvicorn — https://github.com/encode/uvicorn
- **License:** BSD-3-Clause — https://github.com/encode/uvicorn/blob/master/LICENSE.md
- **Use in Vigilant ESP:** ASGI server hosting the FastAPI app.

### Pydantic
- **Project:** Pydantic — https://github.com/pydantic/pydantic
- **License:** MIT — https://github.com/pydantic/pydantic/blob/main/LICENSE
- **Use in Vigilant ESP:** request/response schemas.

### Requests
- **Project:** Requests — https://github.com/psf/requests
- **License:** Apache License 2.0 — https://github.com/psf/requests/blob/main/LICENSE
- **Use in Vigilant ESP:** HTTP client (TMDB enrichment scripts, OpenAI HTTPS).

### PyYAML
- **Project:** PyYAML — https://github.com/yaml/pyyaml
- **License:** MIT — https://github.com/yaml/pyyaml/blob/main/LICENSE
- **Use in Vigilant ESP:** loading `config/engine_params.yaml`.

### tqdm
- **Project:** tqdm — https://github.com/tqdm/tqdm
- **License:** MPL-2.0 + MIT — https://github.com/tqdm/tqdm/blob/master/LICENCE
- **Use in Vigilant ESP:** progress bars in batch scripts and dependencies.

---

## 2. Embeddings & ML

### sentence-transformers
- **Project:** sentence-transformers — https://github.com/UKPLab/sentence-transformers
- **License:** Apache License 2.0 — https://github.com/UKPLab/sentence-transformers/blob/master/LICENSE
- **Use in Vigilant ESP:** loading and inference of the E5 embedding model.

### transformers (Hugging Face)
- **Project:** transformers — https://github.com/huggingface/transformers
- **License:** Apache License 2.0 — https://github.com/huggingface/transformers/blob/main/LICENSE
- **Use in Vigilant ESP:** transitive dependency of sentence-transformers.

### huggingface_hub
- **Project:** huggingface_hub — https://github.com/huggingface/huggingface_hub
- **License:** Apache License 2.0 — https://github.com/huggingface/huggingface_hub/blob/main/LICENSE
- **Use in Vigilant ESP:** model download at first start.

### accelerate, safetensors
- **Project:** accelerate (Apache 2.0), safetensors (Apache 2.0) — both Hugging Face.
- **Use in Vigilant ESP:** transitive dependencies.

### PyTorch
- **Project:** PyTorch — https://github.com/pytorch/pytorch
- **License:** BSD-3-Clause — https://github.com/pytorch/pytorch/blob/main/LICENSE
- **Use in Vigilant ESP:** tensor backend for sentence-transformers / transformers.

### NumPy, SciPy, scikit-learn
- **Licenses:** NumPy (BSD-3), SciPy (BSD-3), scikit-learn (BSD-3).
- **Use in Vigilant ESP:** numeric arrays, sparse vectors, normalization, similarity.

---

## 3. Embedding model (downloaded at runtime, not redistributed)

### intfloat/e5-large-v2
- **Model card:** https://huggingface.co/intfloat/e5-large-v2
- **License:** MIT (per Hugging Face model card)
- **Use in Vigilant ESP:** `synopsis_dense` channel — 1024-dimensional English
  text embedding. Vigilant ESP does not modify or redistribute the model
  weights; they are downloaded from Hugging Face on first start of the
  container.

If the licensee wishes to deploy an offline appliance, the model weights
must be pre-cached into the image. The downstream user remains bound by
the upstream license.

---

## 4. Local LLM path (optional, only when `LOCAL_LLM_ENABLED=1`)

### llama-cpp-python
- **Project:** llama-cpp-python — https://github.com/abetlen/llama-cpp-python
- **License:** MIT — https://github.com/abetlen/llama-cpp-python/blob/main/LICENSE.md
- **Use in Vigilant ESP:** GGUF inference on the local machine when OpenAI is
  not available.

### llama.cpp (transitive C/C++ runtime)
- **Project:** llama.cpp — https://github.com/ggerganov/llama.cpp
- **License:** MIT — https://github.com/ggerganov/llama.cpp/blob/master/LICENSE

### Qwen 3.5 4B GGUF (model weights — not redistributed by Vigilant ESP)
- **Upstream model:** Qwen3.5 — https://huggingface.co/Qwen
- **License:** Tongyi Qianwen License Agreement —
  https://github.com/QwenLM/Qwen/blob/main/Tongyi%20Qianwen%20LICENSE%20AGREEMENT
  (additional commercial-use clause: services with >100M MAU need to
  apply for a separate license from Alibaba.)
- **Use in Vigilant ESP:** offline DNA extraction (batch path). The
  licensee is responsible for obtaining the weights and complying with
  Alibaba's terms.

---

## 5. OpenAI API (network service, no code or weights redistributed)

- **Service:** OpenAI Chat Completions — https://platform.openai.com
- **Terms:** https://openai.com/policies/business-terms
- **Use in Vigilant ESP:** runtime LLM for query-intent extraction and the
  per-film DNA enrichment scripts. Each licensee uses their own
  `OPENAI_API_KEY` and is bound by OpenAI's Business Terms directly.
  Vigilant ESP does not proxy, resell or repackage OpenAI's service.

---

## 6. Film metadata source

### The Movie Database (TMDB)
- **Source:** https://www.themoviedb.org
- **API terms:** https://www.themoviedb.org/api-terms-of-use
- **Mandatory attribution** (per TMDB §6 of the API Terms of Use):

  > This product uses the TMDB API but is not endorsed or certified by TMDB.

  This notice MUST be displayed visibly to end users in any product
  built on Vigilant ESP (the bundled `frontend/index.html` carries it
  in the footer).

- **Logo:** when the TMDB API is used, the TMDB logo should accompany
  the attribution. Licensees may obtain the logo at
  https://www.themoviedb.org/about/logos-attribution.

- **Use in Vigilant ESP:** the demo corpus shipped with Vigilant ESP is derived
  from TMDB's public film data (titles, overviews, posters, vote counts,
  release dates, providers). Posters are served directly from
  `image.tmdb.org` — they are NOT copied into the Vigilant ESP distribution.

- **End-user implications:** the licensee remains responsible for
  honoring TMDB's terms when ingesting their own catalog through
  `POST /api/admin/films`. Vigilant ESP does not modify TMDB content; it
  computes derived structured tags ("DNA") from the supplied metadata.

---

## 7. Other transitive dependencies

All other Python packages installed transitively via `pip install -r
requirements.txt` are distributed under permissive open-source licenses
(MIT, BSD, Apache 2.0). A machine-readable manifest of the exact
versions and licenses can be produced at build time with

    pip-licenses --format=markdown --order=name > LICENSES_MANIFEST.md

The output of that command, when run against a clean install of the
shipped `requirements.txt`, is incorporated by reference and forms part
of these notices.

---

## 8. Trademarks

"Qdrant", "Hugging Face", "OpenAI", "PyTorch", "FastAPI", "TMDB",
"The Movie Database" and "Qwen" are trademarks of their respective
owners. Use of these names in Vigilant ESP is purely descriptive and does
not imply any endorsement.

---

*Last reviewed: 2026-05-14.*
