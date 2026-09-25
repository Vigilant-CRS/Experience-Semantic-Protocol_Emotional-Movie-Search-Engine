"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).

100-Case Demo-Eval — 8 Kategorien, 29 Treffer pro Query, Auto-Analyse.

Usage:
  venv/bin/python3 scripts/eval_100.py
  venv/bin/python3 scripts/eval_100.py --category=tone_shift  # only one cat
  venv/bin/python3 scripts/eval_100.py --replay              # only re-analyze existing JSONL
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "http://localhost:8000"
LIMIT = 29
OUT = ROOT / "data" / "eval_100.jsonl"

CASES: List[Dict[str, Any]] = [
    # ── 1. "wie X" Pure Reference (15) ─────────────────────────────────────
    {"cat": "wie_x", "q": "Filme wie Amélie"},
    {"cat": "wie_x", "q": "Filme wie John Wick"},
    {"cat": "wie_x", "q": "Filme wie Inception"},
    {"cat": "wie_x", "q": "Filme wie Fight Club"},
    {"cat": "wie_x", "q": "Filme wie Pulp Fiction"},
    {"cat": "wie_x", "q": "Filme wie Gladiator"},
    {"cat": "wie_x", "q": "Filme wie Forrest Gump"},
    {"cat": "wie_x", "q": "Filme wie The Matrix"},
    {"cat": "wie_x", "q": "Filme wie Casablanca"},
    {"cat": "wie_x", "q": "Filme wie Schindler's List"},
    {"cat": "wie_x", "q": "Filme wie Goodfellas"},
    {"cat": "wie_x", "q": "Filme wie Titanic"},
    {"cat": "wie_x", "q": "Filme wie Heat"},
    {"cat": "wie_x", "q": "Filme wie The Shawshank Redemption"},
    {"cat": "wie_x", "q": "Filme wie The Lion King"},

    # ── 2. "wie X aber Y" Tone-Shift (15) ──────────────────────────────────
    {"cat": "tone_shift", "q": "Filme wie John Wick aber lustiger"},
    {"cat": "tone_shift", "q": "Filme wie John Wick aber mit weiblicher Hauptrolle"},
    {"cat": "tone_shift", "q": "Filme wie Amélie aber dunkler"},
    {"cat": "tone_shift", "q": "Filme wie Inception aber emotional"},
    {"cat": "tone_shift", "q": "Filme wie The Matrix aber romantisch"},
    {"cat": "tone_shift", "q": "Filme wie Casablanca aber moderner"},
    {"cat": "tone_shift", "q": "Filme wie Fight Club aber weniger nihilistisch"},
    {"cat": "tone_shift", "q": "Filme wie Heat aber kürzer"},
    {"cat": "tone_shift", "q": "Filme wie Forrest Gump aber dunkler"},
    {"cat": "tone_shift", "q": "Filme wie The Godfather aber komödiantisch"},
    {"cat": "tone_shift", "q": "Filme wie Titanic aber mit happy ending"},
    {"cat": "tone_shift", "q": "Filme wie Pulp Fiction aber linear erzählt"},
    {"cat": "tone_shift", "q": "Filme wie Star Wars aber realistisch"},
    {"cat": "tone_shift", "q": "Filme wie The Shining aber subtiler"},
    {"cat": "tone_shift", "q": "Filme wie Pretty Woman aber feminism-aware"},

    # ── 3. "Filme zum X" Purpose/Mood (15) ─────────────────────────────────
    {"cat": "zum_x", "q": "Filme zum Business und Startup motivieren"},
    {"cat": "zum_x", "q": "Filme zum Einschlafen"},
    {"cat": "zum_x", "q": "Filme zum Weinen"},
    {"cat": "zum_x", "q": "Filme zum Lachen"},
    {"cat": "zum_x", "q": "Filme zum Mitfiebern"},
    {"cat": "zum_x", "q": "Filme zum Abschalten nach harter Arbeitswoche"},
    {"cat": "zum_x", "q": "Filme zum Träumen"},
    {"cat": "zum_x", "q": "Filme zum Lernen über andere Kulturen"},
    {"cat": "zum_x", "q": "Filme zum Nachdenken über das Leben"},
    {"cat": "zum_x", "q": "Filme für Date-Night zu zweit"},
    {"cat": "zum_x", "q": "Filme zum Freitag-Abend mit Pizza"},
    {"cat": "zum_x", "q": "Filme zum Mut machen vor schwierigen Entscheidungen"},
    {"cat": "zum_x", "q": "Filme zum Mitgrooven mit Musik im Mittelpunkt"},
    {"cat": "zum_x", "q": "Filme zum Gruseln aber nicht zu brutal"},
    {"cat": "zum_x", "q": "Filme zum Verlieben"},

    # ── 4. Emotion-driven (10) ──────────────────────────────────────────────
    {"cat": "emotion", "q": "melancholische Filme die nicht depressiv machen"},
    {"cat": "emotion", "q": "cathartische Action mit Rachemotiv"},
    {"cat": "emotion", "q": "hoffnungsvolle Sci-Fi"},
    {"cat": "emotion", "q": "bedrückende Drama-Kriegsfilme"},
    {"cat": "emotion", "q": "euphorische feel-good Komödien"},
    {"cat": "emotion", "q": "bittersüße Coming-of-Age"},
    {"cat": "emotion", "q": "dunkle Thriller mit moralischem Dilemma"},
    {"cat": "emotion", "q": "inspirierende Biopics über Visionäre"},
    {"cat": "emotion", "q": "haunting Mystery-Filme mit unerklärlichem Ende"},
    {"cat": "emotion", "q": "überwältigende Epen mit großen Schlachten"},

    # ── 5. Theme/Subject-driven (10) ───────────────────────────────────────
    {"cat": "theme", "q": "Mafiafilme mit weiblicher Hauptrolle"},
    {"cat": "theme", "q": "Vampirfilme die nicht romantisch sind"},
    {"cat": "theme", "q": "Spionagefilme im Kalten Krieg"},
    {"cat": "theme", "q": "Heist-Movies mit Twist am Ende"},
    {"cat": "theme", "q": "Coming-of-age in den 80ern"},
    {"cat": "theme", "q": "Dystopische Sci-Fi mit politischer Botschaft"},
    {"cat": "theme", "q": "Sportfilme über Außenseiter die gewinnen"},
    {"cat": "theme", "q": "Krimi mit weiblicher Detektivin"},
    {"cat": "theme", "q": "Western mit anti-heroischem Protagonisten"},
    {"cat": "theme", "q": "Filme über kreative Krisen von Künstlern"},

    # ── 6. Era/Year-Filter (10) ─────────────────────────────────────────────
    {"cat": "era", "q": "90er Action-Klassiker"},
    {"cat": "era", "q": "Filme aus den 70ern mit politischer Botschaft"},
    {"cat": "era", "q": "2020er Sci-Fi"},
    {"cat": "era", "q": "Mafiafilme der 80er"},
    {"cat": "era", "q": "Komödien der 2000er"},
    {"cat": "era", "q": "Klassiker vor 1980"},
    {"cat": "era", "q": "60er Romantik mit Pariser Setting"},
    {"cat": "era", "q": "Drama ab 2020"},
    {"cat": "era", "q": "80er Sci-Fi"},
    {"cat": "era", "q": "2010er Superhelden-Film aber nicht Marvel"},

    # ── 7. Avoid/Filter (10) ────────────────────────────────────────────────
    {"cat": "avoid", "q": "Action ohne Schusswaffen"},
    {"cat": "avoid", "q": "Sci-Fi ohne Aliens"},
    {"cat": "avoid", "q": "Drama ohne Tod oder schwere Krankheit"},
    {"cat": "avoid", "q": "Romantik ohne Kitsch"},
    {"cat": "avoid", "q": "Horror ohne Jump-Scares"},
    {"cat": "avoid", "q": "Familienfilm ohne Gewalt"},
    {"cat": "avoid", "q": "Krimi ohne Mord"},
    {"cat": "avoid", "q": "Thriller nicht zu blutig"},
    {"cat": "avoid", "q": "Komödie ohne Slapstick"},
    {"cat": "avoid", "q": "Kriegsfilm aus weiblicher Perspektive"},

    # ── 8. Specific Mood Combinations (15) ─────────────────────────────────
    {"cat": "combined", "q": "Filme die mich zum Business und Startup motivieren wie Social Network"},
    {"cat": "combined", "q": "Filme zum Reflektieren über Beziehungen"},
    {"cat": "combined", "q": "Filme mit starker weiblicher Hauptrolle die nicht aufgibt"},
    {"cat": "combined", "q": "Filme über Underdog die sich gegen die Welt durchbeißen"},
    {"cat": "combined", "q": "Filme über Genies die scheitern und sich neu erfinden"},
    {"cat": "combined", "q": "Filme über Verlust und Trauerbewältigung mit Hoffnung am Ende"},
    {"cat": "combined", "q": "Filme über Selbstfindung im Ausland"},
    {"cat": "combined", "q": "Filme über zweite Chancen nach Lebenskrise"},
    {"cat": "combined", "q": "Filme über Freundschaft die alles übersteht"},
    {"cat": "combined", "q": "Filme über Erwachsenwerden in schwierigen Zeiten"},
    {"cat": "combined", "q": "Filme über Künstler die alles riskieren für ihre Vision"},
    {"cat": "combined", "q": "Filme über Wissenschaftler die etwas Bahnbrechendes entdecken"},
    {"cat": "combined", "q": "Filme über Whistleblower und David-gegen-Goliath-Kämpfe"},
    {"cat": "combined", "q": "Filme über Liebe in dunklen Zeiten von Krieg oder Krankheit"},
    {"cat": "combined", "q": "Filme über Familienzusammenhalt nach einer großen Krise"},
]


def call(q: str):
    try:
        r = requests.post(f"{API}/api/search",
                          json={"query": q, "limit": LIMIT},
                          timeout=60)
        if r.status_code != 200:
            return {"_error": f"HTTP {r.status_code}"}
        return r.json()
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def short(rec):
    """Compact one-line summary of one test case."""
    if rec.get("_error"):
        return f"  ERROR: {rec['_error']}"
    i = rec.get("intent") or {}
    r = rec.get("results") or []
    titles = [x.get("title", "?") for x in r[:5]]
    ref = i.get("similar_to_title")
    flags = []
    if ref: flags.append(f"ref={ref}")
    if i.get("protagonist_gender"): flags.append(f"gender={i['protagonist_gender']}")
    if i.get("protagonist_age"): flags.append(f"age={i['protagonist_age']}")
    if i.get("year_min") is not None or i.get("year_max") is not None:
        flags.append(f"year=[{i.get('year_min')},{i.get('year_max')}]")
    if i.get("avoid_content"): flags.append(f"avoid_c={i['avoid_content']}")
    suffix = f" [{', '.join(flags)}]" if flags else ""
    return f"  {' · '.join(titles)}{suffix}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default=None)
    ap.add_argument("--replay", action="store_true",
                    help="Don't run, just re-analyze existing JSONL")
    args = ap.parse_args()

    cases = CASES if not args.category else [c for c in CASES if c["cat"] == args.category]
    print(f"Running {len(cases)} cases against {API} (limit={LIMIT})\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not args.replay:
        with open(OUT, "w") as f:
            t_total = time.time()
            for i, c in enumerate(cases, 1):
                t0 = time.perf_counter()
                rec = call(c["q"])
                rec["_cat"] = c["cat"]
                rec["_q"] = c["q"]
                rec["_elapsed_ms"] = (time.perf_counter() - t0) * 1000
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"[{i:>3}/{len(cases)}]  [{c['cat']}]  {c['q'][:60]}")
                print(short(rec))
            print(f"\nDone. Total {time.time()-t_total:.0f}s. Output → {OUT}")

    # Per-category counts (just sanity)
    print("\n─── Per-Category Statistics ───")
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    with open(OUT) as f:
        for line in f:
            rec = json.loads(line)
            by_cat.setdefault(rec["_cat"], []).append(rec)
    for cat, recs in by_cat.items():
        errs = sum(1 for r in recs if r.get("_error"))
        with_ref = sum(1 for r in recs if (r.get("intent") or {}).get("similar_to_title"))
        avg_ms = sum(r.get("_elapsed_ms", 0) for r in recs) / max(len(recs), 1)
        print(f"  {cat:<12}  n={len(recs):>2}  errors={errs}  with_ref={with_ref}  "
              f"avg={avg_ms:.0f}ms")


if __name__ == "__main__":
    main()
