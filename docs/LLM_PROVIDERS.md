# Vigilant ESP — LLM Provider Swap & Configure

*Experience Semantic Protocol. Engine codename: MindRead V3.
Proprietary commercial software — see [`../LICENSE`](../LICENSE).*

Vigilant ESP trennt **welches LLM** den Intent extrahiert von **wie** es
das tut. Du kannst jedes der drei Pfade verwenden, indem du eine Handvoll
Environment-Variablen setzt — kein Code-Change nötig.

| Pfad | Aktiviert durch | Latenz pro Query | Kosten |
|---|---|---|---|
| **OpenAI Cloud** | `OPENAI_API_KEY=sk-…` | ~2-3 s | $0.0003 / Query |
| **OpenAI-kompatibler Endpoint** (Azure, Together, Groq, vLLM, Ollama) | `OPENAI_BASE_URL=https://…` + `OPENAI_API_KEY=…` | je nach Anbieter | je nach Anbieter |
| **Lokales GGUF via llama.cpp** | `LOCAL_LLM_ENABLED=1` + `LOCAL_LLM_GGUF=/path.gguf` | ~5-100 s je nach GPU | $0 (Strom) |

---

## 1. OpenAI Cloud (Default)

Einfachster Pfad. In `.env`:

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL_DNA=gpt-5.4-mini      # Default. Beliebiges Chat-Completions-Modell.
# OPENAI_BASE_URL bleibt leer → api.openai.com
```

Modell-Tipp: `gpt-5.4-mini` ist optimaler Trade-off Qualität/$/Latenz. Für
höhere Qualität ohne Code-Change: `OPENAI_MODEL_DNA=gpt-5` oder
`OPENAI_MODEL_DNA=gpt-5.4`. Für noch billiger:
`OPENAI_MODEL_DNA=gpt-5.4-nano` (geringere Tag-Recall-Quote).

---

## 2. OpenAI-kompatibler Endpoint

Funktioniert mit jedem Anbieter, der das Chat-Completions-Schema spricht.

### Azure OpenAI
```env
OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/deployments/<deployment>
OPENAI_API_KEY=<azure-key>
OPENAI_MODEL_DNA=gpt-5.4-mini      # ignoriert, deployment-name in URL
```

### Together.ai / Groq / Fireworks
```env
OPENAI_BASE_URL=https://api.together.xyz/v1
OPENAI_API_KEY=<together-key>
OPENAI_MODEL_DNA=meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
```

### vLLM (selbst-gehostet)
```env
OPENAI_BASE_URL=http://vllm.internal:8000/v1
OPENAI_API_KEY=dummy               # vLLM ignoriert den Key, MUSS aber gesetzt sein
OPENAI_MODEL_DNA=meta-llama/Llama-3.1-8B-Instruct
```

### Ollama (lokal, einfach)
```env
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL_DNA=llama3.1:8b-instruct-q5_K_M
```

**Wichtig:** MindRead schickt strikt JSON-Output. Manche kleine Modelle
(< 7B) halten das Format nicht ein und produzieren Markdown-Wrapper.
In dem Fall:
- empirisch verifizieren: `venv/bin/python3 scripts/eval_v3.py --query "Mafiafilme"`
- ggf. größeres Modell wählen
- als Fallback `LOCAL_LLM_ENABLED=1` mit einem stärkeren GGUF

---

## 3. Lokales GGUF via llama.cpp

Für air-gapped Deployments, Compliance oder Kostenstrich. Voraussetzung:
`llama-cpp-python` ist in `requirements.txt` enthalten — die CUDA-Variante
wird automatisch gebaut, wenn `CUDA_HOME` zur Build-Zeit gesetzt ist
(siehe `Dockerfile`).

### Qwen 3.5 4B (default, getestet)
```env
LOCAL_LLM_ENABLED=1
LOCAL_LLM_GGUF=/models/Qwen3.5-4B-Q5_K_M.gguf
LOCAL_LLM_N_GPU_LAYERS=999         # alle Layer auf GPU; 0 = CPU-only
LOCAL_LLM_CTX=8192                  # 4096 default reicht NICHT für volle Ontologie
LOCAL_LLM_THREADS=12
```
Lizenz: **Tongyi Qianwen** — siehe `THIRD_PARTY_NOTICES.md` §4.
> Achtung: bei >100 M MAU braucht der Kunde eine separate Alibaba-Lizenz.

### Llama 3.1 8B (Empfehlung wenn Qwen-Lizenz nicht passt)
```env
LOCAL_LLM_ENABLED=1
LOCAL_LLM_GGUF=/models/Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf
LOCAL_LLM_N_GPU_LAYERS=999
LOCAL_LLM_CTX=8192
```
Lizenz: Llama 3.1 Community License (kommerziell frei bis 700 M MAU).
Source: `https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct`.

### Mistral 7B / Mixtral 8x7B
```env
LOCAL_LLM_ENABLED=1
LOCAL_LLM_GGUF=/models/mistral-7b-instruct-v0.3.Q5_K_M.gguf
LOCAL_LLM_N_GPU_LAYERS=999
LOCAL_LLM_CTX=8192
```
Lizenz: Apache 2.0 — wirklich frei.

### Phi-3 Mini (3.8B, leichtgewichtig)
```env
LOCAL_LLM_ENABLED=1
LOCAL_LLM_GGUF=/models/Phi-3-mini-4k-instruct.Q5_K_M.gguf
LOCAL_LLM_N_GPU_LAYERS=999
LOCAL_LLM_CTX=4096
```
Lizenz: MIT. Schnell auf CPU, aber JSON-Stabilität bei großen Prompts
schwächer — bitte mit Eval testen.

### GGUF auto-discovery (statt expliziter Pfad)
Wenn du mehrere GGUFs in einem Verzeichnis hast:
```env
LOCAL_LLM_MODEL_DIR=/models
LOCAL_LLM_SIZE=4b                  # sucht nach *4b*.gguf, *Q5_K_M*, etc.
```
Die Discovery-Pattern stehen in `scripts/llm_local.py:MODEL_PATTERNS`.

---

## Mischbetrieb: schneller Cloud-Pfad für Live-Queries, Local für Batch

Häufiges Muster: OpenAI für API-Latenz, lokales LLM für Bulk-Ingest.

`.env` für die Live-API:
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL_DNA=gpt-5.4-mini
# LOCAL_LLM_ENABLED leer → API nutzt OpenAI
```

Beim Bulk-Ingest CLI-Flag `--local-llm` setzen:
```bash
venv/bin/python3 scripts/extract_dna_v3.py --local-llm --workers 4 --source data/catalog.json
```

`extract_dna_v3.py` ignoriert dann `OPENAI_API_KEY` und routet auf den
GGUF-Pfad. Skaliert auf jeder Hardware mit CUDA-fähiger GPU.

---

## Eval nach Provider-Swap (Pflicht vor Produktion)

```bash
venv/bin/python3 scripts/eval_v3.py
```

Das Suite hat 29 Test-Queries (Genre, Tone-Shift, Avoid-Content,
Gender-Flip, Year-Range, Subject-Query). Pass-Rate sollte ≥ 80% sein,
LLM-Varianz ±5%. Bei < 70% Provider/Modell tauschen.

Erwartete Pass-Raten je Modell-Klasse (empirisch, ohne Garantie):
- GPT-5.4-mini / GPT-5.4 / GPT-5 → 24-27/29
- Llama 3.1 70B / Mixtral 8x7B → 22-25/29
- Llama 3.1 8B / Qwen 3.5 4B → 19-23/29
- Phi-3 Mini → 15-20/29

---

## Was MindRead vom LLM erwartet (für eigenes Tuning)

- Streng JSON-Output (kein Markdown-Fence)
- Tool-Use NICHT benötigt (alles im Prompt)
- Context-Window ≥ 8 K (System-Prompt ist ~3 K, mit User-Prompt + Few-Shot ~5 K)
- Function-Calling NICHT genutzt — pure Text-Completion
- Temperatur 0.1 (in `extract_dna_v3.py:_chat_payload` hartcodiert)

Wenn das alles passt → das Modell läuft mit MindRead.
