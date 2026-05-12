"""
Lokaler LLM Provider — Drop-in-Replacement für OpenAI Chat-Completions.

Lädt ein GGUF-Modell via llama-cpp-python einmal beim Import, hält es im RAM.
Exportiert `chat_complete(system, user)` mit demselben Vertrag wie der OpenAI-Pfad.

Konfiguration via Umgebungsvariablen (keine hardcoded Pfade):
  LOCAL_LLM_ENABLED=1           # api_v3 nutzt diesen Pfad statt OpenAI
  LOCAL_LLM_GGUF=/full/path.gguf  # exakter Modellpfad (höchste Priorität)
  LOCAL_LLM_MODEL_DIR=/dir       # Verzeichnis in dem nach GGUFs gesucht wird
  LOCAL_LLM_SIZE=2b|4b           # Größen-Preference wenn LOCAL_LLM_GGUF leer
  LOCAL_LLM_THREADS=12
  LOCAL_LLM_N_GPU_LAYERS=999     # alle Layer auf GPU; 0 = pure CPU
  LOCAL_LLM_CTX=8192

Usage als Speed-Test:
  venv/bin/python3 scripts/llm_local.py --query "Filme wie John Wick aber lustiger"
"""
from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from typing import Any, Dict, Optional, List

ROOT = Path(__file__).resolve().parent.parent

# Filename-Patterns pro Größen-Preference. Werden im LOCAL_LLM_MODEL_DIR gesucht.
_SIZE_PATTERNS = {
    "2b": ["Qwen3.5-2B-Q6_K.gguf", "qwen2.5-2b-instruct-q6_k.gguf",
           "Qwen3.5-2B*.gguf", "qwen*2b*.gguf"],
    "4b": ["Qwen3.5-4B-Q5_K_M.gguf", "qwen2.5-4b-instruct-q5_k_m.gguf",
           "Qwen3.5-4B*.gguf", "qwen*4b*.gguf"],
}

_LLM = None


def _resolve_gguf_path() -> str:
    """Find a GGUF model file via env config; no hardcoded paths.

    Priority:
      1. LOCAL_LLM_GGUF (exact path)
      2. LOCAL_LLM_MODEL_DIR + LOCAL_LLM_SIZE (glob lookup)
      3. error with helpful message

    Audit Pfusch #1 fix — previously had hardcoded USB-HDD paths in DEFAULTS.
    """
    exact = os.environ.get("LOCAL_LLM_GGUF")
    if exact:
        if not Path(exact).exists():
            raise RuntimeError(f"LOCAL_LLM_GGUF={exact!r} does not exist")
        return exact

    model_dir = os.environ.get("LOCAL_LLM_MODEL_DIR")
    size = os.environ.get("LOCAL_LLM_SIZE", "2b")
    patterns = _SIZE_PATTERNS.get(size, _SIZE_PATTERNS["2b"])

    candidates: List[Path] = []
    if model_dir:
        d = Path(model_dir)
        if not d.is_dir():
            raise RuntimeError(f"LOCAL_LLM_MODEL_DIR={model_dir!r} is not a directory")
        for pat in patterns:
            candidates.extend(d.rglob(pat))
    if not candidates:
        raise RuntimeError(
            "No GGUF model found. Set one of:\n"
            "  LOCAL_LLM_GGUF=/absolute/path/to/model.gguf  (exact)\n"
            "  LOCAL_LLM_MODEL_DIR=/dir/with/ggufs  (auto-discover by LOCAL_LLM_SIZE={2b,4b})\n"
            f"Searched patterns: {patterns}"
        )
    # Prefer exact matches over glob results — stable sort keeps first preferred file
    candidates.sort(key=lambda p: (p.name not in patterns, p.name))
    return str(candidates[0])


def get_llm():
    global _LLM
    if _LLM is not None:
        return _LLM
    from llama_cpp import Llama
    gguf = _resolve_gguf_path()
    n_threads = int(os.environ.get("LOCAL_LLM_THREADS", "12"))
    n_ctx = int(os.environ.get("LOCAL_LLM_CTX", "8192"))
    n_gpu_layers = int(os.environ.get("LOCAL_LLM_N_GPU_LAYERS", "0"))
    print(f"[local_llm] loading {gguf}  (threads={n_threads}, ctx={n_ctx}, gpu_layers={n_gpu_layers})", flush=True)
    t0 = time.time()
    _LLM = Llama(model_path=gguf, n_ctx=n_ctx, n_threads=n_threads,
                 n_gpu_layers=n_gpu_layers, verbose=False)
    print(f"[local_llm] loaded in {time.time()-t0:.1f}s", flush=True)
    return _LLM


def chat_complete(system: str, user: str, max_tokens: int = 1500,
                  temperature: float = 0.1) -> str:
    """JSON-output chat completion. Returns the assistant content string."""
    llm = get_llm()
    out = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return out["choices"][0]["message"]["content"]


def llm_query_to_dna_local(query: str, system_prompt: str,
                            ontology: Dict[str, Any]) -> Dict[str, Any]:
    """Drop-in replacement for the OpenAI llm_query_to_dna in api_v3.

    Uses the canonical `build_query_user_prompt` + `parse_query_dna` from
    extract_dna_v3.py, so this local-LLM path stays in sync with the OpenAI
    path automatically (audit F-005 + F-006).
    """
    sys.path.insert(0, str(ROOT))
    from scripts.extract_dna_v3 import build_query_user_prompt, parse_query_dna
    user = build_query_user_prompt(query)
    text = chat_complete(system_prompt, user, max_tokens=1500, temperature=0.1)
    raw = json.loads(text)
    return parse_query_dna(raw, query, ontology)


# ─── Speed test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    sys.path.insert(0, str(ROOT))
    from scripts.extract_dna_v3 import build_system_prompt, load_ontology, load_env
    load_env()

    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="Filme wie John Wick aber lustiger")
    ap.add_argument("--size", default="2b", choices=["2b", "4b"])
    ap.add_argument("--repeat", type=int, default=3, help="number of warm runs")
    args = ap.parse_args()

    os.environ["LOCAL_LLM_SIZE"] = args.size
    ont = load_ontology()
    system = build_system_prompt(ont)

    print(f"\nSystem prompt: {len(system)} chars (~{len(system)//4} tokens)")
    print(f"Query: {args.query!r}\n")

    # Warmup load
    get_llm()

    times = []
    for i in range(args.repeat):
        t0 = time.time()
        try:
            dna = llm_query_to_dna_local(args.query, system, ont)
        except Exception as e:
            print(f"  Run {i+1}: FAILED — {e}")
            continue
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  Run {i+1}/{args.repeat}: {elapsed:.1f}s")
        if i == 0:
            print(f"    intent.emotion: {list(dna.get('emotion_sparse',{}).items())[:3]}")
            print(f"    intent.theme:   {list(dna.get('theme_sparse',{}).items())[:3]}")
            print(f"    similar_to_title: {dna.get('similar_to_title')!r}")
    if times:
        avg = sum(times) / len(times)
        print(f"\nAvg per call: {avg:.1f}s  (min {min(times):.1f}s, max {max(times):.1f}s)")
        print(f"For 7000 films batch-extract: {avg*7000/3600:.1f} hours")
