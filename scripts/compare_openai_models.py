"""Run our DNA extraction on 3 pilot films across multiple OpenAI models, compare quality+latency+cost."""
import json, time, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.extract_dna_v3 import build_system_prompt, build_user_prompt, load_ontology, normalize_dna, load_env

import requests

load_env()

# OpenAI pricing per 1M tokens (USD), as of 2026-04-30
# Sources: api.openai.com/pricing — verify before billing
PRICING = {
    "gpt-4.1-mini":   {"in": 0.40, "out": 1.60},
    "gpt-4.1-nano":   {"in": 0.10, "out": 0.40},
    "gpt-5-mini":     {"in": 0.25, "out": 2.00},
    "gpt-5-nano":     {"in": 0.05, "out": 0.40},
    "gpt-5.4-mini":   {"in": 0.25, "out": 2.00},   # likely same tier as gpt-5-mini
    "gpt-5.4-nano":   {"in": 0.05, "out": 0.40},   # likely same tier as gpt-5-nano
}
MODELS = [
    "gpt-4.1-mini",   # current baseline (one year old)
    "gpt-4.1-nano",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.4-mini",   # current generation mini
    "gpt-5.4-nano",   # current generation nano
]

ont = load_ontology()
system = build_system_prompt(ont)

movies = json.load(open("movies_export.json"))
by_id = {m["tmdb_id"]: m for m in movies}

baseline = {}
for fp in ("data/movies_dna_v3.jsonl", "data/movies_dna_v3.pilot.jsonl"):
    for line in open(fp):
        r = json.loads(line)
        baseline[r["tmdb_id"]] = r["dna_v3"]

targets = [(245891, "John Wick"), (194, "Amélie"), (1813, "Devil's Advocate")]


def call(model, system, user):
    hdr = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"}
    # GPT-5.x and o-series use max_completion_tokens
    is_new = ("gpt-5" in model) or model.startswith("o3") or model.startswith("o4")
    token_field = "max_completion_tokens" if is_new else "max_tokens"
    body = {
        "model": model,
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
        token_field: 1500,
        "response_format": {"type":"json_object"},
    }
    if not is_new:
        body["temperature"] = 0.1
    t0 = time.time()
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=hdr, json=body, timeout=180)
    elapsed = time.time() - t0
    if r.status_code != 200:
        return None, elapsed, r.text[:300]
    j = r.json()
    return j["choices"][0]["message"]["content"], elapsed, j["usage"]


def overlap(a, b):
    if not a or not b: return 0.0
    keys = set(a.keys()) | set(b.keys())
    return sum(min(a.get(k,0), b.get(k,0)) for k in keys)


print(f"\n{'='*100}")
print(f"{'film':<22} {'model':<18} {'lat':>7} {'in_tok':>8} {'out_tok':>8} {'emo_ovl':>8} {'th_ovl':>8} top emotions")
print(f"{'-'*100}")

results = []
for tid, name in targets:
    film = by_id[tid]
    user = build_user_prompt(film)
    op_baseline = baseline.get(tid, {})
    for model in MODELS:
        try:
            text, elapsed, usage = call(model, system, user)
            if text is None:
                print(f"  {name:<20} {model:<18} ERROR: {usage}")
                continue
            raw = json.loads(text)
            dna = normalize_dna(raw, ont)
            eo = overlap(dna["emotion_sparse"], op_baseline.get("emotion_sparse", {}))
            to = overlap(dna["theme_sparse"], op_baseline.get("theme_sparse", {}))
            top_e = ",".join(sorted(dna["emotion_sparse"], key=lambda k: -dna["emotion_sparse"][k])[:3])
            print(f"  {name:<20} {model:<18} {elapsed:>5.1f}s {usage['prompt_tokens']:>8} {usage['completion_tokens']:>8} {eo:>8.2f} {to:>8.2f}  {top_e}")
            results.append({"film": name, "model": model, "lat": elapsed, "tokens_in": usage['prompt_tokens'],
                            "tokens_out": usage['completion_tokens'], "emo_ovl": eo, "th_ovl": to,
                            "dna": dna, "raw": raw})
        except Exception as e:
            print(f"  {name:<20} {model:<18} EXCEPTION: {type(e).__name__}: {e}")

# Aggregate per model with cost
print(f"\n{'='*120}")
print(f"AGGREGATE per model (3 pilot films) + projection for full extraction (3000 missing films):")
print(f"{'-'*120}")
print(f"  {'Model':<18} {'lat':>6} {'in':>5} {'out':>5} {'emo':>5} {'th':>5}  {'$/film':>9}  {'$/3000':>10}  {'$/7000':>10}")
for m in MODELS:
    sub = [r for r in results if r["model"] == m]
    if not sub: continue
    avg_lat = sum(r["lat"] for r in sub) / len(sub)
    avg_in = sum(r["tokens_in"] for r in sub) / len(sub)
    avg_out = sum(r["tokens_out"] for r in sub) / len(sub)
    avg_eo = sum(r["emo_ovl"] for r in sub) / len(sub)
    avg_to = sum(r["th_ovl"] for r in sub) / len(sub)
    p = PRICING.get(m, {"in": 0, "out": 0})
    cost_per_film = (avg_in * p["in"] + avg_out * p["out"]) / 1_000_000
    print(f"  {m:<18} {avg_lat:>4.1f}s {avg_in:>5.0f} {avg_out:>5.0f} {avg_eo:>5.2f} {avg_to:>5.2f}"
          f"  ${cost_per_film:>7.5f}  ${cost_per_film*3000:>8.2f}  ${cost_per_film*7369:>8.2f}")
