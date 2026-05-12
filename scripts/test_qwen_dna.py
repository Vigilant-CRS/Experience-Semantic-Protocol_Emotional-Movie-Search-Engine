"""Test Qwen 3.5 4B on the 3 pilot films, compare DNAs to OpenAI baseline."""
import json, time, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.extract_dna_v3 import build_system_prompt, build_user_prompt, load_ontology, normalize_dna

from llama_cpp import Llama

GGUF = "/media/dd/USB_4028/Projekte/Temp/Vigilant-Models/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q5_K_M.gguf"
print(f"Loading {GGUF}", flush=True)
t0 = time.time()
llm = Llama(model_path=GGUF, n_ctx=8192, n_threads=10, verbose=False)
print(f"Loaded in {time.time()-t0:.1f}s", flush=True)

ont = load_ontology()
system = build_system_prompt(ont)
print(f"System prompt: {len(system)} chars", flush=True)

# load source films + OpenAI baseline DNAs
movies = json.load(open("movies_export.json"))
by_id = {m["tmdb_id"]: m for m in movies}

baseline = {}
for fp in ("data/movies_dna_v3.jsonl", "data/movies_dna_v3.pilot.jsonl"):
    for line in open(fp):
        r = json.loads(line)
        baseline[r["tmdb_id"]] = r["dna_v3"]

targets = [(245891, "John Wick"), (194, "Amélie"), (1813, "Devil's Advocate")]

for tid, name in targets:
    film = by_id[tid]
    user = build_user_prompt(film)
    print(f"\n{'='*70}\n  {name} ({tid})\n{'='*70}", flush=True)

    t0 = time.time()
    out = llm.create_chat_completion(
        messages=[{"role":"system","content":system},
                  {"role":"user","content":user}],
        max_tokens=800,
        temperature=0.1,
        response_format={"type":"json_object"},
    )
    elapsed = time.time() - t0
    raw_text = out["choices"][0]["message"]["content"]
    usage = out["usage"]
    print(f"  Time: {elapsed:.1f}s  ({usage['completion_tokens']} out tokens, {usage['completion_tokens']/elapsed:.1f} tok/s)", flush=True)

    try:
        raw = json.loads(raw_text)
    except Exception as e:
        print(f"  JSON FAIL: {e}\n  Raw: {raw_text[:300]}")
        continue

    qwen_dna = normalize_dna(raw, ont)

    # compare
    def fmt(d):
        return ", ".join(f"{k}={v:.2f}" for k,v in sorted(d.items(), key=lambda x:-x[1])[:5])

    op = baseline.get(tid, {})
    print(f"\n  EMOTION  Qwen: {fmt(qwen_dna['emotion_sparse'])}")
    print(f"           OpenAI: {fmt(op.get('emotion_sparse', {}))}")
    print(f"\n  THEME    Qwen: {fmt(qwen_dna['theme_sparse'])}")
    print(f"           OpenAI: {fmt(op.get('theme_sparse', {}))}")
    print(f"\n  Setting  Qwen: {qwen_dna['setting']}")
    print(f"           OpenAI: {op.get('setting')}")
    print(f"\n  Archet.  Qwen: {qwen_dna['archetype']}     OpenAI: {op.get('archetype')}")
    print(f"  Mood     Qwen: {qwen_dna['mood']}")
    print(f"           OpenAI: {op.get('mood')}")
    print(f"  Pacing   Qwen: {qwen_dna['pacing']}")
    print(f"           OpenAI: {op.get('pacing')}")
    print(f"  Gender   Qwen: {qwen_dna['protagonist_gender']}     OpenAI: {op.get('protagonist_gender')}")

    # overlap metric
    def overlap(a, b):
        keys = set(a.keys()) | set(b.keys())
        if not keys: return 0
        agree = sum(min(a.get(k,0), b.get(k,0)) for k in keys)
        return agree
    eo = overlap(qwen_dna['emotion_sparse'], op.get('emotion_sparse', {}))
    to = overlap(qwen_dna['theme_sparse'], op.get('theme_sparse', {}))
    print(f"\n  L1 overlap  emotion: {eo:.2f}  theme: {to:.2f}  (1.0 = identical)")
