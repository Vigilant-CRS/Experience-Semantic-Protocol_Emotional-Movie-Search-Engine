"""Side-by-side DNA comparison across models for the 3 test films."""
import json, sys, os, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.extract_dna_v3 import build_system_prompt, build_user_prompt, load_ontology, normalize_dna, load_env
import requests

load_env()
ont = load_ontology()
system = build_system_prompt(ont)
movies = json.load(open("movies_export.json"))
by_id = {m["tmdb_id"]: m for m in movies}

baseline = {}
for fp in ("data/movies_dna_v3.jsonl", "data/movies_dna_v3.pilot.jsonl"):
    for line in open(fp):
        r = json.loads(line)
        baseline[r["tmdb_id"]] = r["dna_v3"]

MODELS = ["gpt-4.1-mini", "gpt-5.4-mini", "gpt-5.4-nano"]
TARGETS = [(245891, "John Wick"), (194, "Amélie"), (1813, "Devil's Advocate")]

def call(model, system, user):
    is_new = "gpt-5" in model
    body = {
        "model": model,
        "messages":[{"role":"system","content":system},{"role":"user","content":user}],
        ("max_completion_tokens" if is_new else "max_tokens"): 1500,
        "response_format":{"type":"json_object"},
    }
    if not is_new: body["temperature"] = 0.1
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type":"application/json"},
        json=body, timeout=180)
    return r.json()["choices"][0]["message"]["content"]

results = {}  # (tid, model) -> dna
for tid, name in TARGETS:
    user = build_user_prompt(by_id[tid])
    for m in MODELS:
        try:
            text = call(m, system, user)
            results[(tid,m)] = normalize_dna(json.loads(text), ont)
        except Exception as e:
            print(f"FAIL {name}/{m}: {e}", flush=True)
            results[(tid,m)] = {}

# Print side-by-side
def fmt(d, n=5):
    if not d: return "—"
    items = sorted(d.items(), key=lambda x:-x[1])[:n]
    return ", ".join(f"{k}({v:.2f})" for k,v in items)

for tid, name in TARGETS:
    print(f"\n{'='*100}")
    print(f"  {name} ({tid})")
    print('='*100)
    for field in ['emotion_sparse','theme_sparse','setting','mood','pacing']:
        print(f"\n  {field}:")
        for m in MODELS:
            d = results[(tid,m)].get(field, {})
            if isinstance(d, str): d = {d: 1.0}
            print(f"    {m:<18} {fmt(d, 6 if field in ('emotion_sparse','theme_sparse') else 3)}")
    for field in ['archetype','protagonist_gender']:
        print(f"\n  {field}:")
        for m in MODELS:
            print(f"    {m:<18} {results[(tid,m)].get(field)}")
