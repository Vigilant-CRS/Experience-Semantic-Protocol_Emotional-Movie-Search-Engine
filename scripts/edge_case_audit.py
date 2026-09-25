"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).

Edge-Case-Audit: systematische Sweeps für potenzielle Failure-Modi.
Findet keine 100% korrekte Wahrheit aber zeigt Bruchstellen schnell auf.
"""
import requests
import time

API = "http://localhost:8000"


def search(body, timeout=30):
    try:
        r = requests.post(f"{API}/api/search", json=body, timeout=timeout)
        return r.status_code, r.json() if r.status_code == 200 else None
    except Exception as e:
        return -1, {"error": str(e)}


def describe(d, n=3):
    if not d or "results" not in d:
        return "  (no response)"
    intent = d.get("intent") or {}
    lines = [f"  intent.similar_to: {intent.get('similar_to_title')!r}"]
    lines.append(f"  intent.gender: {intent.get('protagonist_gender')}  "
                 f"age: {intent.get('protagonist_age')}  "
                 f"year: [{intent.get('year_min')}, {intent.get('year_max')}]")
    for r in d["results"][:n]:
        g = ",".join(r.get("genres", [])[:2])
        lines.append(f"    {r['title']} ({r['year']}) — {g}")
    return "\n".join(lines)


CASES = [
    # ─ Title-Resolution Edge-Cases ────────────────────────────────────────
    {"id": "T1", "name": "Short title with stopwords",
     "query": "Her",
     "expect": "Spike Jonze 'Her' (2013) should be #1 (short-title bypass)"},
    {"id": "T2", "name": "Single-letter / number title",
     "query": "9",
     "expect": "Some kind of resolution — '9' (2009) or just topic"},
    {"id": "T3", "name": "Title with colon vs dash (Peppermint variant)",
     "query": "Mission: Impossible - Fallout",
     "expect": "Should match the M:I film, not fuzzy on something else"},
    {"id": "T4", "name": "German release title",
     "query": "Stirb langsam",
     "expect": "Should resolve to Die Hard (English title in our index)"},
    {"id": "T5", "name": "Title with apostrophe",
     "query": "Schindler's List",
     "expect": "Should pin Schindler's List #1"},
    {"id": "T6", "name": "Very generic short title that IS a film",
     "query": "It",
     "expect": "Either pin 'It' or treat as too short to be useful"},
    {"id": "T7", "name": "Sequel disambiguation",
     "query": "John Wick: Chapter 4",
     "expect": "Should NOT collapse to John Wick (orig); JW:C4 #1"},
    {"id": "T8", "name": "Two films with similar title (reboot)",
     "query": "The Mummy",
     "expect": "Resolves to ONE of them deterministically"},
    {"id": "T9", "name": "Title that contains generic words",
     "query": "Action Jackson",
     "expect": "Pin Action Jackson, don't switch to Topic 'Action'"},
    {"id": "T10", "name": "Word from a stopword title bypass abuse",
     "query": "The The The",
     "expect": "No false match — degenerate query"},

    # ─ LLM-Intent Edge-Cases ──────────────────────────────────────────────
    {"id": "L1", "name": "Negation: 'nicht zu düster'",
     "query": "Sci-Fi nicht zu düster",
     "expect": "Should NOT set similar_to; should use avoid_emotions or skew lighter"},
    {"id": "L2", "name": "Question form",
     "query": "Welche Mafiafilme aus den 90ern?",
     "expect": "Should treat as topic, year filter [1990,1999]"},
    {"id": "L3", "name": "Multi-language query",
     "query": "Filme mit feel-good factor",
     "expect": "Topic query, mood=comforting/joy"},
    {"id": "L4", "name": "Comparative without reference",
     "query": "Etwas Spannenderes als gestern",
     "expect": "No reference, topic=thriller/anticipation"},
    {"id": "L5", "name": "Ambivalent / contradictory",
     "query": "traurig aber tröstlich",
     "expect": "emotion has sadness + comforting (wirkung)"},
    {"id": "L6", "name": "Very long query",
     "query": "Ich suche etwas für einen Freitag-Abend wenn ich müde bin und eigentlich nichts denken will aber auch nicht ganz dumm sein soll, vielleicht etwas das mich emotional berührt aber nicht weinen macht und mit einer starken weiblichen Hauptfigur",
     "expect": "Should not crash; gender=female, mood=light/intelligent"},
    {"id": "L7", "name": "Single emoji query",
     "query": "🎬",
     "expect": "No crash; either empty results or topic-fallback"},
    {"id": "L8", "name": "Specific year",
     "query": "Filme aus dem Jahr 1999",
     "expect": "year_min=year_max=1999"},
    {"id": "L9", "name": "Decade specific topic without era",
     "query": "Tarantino Filme",
     "expect": "Pulp Fiction, Kill Bill etc. — director-name handling?"},
    {"id": "L10", "name": "Avoid-content phrasing",
     "query": "Action für die ganze Familie ohne Gewalt",
     "expect": "avoid_content has graphic_violence + maybe firearms"},

    # ─ Filter / Engine Edge-Cases ─────────────────────────────────────────
    {"id": "E1", "name": "similar_to=invalid_id",
     "body": {"similar_to": 99999999, "limit": 5},
     "expect": "Graceful 404 or empty results, no crash"},
    {"id": "E2", "name": "All sliders zero",
     "body": {"query": "Action", "w_synopsis": 0, "w_emotion": 0,
              "w_theme": 0, "limit": 5},
     "expect": "Doesn't crash; perhaps returns empty"},
    {"id": "E3", "name": "Conflicting gender filter",
     "body": {"query": "Filme wie John Wick", "gender": "female", "limit": 5},
     "expect": "John Wick pinned (gender filter conflicts with ref) — what happens?"},
    {"id": "E4", "name": "Year filter excludes reference",
     "body": {"query": "Filme wie Casablanca", "year_min": 2020, "limit": 5},
     "expect": "Casablanca (1942) excluded by year filter — bug or correct?"},
    {"id": "E5", "name": "Empty query + empty similar_to",
     "body": {"limit": 5},
     "expect": "400 Bad Request"},
    {"id": "E6", "name": "Avoid an emotion AND select it via wheel",
     "body": {"query": "Action",
              "adjusted_emotions": {"rage": 0.5},
              "avoid_emotions": ["rage"],
              "limit": 5},
     "expect": "Conflicting wish; pick one or warn"},
    {"id": "E7", "name": "Runtime filter impossible",
     "body": {"query": "Drama", "runtime_min": 99999, "limit": 5},
     "expect": "Empty results, no crash"},
    {"id": "E8", "name": "Streaming filter unknown provider",
     "body": {"query": "Action",
              "streaming_providers": ["Nonexistent+ Channel"],
              "limit": 5},
     "expect": "Empty results, no crash"},
]


def main():
    print(f"Running {len(CASES)} edge-case probes against {API}\n")
    t0 = time.time()
    bad, good, slow = [], [], []
    for c in CASES:
        body = c.get("body") or {"query": c["query"], "limit": 5}
        if "limit" not in body:
            body["limit"] = 5
        t_start = time.perf_counter()
        status, data = search(body)
        elapsed = (time.perf_counter() - t_start) * 1000
        if elapsed > 8000:
            slow.append(c["id"])
        category = "❌" if status < 200 or status >= 500 else ("🟡" if status >= 400 else "✅")
        print(f"{category} {c['id']:>3}  [{elapsed:>5.0f}ms] {c['name']}: "
              f"q={c.get('query', body)!r}")
        print(f"     expect: {c['expect']}")
        if status == 200:
            print(describe(data))
            good.append(c["id"])
        elif status == 400:
            print(f"  → 400 OK (expected): {(data or {}).get('detail', '')}")
            good.append(c["id"])
        else:
            print(f"  → status={status} body={data}")
            bad.append(c["id"])
        print()
    print("─" * 60)
    print(f"  OK:     {len(good):>2} / {len(CASES)}")
    print(f"  ERROR:  {len(bad):>2} / {len(CASES)}  {bad if bad else ''}")
    print(f"  SLOW:   {len(slow):>2} / {len(CASES)}  {slow if slow else ''}")
    print(f"  Total:  {(time.time()-t0):.0f}s")


if __name__ == "__main__":
    main()
