"""
⚠️  DEPRECATED — kept for reference only.

This file is the *original* expanded eval set (41 test cases in 6 categories).
It is NOT executed by any CI/automation. The active eval suite is
`scripts/eval_v3.py` (29 tests, mostly disjoint).

Audit 2026-05-12 (F-008): this file contains test-case ideas that are NOT in
the active suite — particularly category-organized tests and property-tests
(see DISPUTED_POINTS DP-006). When the active suite is refactored toward
property-based testing, these 41 cases are the source pool.

DO NOT extend this file. Add new tests to `eval_v3.py` instead.

Original docstring:
  Expanded Quality-Eval-Suite for MindRead V3 — 50+ test cases organized by
  category: Reference-based, Genre/Mood, Activity-context, Modifier-queries,
  Avoid-filters, Edge-cases, Semantic checks, Latency budget.
"""
import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional
import requests


# ─── TEST CATEGORIES ─────────────────────────────────────────────────────

REFERENCE_TESTS = [
    {"id":"ref_john_wick", "kind":"similar_to", "input":{"similar_to":245891},
     "must_contain_any_of":["John Wick: Chapter 2","John Wick: Kapitel 4","Furious 7","Desperado","Rage","Django Unchained","A Man Apart","Crank","Machete","Harry Brown","Out for Justice","I Am Wrath","Bullet to the Head","The Punisher"],
     "min_hits":3, "must_not_match":["Featurette","Behind","Wick Is Pain"]},
    {"id":"ref_amelie", "kind":"similar_to", "input":{"similar_to":194},
     "must_contain_any_of":["Angel-A","Mulholland Drive","Bridget Jones","Emma","Alice in Wonderland","Lost in Translation","Punch-Drunk Love","Eternal Sunshine of the Spotless Mind","Chouchou","Miracle on 34th Street","The Science of Sleep"],
     "min_hits":2},
    {"id":"ref_devils_advocate", "kind":"similar_to", "input":{"similar_to":1813},
     "must_contain_any_of":["Needful Things","Under Suspicion","Lolita","The Fan","Thinner","...And Justice for All","A Time to Kill","Primal Fear","Angel Heart","Constantine"],
     "min_hits":2},
    {"id":"ref_amelie_via_text", "kind":"freetext", "input":{"query":"Filme wie Amélie"},
     "expected_reference_title_substring":"Amélie", "min_hits":0},
    {"id":"ref_shawshank_via_german", "kind":"freetext", "input":{"query":"Filme wie Die Verurteilten"},
     "expected_reference_title_substring":"Shawshank", "min_hits":0},
]

GENRE_MOOD_TESTS = [
    {"id":"mood_dark_thriller", "kind":"freetext", "input":{"query":"düsterer Thriller mit Wendungen"},
     "intent_should_contain_emotion_any_of":["unsettling","dread","haunting"],
     "intent_should_contain_theme_any_of":["Thriller","mystery_investigation","conspiracy"], "min_hits":0},
    {"id":"mood_uplifting", "kind":"freetext", "input":{"query":"feel-good Filme zum Aufmuntern"},
     "intent_should_contain_emotion_any_of":["joy","comforting","inspiring","warmth"],
     "must_contain_any_of":["Babe","The Princess and the Frog","Beethoven","Marmaduke","About Time","Forrest Gump","Big Fish"],
     "min_hits":1},
    {"id":"mood_atmospheric_slow", "kind":"freetext", "input":{"query":"atmosphärischer langsamer Film"},
     "intent_should_contain_theme_any_of":["atmospheric","slow_burn","contemplative","minimalist"], "min_hits":0},
    {"id":"genre_western", "kind":"freetext", "input":{"query":"klassischer Western mit Antiheld"},
     "intent_should_contain_theme_any_of":["Western"],
     "must_contain_any_of":["The Magnificent Seven","Open Range","Django Unchained","Once Upon a Time","Unforgiven","The Quick and the Dead","3:10 to Yuma"], "min_hits":1},
    {"id":"genre_noir", "kind":"freetext", "input":{"query":"film noir Krimi schwarz-weiß Stimmung"},
     "intent_should_contain_theme_any_of":["noir","mystery_investigation","dark"], "min_hits":0},
    {"id":"genre_pure_comedy", "kind":"freetext", "input":{"query":"einfach lachen Komödie"},
     "intent_should_contain_theme_any_of":["Comedy"],
     "must_contain_any_of":["Anchorman","Step Brothers","Grown Ups","Old School","Tropic Thunder","Dumb and Dumber","Hot Fuzz"], "min_hits":1},
    {"id":"genre_horror_psyche", "kind":"freetext", "input":{"query":"psychologischer Horror"},
     "intent_should_contain_emotion_any_of":["dread","unsettling","fear"],
     "must_contain_any_of":["Repulsion","The Brood","Inside","The Conjuring","Insidious","The Babadook","It Follows","The Witch","Hereditary"], "min_hits":2},
    {"id":"genre_cyberpunk", "kind":"freetext", "input":{"query":"cyberpunk action filme"},
     "intent_should_contain_theme_any_of":["Science Fiction","Action"],
     "must_contain_any_of":["Ghost in the Shell","Alita: Battle Angel","RoboCop","Cyborg","Blade Runner","Total Recall","The Matrix","Lucy","Pixels","District B13","Tron","Equilibrium"], "min_hits":1},
    {"id":"genre_period_war", "kind":"freetext", "input":{"query":"Kriegsfilm Zweiter Weltkrieg dramatisch"},
     "intent_should_contain_theme_any_of":["War","war_and_peace","Drama"], "min_hits":0},
]

ACTIVITY_TESTS = [
    {"id":"act_einschlafen", "kind":"freetext", "input":{"query":"Filme zum Einschlafen, gemütlich, ruhig"},
     "intent_should_contain_emotion_any_of":["comforting","contentment","warmth"],
     "must_contain_any_of":["Babe","Beethoven","The Princess and the Frog","Marmaduke","Cheaper by the Dozen","Nicholas on Holiday","Mary Poppins","The Aristocats"], "min_hits":1},
    {"id":"act_family_evening", "kind":"freetext", "input":{"query":"Familienabend kindgeeignet"},
     "intent_should_contain_emotion_any_of":["comforting","joy","warmth"],
     "must_contain_any_of":["Babe","The Aristocats","Mary Poppins","Marmaduke","Beethoven","The Princess and the Frog","Mr. Popper's Penguins","Cheaper by the Dozen","Paddington","Elemental"], "min_hits":2},
    {"id":"act_date_night", "kind":"freetext", "input":{"query":"romantischer Date-Night-Film, nicht zu kitschig"},
     "intent_should_contain_emotion_any_of":["love","tenderness","warmth"],
     "intent_should_contain_theme_any_of":["Romance","romance"], "min_hits":0},
    {"id":"act_workout", "kind":"freetext", "input":{"query":"Action-Film zum Sport machen, energiegeladen"},
     "intent_should_contain_emotion_any_of":["thrill","excitement","cathartic"], "min_hits":0},
    {"id":"act_thinking_movie", "kind":"freetext", "input":{"query":"Film der zum Nachdenken anregt"},
     "intent_should_contain_theme_any_of":["contemplative","moral_dilemma","faith_vs_doubt","philosophy"], "min_hits":0},
    {"id":"act_dinner_party", "kind":"freetext", "input":{"query":"unterhaltsamer Film für Abend mit Freunden"},
     "intent_should_contain_emotion_any_of":["joy","comforting","excitement"], "min_hits":0},
    {"id":"act_sad_mood", "kind":"freetext", "input":{"query":"emotionaler Film zum Heulen"},
     "intent_should_contain_emotion_any_of":["grief","sadness","melancholy","bittersweet"],
     "must_contain_any_of":["Reign Over Me","Remember Me","Three Colors: Blue","Restless","Collateral Beauty","Marley & Me","The Notebook","Atonement","Manchester by the Sea"], "min_hits":1},
]

MODIFIER_TESTS = [
    {"id":"mod_jw_funnier", "kind":"freetext", "input":{"query":"Filme wie John Wick aber lustiger"},
     "intent_should_contain_emotion_any_of":["joy","cathartic","excitement"],
     "intent_should_contain_theme_any_of":["Action","Comedy"], "min_hits":0},
    {"id":"mod_inception_newer", "kind":"freetext", "input":{"query":"Filme wie Inception aber aktueller"},
     "intent_should_contain_theme_any_of":["artificial_reality","Science Fiction"], "min_hits":0},
    {"id":"mod_dark_knight_lighter", "kind":"freetext", "input":{"query":"Filme wie The Dark Knight aber leichter"},
     "intent_should_contain_emotion_any_of":["excitement","comforting"], "min_hits":0},
    {"id":"mod_devils_advocate_action", "kind":"freetext", "input":{"query":"Filme wie Im Auftrag des Teufels aber mit mehr action"},
     "expected_reference_title_substring":"Devil",
     "intent_should_contain_theme_any_of":["Action","Thriller"], "min_hits":0},
    {"id":"mod_amelie_darker", "kind":"freetext", "input":{"query":"Filme wie Amélie aber düsterer"},
     "expected_reference_title_substring":"Amélie", "min_hits":0},
]

AVOID_TESTS = [
    {"id":"avoid_strict_rage", "kind":"similar_to", "input":{"similar_to":245891,"avoid_emotions":["rage"],"avoid_strict":True},
     "min_hits":0, "assert_no_film_has_emotion_above":("rage",0.10)},
    {"id":"avoid_horror_in_query", "kind":"freetext", "input":{"query":"Action ohne Horror ohne Splatter"},
     "intent_should_have_avoid":True, "min_hits":0},
    {"id":"avoid_strict_horror", "kind":"freetext", "input":{"query":"spannender Action-Film","avoid_themes":["Horror"],"avoid_strict":True},
     "min_hits":0},
    {"id":"avoid_grief_strict", "kind":"freetext", "input":{"query":"Filme zum Wohlfühlen","avoid_emotions":["grief","despair"],"avoid_strict":True},
     "min_hits":0, "assert_no_film_has_emotion_above":("grief",0.15)},
]

GENRE_FILTER_TESTS = [
    {"id":"filter_drama_only", "kind":"freetext", "input":{"query":"emotionaler Film","genre":["Drama"]},
     "min_hits":0, "assert_all_have_genre":"Drama"},
    {"id":"filter_action_thriller", "kind":"freetext", "input":{"query":"spannend","genre":["Action","Thriller"]},
     "min_hits":0, "assert_all_have_any_genre":["Action","Thriller"]},
]

YEAR_RUNTIME_TESTS = [
    {"id":"year_recent_only", "kind":"freetext", "input":{"query":"sci-fi","year_min":2015},
     "min_hits":0, "assert_all_year_at_least":2015},
    {"id":"runtime_short", "kind":"freetext", "input":{"query":"Komödie","runtime_max":100},
     "min_hits":0, "assert_all_runtime_at_most":100},
]

PROVIDER_TESTS = [
    {"id":"provider_disney", "kind":"freetext", "input":{"query":"Action","streaming_providers":["Disney Plus"],"limit":5},
     "min_hits":0},
    {"id":"provider_magenta", "kind":"freetext", "input":{"query":"Action","streaming_providers":["Magenta TV+"],"limit":5},
     "min_hits":0},
]

ML_HOOK_TESTS = [
    {"id":"ml_liked_jw_da", "kind":"freetext", "input":{"query":"empfehl mir was","liked_tmdb_ids":[245891,1813],"w_personal":0.6},
     "min_hits":0},
    {"id":"ml_external_boost", "kind":"freetext", "input":{"query":"Action","external_score_boost":{"245891":1.0},"w_external":1.5},
     "min_hits":0, "assert_film_in_top":("245891",5)},
]

EDGE_CASE_TESTS = [
    {"id":"edge_one_word", "kind":"freetext", "input":{"query":"Rache"},
     "intent_should_contain_theme_any_of":["revenge"], "min_hits":0},
    {"id":"edge_english_query", "kind":"freetext", "input":{"query":"feel-good cozy films"},
     "intent_should_contain_emotion_any_of":["comforting","joy","warmth"], "min_hits":0},
    {"id":"edge_long_query", "kind":"freetext", "input":{"query":"Ein Film bei dem ein Antiheld in einer dystopischen Zukunft gegen ein totalitäres System kämpft, mit moralischen Grauzonen und einer kleinen Liebesgeschichte"},
     "intent_should_contain_theme_any_of":["dystopian_future","power_corrupts","moral_dilemma"], "min_hits":0},
]

ALL_TESTS = (REFERENCE_TESTS + GENRE_MOOD_TESTS + ACTIVITY_TESTS + MODIFIER_TESTS
             + AVOID_TESTS + GENRE_FILTER_TESTS + YEAR_RUNTIME_TESTS
             + PROVIDER_TESTS + ML_HOOK_TESTS + EDGE_CASE_TESTS)

CATEGORIES = {
    "reference": REFERENCE_TESTS, "mood": GENRE_MOOD_TESTS, "activity": ACTIVITY_TESTS,
    "modifier": MODIFIER_TESTS, "avoid": AVOID_TESTS, "filter": GENRE_FILTER_TESTS,
    "year_runtime": YEAR_RUNTIME_TESTS, "provider": PROVIDER_TESTS,
    "ml_hook": ML_HOOK_TESTS, "edge": EDGE_CASE_TESTS,
}


# ─── RUNNER ───────────────────────────────────────────────────────────────

def run_test(base_url: str, tc: Dict[str, Any], latency_budget_ms: int = 8000) -> Dict[str, Any]:
    body = {"limit": tc.get("limit", 10), "runtime_min": tc.get("runtime_min", 60), **tc["input"]}
    t0 = time.time()
    try:
        r = requests.post(f"{base_url}/api/search", json=body, timeout=120)
        elapsed = (time.time() - t0) * 1000
        if r.status_code != 200:
            return {"id": tc["id"], "ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}",
                    "latency_ms": elapsed}
        data = r.json()
    except Exception as e:
        return {"id": tc["id"], "ok": False, "error": str(e), "latency_ms": (time.time()-t0)*1000}

    titles = [(rr.get("title") or "") for rr in data.get("results", [])]
    failures: List[str] = []

    # name-based hits
    hits = []
    for needle in tc.get("must_contain_any_of", []):
        for t in titles:
            if needle.lower() in t.lower() or t.lower() in needle.lower():
                hits.append(needle); break
    min_hits = tc.get("min_hits", 0)
    if min_hits > 0 and len(hits) < min_hits:
        failures.append(f"only {len(hits)} of expected films found, need >= {min_hits}")

    for needle in tc.get("must_not_match", []):
        bad = [t for t in titles if needle.lower() in t.lower()]
        if bad: failures.append(f"forbidden pattern '{needle}' matched: {bad}")

    intent = data.get("intent") or {}
    if "intent_should_contain_emotion_any_of" in tc:
        keys = list((intent.get("emotion_sparse") or {}).keys())
        if not any(w in keys for w in tc["intent_should_contain_emotion_any_of"]):
            failures.append(f"emotion lacks {tc['intent_should_contain_emotion_any_of']}, got {keys[:5]}")
    if "intent_should_contain_theme_any_of" in tc:
        keys = list((intent.get("theme_sparse") or {}).keys())
        if not any(w in keys for w in tc["intent_should_contain_theme_any_of"]):
            failures.append(f"theme lacks {tc['intent_should_contain_theme_any_of']}, got {keys[:5]}")
    if tc.get("intent_should_have_avoid"):
        if not (intent.get("avoid_emotions") or intent.get("avoid_themes")):
            failures.append("intent should have at least one avoid_* entry")

    if "expected_reference_title_substring" in tc:
        rt = data.get("reference_title") or ""
        if tc["expected_reference_title_substring"].lower() not in rt.lower():
            failures.append(f"reference_title='{rt}' missing substring '{tc['expected_reference_title_substring']}'")

    if "assert_no_film_has_emotion_above" in tc:
        bad_emo, thresh = tc["assert_no_film_has_emotion_above"]
        offenders = [f"{rr['title']}({rr.get('emotion_dna',{}).get(bad_emo,0):.2f})"
                     for rr in data.get("results", [])
                     if (rr.get("emotion_dna") or {}).get(bad_emo, 0) > thresh]
        if offenders: failures.append(f"avoid '{bad_emo}'>{thresh} leaked: {offenders[:3]}")

    if "assert_all_have_genre" in tc:
        g = tc["assert_all_have_genre"]
        offenders = [rr["title"] for rr in data.get("results", []) if g not in (rr.get("genres") or [])]
        if offenders: failures.append(f"genre={g} filter leaked: {offenders[:3]}")
    if "assert_all_have_any_genre" in tc:
        gs = set(tc["assert_all_have_any_genre"])
        offenders = [rr["title"] for rr in data.get("results", [])
                     if not (gs & set(rr.get("genres") or []))]
        if offenders: failures.append(f"any-of-genre {gs} filter leaked: {offenders[:3]}")
    if "assert_all_year_at_least" in tc:
        y = tc["assert_all_year_at_least"]
        offenders = [(rr["title"], rr.get("year")) for rr in data.get("results", [])
                     if rr.get("year") and rr["year"] < y]
        if offenders: failures.append(f"year>={y} leaked: {offenders[:3]}")
    if "assert_all_runtime_at_most" in tc:
        m = tc["assert_all_runtime_at_most"]
        offenders = [(rr["title"], rr.get("runtime")) for rr in data.get("results", [])
                     if rr.get("runtime") and rr["runtime"] > m]
        if offenders: failures.append(f"runtime<={m} leaked: {offenders[:3]}")
    if "assert_film_in_top" in tc:
        film_id, top_n = tc["assert_film_in_top"]
        ids_top = [str(rr.get("tmdb_id")) for rr in data.get("results", [])[:top_n]]
        if str(film_id) not in ids_top:
            failures.append(f"film {film_id} not in top-{top_n}: {ids_top}")

    if elapsed > latency_budget_ms:
        failures.append(f"latency {elapsed:.0f}ms > budget {latency_budget_ms}ms")

    return {
        "id": tc["id"], "ok": not failures, "failures": failures,
        "hits_found": hits, "n_results": len(titles),
        "latency_ms": elapsed, "search_time_ms": data.get("search_time_ms"),
        "top_titles": titles[:5],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--json", default=None)
    ap.add_argument("--category", default=None, help=f"one of {list(CATEGORIES.keys())}")
    args = ap.parse_args()

    tests = CATEGORIES.get(args.category, ALL_TESTS) if args.category else ALL_TESTS
    print(f"Running {len(tests)} tests against {args.base}\n")
    results = []
    by_cat: Dict[str, Dict[str, int]] = {}
    for tc in tests:
        rec = run_test(args.base, tc)
        results.append(rec)
        # category summary
        cat = next((k for k, v in CATEGORIES.items() if tc in v), "uncategorized")
        by_cat.setdefault(cat, {"pass":0,"fail":0})
        by_cat[cat]["pass" if rec["ok"] else "fail"] += 1
        # output
        status = "✅" if rec["ok"] else "❌"
        lat = rec.get("latency_ms", 0)
        print(f"  {status} [{cat:<8}] {rec['id']:<32} {lat:>6.0f}ms")
        if not rec["ok"]:
            for f in rec.get("failures", [])[:3]:
                print(f"     ↳ {f}")

    n = len(results); passed = sum(1 for r in results if r["ok"])
    print(f"\n{'='*70}\n  TOTAL: {passed}/{n} passed ({100*passed/n if n else 0:.0f}%)")
    print(f"  Avg latency: {sum(r.get('latency_ms',0) for r in results)/max(n,1):.0f}ms")
    print("\n  Per-category:")
    for cat, c in sorted(by_cat.items()):
        total = c['pass']+c['fail']
        print(f"    {cat:<14}  {c['pass']}/{total}  ({100*c['pass']/total:.0f}%)")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"summary":{"passed":passed,"total":n,"by_category":by_cat},
                       "results":results}, f, indent=2)
        print(f"\n  Detailed results → {args.json}")
    sys.exit(0 if passed == n else 1)


if __name__ == "__main__":
    main()
