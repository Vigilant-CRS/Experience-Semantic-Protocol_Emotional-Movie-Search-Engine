"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Eval-Suite — 20 vorhersagbare Queries für die Demo-Qualität.

Jede Query hat erwartete Top-N Treffer (oder Eigenschaften). Skript ruft
die API auf, vergleicht, gibt Pass-Rate aus. Lauflänge ~2-3 min wegen
LLM-Calls (40-60 Calls total bei Tone-Shifts).

Usage:
  venv/bin/python3 scripts/eval_predictable.py
  venv/bin/python3 scripts/eval_predictable.py --verbose    # alle Top-5 zeigen
  venv/bin/python3 scripts/eval_predictable.py --query 7    # nur Test 7
"""
import argparse
import json
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests

API = "http://localhost:8000"


def matches(title: str, expected: List[str]) -> bool:
    """True if title contains any expected substring (case-insensitive)."""
    t = (title or "").lower()
    return any(e.lower() in t for e in expected)


EVAL = [
    # ── 1. Pure-Title Pins ───────────────────────────────────────────
    {"id": 1, "query": "Amélie",
     "expect_top1": ["amélie", "amelie"],
     "category": "pure-title"},
    {"id": 2, "query": "Fight Club",
     "expect_top1": ["fight club"],
     "category": "pure-title"},
    {"id": 3, "query": "Pulp Fiction",
     "expect_top1": ["pulp fiction"],
     "category": "pure-title"},

    # ── 2. Pure "wie X" (Top 1 = X, dann ähnliches) ──────────────────
    {"id": 4, "query": "Filme wie John Wick",
     "expect_top1": ["john wick"],
     "expect_in_top5": ["wick", "atomic blonde", "kate", "extraction",
                         "the equalizer", "hitman", "kill bill", "nobody",
                         "the mechanic"],
     "category": "wie-X"},
    {"id": 5, "query": "Filme wie Amélie",
     "expect_top1": ["amélie", "amelie"],
     "expect_in_top5": ["delicatessen", "moonrise", "garden state",
                         "her", "in der welt", "fantastic mr fox",
                         "wes anderson", "punch-drunk", "submarine"],
     "category": "wie-X"},

    # ── 3. Tone-Shift "wie X aber Y" (Variant Z mit Anchor) ──────────
    {"id": 6, "query": "Filme wie John Wick aber mit weiblicher Hauptrolle",
     "expect_in_top10": ["atomic blonde", "peppermint", "kate", "anna",
                          "the villainess", "ava", "hanna", "salt", "lucy",
                          "miss bala", "colombiana"],
     "expect_gender": "female",
     "category": "tone-shift gender-flip"},
    {"id": 7, "query": "Filme wie John Wick aber lustiger",
     "expect_in_top5_genres_contain": "Comedy",
     "expect_in_top10": ["keanu", "accidental spy", "nice guy", "spy",
                          "the man from u.n.c.l.e.", "kingsman",
                          "central intelligence", "tropic thunder",
                          "skiptrace", "shanghai noon"],
     "category": "tone-shift comedy"},
    {"id": 8, "query": "Filme wie Inception aber emotional",
     "expect_in_top10": ["eternal sunshine", "son's room", "tree of life",
                          "manchester", "solaris", "arrival", "interstellar",
                          "marriage story", "her"],
     "category": "tone-shift emotional"},
    {"id": 9, "query": "Filme wie Fight Club aber weniger nihilistisch",
     "expect_not_top1": ["fight club"],
     "expect_in_top10": ["american beauty", "donnie darko", "trainspotting",
                          "requiem for a dream", "ghost world", "groundhog",
                          "office space", "matrix"],
     "category": "tone-shift mood-shift"},

    # ── 4. Topic / Subject queries ───────────────────────────────────
    {"id": 10, "query": "Mafiafilme aus den 90ern",
     "expect_in_top10": ["goodfellas", "casino", "donnie brasco", "godfather",
                          "carlito", "bronx", "heat", "scarface", "boondock"],
     "expect_year_range": (1990, 1999),
     "category": "topic + year-filter"},
    {"id": 11, "query": "Vampirfilme",
     "expect_in_top10": ["dracula", "vampire", "nosferatu",
                          "interview", "blade", "twilight", "let the right",
                          "what we do in the shadows", "underworld",
                          "byzantium", "30 days", "lost boys"],
     "category": "topic"},
    {"id": 12, "query": "düstere Sci-Fi mit moralischem Dilemma",
     "expect_in_top10": ["blade runner", "ex machina", "gattaca", "minority report",
                          "her", "moon", "annihilation", "arrival", "children of men",
                          "the road", "snowpiercer"],
     "category": "mood + theme"},
    {"id": 13, "query": "Senior-Action wie Expendables",
     "expect_in_top10": ["expendables", "red", "mechanic", "killers",
                          "irishman", "old guard", "going in style", "last vegas",
                          "wild card"],
     "expect_age": "senior",
     "category": "age-filter + similar"},
    {"id": 14, "query": "Teenager als Hauptrolle in der Highschool",
     "expect_in_top10": ["mean girls", "spider-man", "homecoming", "easy a",
                          "10 things", "ferris bueller", "clueless",
                          "high school", "carrie", "to all the boys",
                          "21 jump", "sky high", "metal lords"],
     "expect_age": "teen",
     "category": "age-filter + setting"},

    # ── 5. Visual style (color_palette) ──────────────────────────────
    {"id": 15, "query": "Schwarz-Weiß Klassiker",
     "expect_in_top10": ["casablanca", "kane", "schindler", "manhattan",
                          "raging bull", "fantasia", "wages of fear",
                          "8½", "the seventh seal", "metropolis",
                          "third man", "12 angry men"],
     "category": "color-palette"},
    {"id": 16, "query": "neon-noir cyberpunk Filme",
     "expect_in_top10": ["blade runner", "ghost in the shell", "tron",
                          "altered carbon", "matrix", "akira", "drive",
                          "dark city", "johnny mnemonic", "ex machina"],
     "category": "color-palette + theme"},
    {"id": 17, "query": "warme Sonnenuntergangs-Dramen",
     "expect_color_palette_top5": "warm_palette",
     "category": "color-palette"},

    # ── 6. Avoid-Content ─────────────────────────────────────────────
    {"id": 18, "query": "Action ohne Schusswaffen",
     "expect_no_firearms_top10": True,
     "category": "avoid-content"},

    # ── 7. Feel-good / Comfort ───────────────────────────────────────
    {"id": 19, "query": "feel-good Sci-Fi",
     "expect_in_top10": ["wall-e", "martian", "back to the future", "e.t.",
                          "her", "guardians of the galaxy", "matrix",
                          "galaxy quest", "starman", "ghostbusters",
                          "groundhog day", "tomorrowland"],
     "category": "mood"},
    {"id": 20, "query": "romantische Komödie zum Einschlafen",
     "expect_in_top10": ["notting hill", "love actually", "you've got mail",
                          "while you were sleeping", "when harry met sally",
                          "sleepless in seattle", "pride and prejudice",
                          "bridget jones", "amelie", "amélie",
                          "about time", "begin again", "her"],
     "category": "mood + genre"},
]


def run_query(q: str, limit: int = 15) -> Optional[Dict[str, Any]]:
    try:
        r = requests.post(f"{API}/api/search",
                          json={"query": q, "limit": limit}, timeout=60)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        print(f"  ERR: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def score(case: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    results = data.get("results") or []
    titles = [r.get("title") or "" for r in results]
    out = {"id": case["id"], "query": case["query"], "category": case["category"],
           "passes": [], "fails": [], "top5": titles[:5]}

    if "expect_top1" in case:
        ok = bool(titles) and matches(titles[0], case["expect_top1"])
        (out["passes"] if ok else out["fails"]).append(
            f"top1 in {case['expect_top1']} → got {titles[0] if titles else '∅'}")

    if "expect_in_top5" in case:
        ok = any(matches(t, case["expect_in_top5"]) for t in titles[:5])
        (out["passes"] if ok else out["fails"]).append(
            f"any of {case['expect_in_top5'][:3]}… in top5 → "
            f"{'hit' if ok else 'miss'}")

    if "expect_in_top10" in case:
        ok = any(matches(t, case["expect_in_top10"]) for t in titles[:10])
        (out["passes"] if ok else out["fails"]).append(
            f"any of {case['expect_in_top10'][:3]}… in top10 → "
            f"{'hit' if ok else 'miss'}")

    if "expect_not_top1" in case:
        ok = not (titles and matches(titles[0], case["expect_not_top1"]))
        (out["passes"] if ok else out["fails"]).append(
            f"top1 NOT in {case['expect_not_top1']} → got {titles[0] if titles else '∅'}")

    if "expect_gender" in case:
        genders = [r.get("protagonist_gender") for r in results[:10]]
        match = sum(1 for g in genders if g == case["expect_gender"])
        ok = match >= 3
        (out["passes"] if ok else out["fails"]).append(
            f"≥3 of top10 protagonist_gender={case['expect_gender']} → {match}/10")

    if "expect_age" in case:
        ages = [r.get("protagonist_age") for r in results[:10]]
        match = sum(1 for a in ages if a == case["expect_age"])
        ok = match >= 4
        (out["passes"] if ok else out["fails"]).append(
            f"≥4 of top10 protagonist_age={case['expect_age']} → {match}/10")

    if "expect_year_range" in case:
        lo, hi = case["expect_year_range"]
        years = [r.get("year") for r in results[:10] if r.get("year")]
        match = sum(1 for y in years if lo <= y <= hi)
        ok = match >= 5
        (out["passes"] if ok else out["fails"]).append(
            f"≥5 of top10 year in [{lo},{hi}] → {match}/{len(years)}")

    if "expect_in_top5_genres_contain" in case:
        wanted = case["expect_in_top5_genres_contain"]
        match = sum(1 for r in results[:5]
                    if wanted in (r.get("genres") or []))
        ok = match >= 2
        (out["passes"] if ok else out["fails"]).append(
            f"≥2 of top5 genres contain {wanted!r} → {match}/5")

    if "expect_color_palette_top5" in case:
        wanted = case["expect_color_palette_top5"]
        match = sum(1 for r in results[:5]
                    if (r.get("color_palette") or {}).get(wanted, 0) > 0.2)
        ok = match >= 2
        (out["passes"] if ok else out["fails"]).append(
            f"≥2 of top5 color_palette has {wanted!r} > 0.2 → {match}/5")

    if "expect_no_firearms_top10" in case:
        # Heuristic: result film's content_features.firearms should be small
        # or missing. We can only check the film payload — query for /api/film.
        nofire = 0
        for r in results[:10]:
            cf = r.get("content_features") or {}
            if isinstance(cf, dict) and cf.get("firearms", 0) <= 0.05:
                nofire += 1
        ok = nofire >= 7
        (out["passes"] if ok else out["fails"]).append(
            f"≥7 of top10 have firearms ≤ 0.05 → {nofire}/10")

    out["pass"] = (len(out["fails"]) == 0) and (len(out["passes"]) > 0)
    out["partial"] = (len(out["passes"]) > 0) and (len(out["fails"]) > 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--query", type=int, default=None, help="run only test with this id")
    args = ap.parse_args()

    cases = EVAL if args.query is None else [c for c in EVAL if c["id"] == args.query]

    print(f"Running {len(cases)} eval queries against {API}…\n")
    t0 = time.time()
    full_pass, partial, fail = 0, 0, 0
    rows = []
    for c in cases:
        data = run_query(c["query"])
        if not data:
            fail += 1
            rows.append({"id": c["id"], "query": c["query"], "pass": False,
                         "partial": False, "fails": ["API call failed"], "passes": [],
                         "top5": [], "category": c["category"]})
            continue
        row = score(c, data)
        rows.append(row)
        if row["pass"]:
            full_pass += 1
        elif row["partial"]:
            partial += 1
        else:
            fail += 1
        mark = "✅" if row["pass"] else ("🟡" if row["partial"] else "❌")
        print(f"{mark} #{c['id']:>2}  [{c['category']:<24s}]  {c['query'][:60]}")
        for p in row["passes"]: print(f"     · ✓ {p}")
        for f_ in row["fails"]: print(f"     · ✗ {f_}")
        if args.verbose or not row["pass"]:
            for i, t in enumerate(row["top5"], 1):
                print(f"        {i}. {t}")

    elapsed = time.time() - t0
    print()
    print("─" * 60)
    print(f"  PASS:    {full_pass:>2} / {len(cases)}")
    print(f"  PARTIAL: {partial:>2} / {len(cases)}")
    print(f"  FAIL:    {fail:>2} / {len(cases)}")
    print(f"  Elapsed: {elapsed:.0f}s")
    print("─" * 60)


if __name__ == "__main__":
    main()
