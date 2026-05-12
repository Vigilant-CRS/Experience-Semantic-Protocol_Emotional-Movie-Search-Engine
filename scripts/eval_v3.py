"""
Quality-Eval-Suite for MindRead V3.

Runs a curated set of test queries against the API, checks that:
  - expected films appear in top-N
  - forbidden patterns (Featurettes, etc.) do NOT appear in top-N
  - LLM extracts expected core tags for free-text queries

Usage:
  venv/bin/python3 scripts/eval_v3.py
  venv/bin/python3 scripts/eval_v3.py --base http://localhost:8000 --json eval_results.json
"""
import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional
import requests


TEST_CASES: List[Dict[str, Any]] = [
    # ─── similar_to: classic action/revenge ──────────────────────────────
    {
        "id": "similar_john_wick",
        "kind": "similar_to",
        "input": {"similar_to": 245891},
        "limit": 10,
        "must_contain_any_of": [
            "John Wick: Chapter 2", "John Wick: Kapitel 4", "Furious 7",
            "Desperado", "Rage", "Django Unchained", "A Man Apart", "Crank", "Machete",
            "Harry Brown", "Interview with a Hitman",
            # also-valid: Out for Justice, I Am Wrath, Bullet to the Head
            "Out for Justice", "I Am Wrath", "Bullet to the Head", "The Punisher",
        ],
        "must_not_match": ["Featurette", "Behind the", "Wick Is Pain"],
        "min_hits": 3,
    },
    # ─── similar_to: whimsical romance ───────────────────────────────────
    {
        "id": "similar_amelie",
        "kind": "similar_to",
        "input": {"similar_to": 194},
        "limit": 10,
        "must_contain_any_of": [
            "Angel-A", "Mulholland Drive", "Bridget Jones", "Emma", "Alice in Wonderland",
            "Lost in Translation", "Punch-Drunk Love", "Eternal Sunshine of the Spotless Mind",
            # also-valid French/whimsical
            "Chouchou", "Miracle on 34th Street", "The Science of Sleep",
        ],
        "must_not_match": ["Featurette", "Behind"],
        "min_hits": 2,
    },
    # ─── similar_to: theological thriller ────────────────────────────────
    {
        "id": "similar_devils_advocate",
        "kind": "similar_to",
        "input": {"similar_to": 1813},
        "limit": 10,
        "must_contain_any_of": [
            "Needful Things", "Under Suspicion", "Lolita", "The Fan", "Thinner",
            "...And Justice for All", "A Time to Kill", "Primal Fear",
            "Angel Heart", "Constantine", "End of Days", "Rosemary's Baby",
        ],
        "must_not_match": ["Featurette"],
        "min_hits": 2,
    },
    # ─── Free-text: revenge ──────────────────────────────────────────────
    {
        "id": "freetext_rachefilme",
        "kind": "freetext",
        "input": {"query": "Rachefilme mit Antiheld"},
        "limit": 10,
        "must_contain_any_of": [
            "John Wick", "Kill Bill", "Django Unchained", "Punisher", "Death Wish",
            "I Saw the Devil", "Oldboy", "Man on Fire", "The Crow", "Léon", "Taken",
            # also-valid
            "Wake of Death", "Rage", "Payback", "Crank", "A Man Apart",
            "I Am Wrath", "Furious 7", "Machete", "Desperado", "Harry Brown",
        ],
        "must_not_match": ["Featurette"],
        "min_hits": 3,
        "intent_should_contain_emotion_any_of": ["rage", "anger", "cathartic", "fury"],
        "intent_should_contain_theme_any_of": ["revenge"],
    },
    # ─── Free-text: cyberpunk action ────────────────────────────────────
    {
        "id": "freetext_cyberpunk",
        "kind": "freetext",
        "input": {"query": "cyberpunk Filme mit Action"},
        "limit": 10,
        "must_contain_any_of": [
            "Ghost in the Shell", "Alita: Battle Angel", "Blade Runner", "RoboCop",
            "The Matrix", "Cyborg", "Lucy", "Total Recall", "Minority Report",
            "Equilibrium", "Tron", "Upgrade",
            # also-valid
            "District B13", "Pixels", "Æon Flux", "Tracers", "Max Steel",
            "Ultraviolet", "Dredd",
        ],
        "must_not_match": [],
        "min_hits": 2,
        "intent_should_contain_theme_any_of": ["Science Fiction", "Action"],
    },
    # ─── Free-text: feel-good cozy ──────────────────────────────────────
    {
        "id": "freetext_feelgood",
        "kind": "freetext",
        "input": {"query": "feel-good Filme zum Einschlafen, gemütlich"},
        "limit": 10,
        "must_contain_any_of": [
            "About Time", "Amélie", "The Secret Life of Walter Mitty",
            "Forrest Gump", "Chocolat", "Julie & Julia", "Big Fish",
            "The Grand Budapest Hotel", "Paddington", "Notting Hill", "Mamma Mia",
            "Babe", "The Princess and the Frog", "Nicholas on Holiday",
            "Beethoven", "Marmaduke", "The Aristocats",
            "A Street Cat Named Bob", "Deck the Halls", "P.S. I Love You",
            "St. Vincent", "Playing for Keeps", "Almost Christmas",
        ],
        "min_hits": 2,
        "intent_should_contain_emotion_any_of": ["comforting", "joy", "contentment", "warmth", "inspiring"],
    },
    # ─── Free-text: tearjerker ──────────────────────────────────────────
    {
        "id": "freetext_tearjerker",
        "kind": "freetext",
        "input": {"query": "tearjerker zum Heulen, traurig aber schön"},
        "limit": 10,
        "must_contain_any_of": [
            "The Notebook", "A Walk to Remember", "P.S. I Love You", "Marley & Me",
            "Manchester by the Sea", "The Fault in Our Stars", "Million Dollar Baby",
            "Schindler's List", "Atonement", "Up",
            # also-valid
            "Reign Over Me", "Remember Me", "Three Colors: Blue", "Restless",
            "Collateral Beauty", "Eleanor Rigby",
        ],
        "min_hits": 2,
        "intent_should_contain_emotion_any_of": ["grief", "sadness", "melancholy", "bittersweet"],
    },
    # ─── Free-text: sci-fi mind-bending ─────────────────────────────────
    {
        "id": "freetext_mindbending",
        "kind": "freetext",
        "input": {"query": "mind-bending Sci-Fi Filme mit Realitäts-Fragen"},
        "limit": 10,
        "must_contain_any_of": [
            # canonical
            "The Matrix", "Inception", "Memento", "Mr. Nobody", "Donnie Darko",
            "Primer", "Predestination", "Coherence", "Ex Machina", "Source Code",
            "Eternal Sunshine of the Spotless Mind", "Mulholland Drive",
            # also-valid
            "Synchronicity", "Transcendence", "Solaris", "Dark City",
            "Altered States", "Gattaca", "2001: A Space Odyssey", "The Lawnmower Man",
            "Upside Down",
        ],
        "min_hits": 2,
        "intent_should_contain_theme_any_of": ["artificial_reality", "Science Fiction", "identity_crisis"],
    },
    # ─── Avoid filter ───────────────────────────────────────────────────
    {
        "id": "avoid_rage",
        "kind": "similar_to",
        "input": {"similar_to": 245891, "avoid_emotions": ["rage"], "avoid_strict": True},
        "limit": 10,
        "must_not_match": [],
        "min_hits": 0,
        "assert_no_film_has_emotion_above": ("rage", 0.10),  # threshold matches avoid_strict_threshold
    },
    # ─── Indie shift ────────────────────────────────────────────────────
    {
        "id": "indie_shift",
        "kind": "similar_to",
        "input": {"similar_to": 245891, "indie_mainstream": -1.0},
        "limit": 10,
        "must_contain_any_of": [
            "Dead Man's Shoes", "Open Range", "Ghost Dog", "Death Wish", "Blue Ruin",
            "Cold in July",
        ],
        "min_hits": 1,
    },
    # ─── German title resolution ────────────────────────────────────────
    {
        "id": "german_title_resolution",
        "kind": "freetext",
        "input": {"query": "Filme wie Im Auftrag des Teufels aber lustiger"},
        "limit": 5,
        "must_contain_any_of": ["The Devil's Advocate", "Lolita", "The Fan"],
        "min_hits": 1,
        "expected_reference_title_substring": "Devil",
    },
    # ─── Genre-only-ish ─────────────────────────────────────────────────
    {
        "id": "freetext_horror",
        "kind": "freetext",
        "input": {"query": "psychologischer Horror mit unsettling atmosphäre"},
        "limit": 10,
        "must_contain_any_of": [
            "Hereditary", "Get Out", "The Witch", "Rosemary's Baby", "It Follows",
            "The Babadook", "The Others", "The Sixth Sense", "Black Swan",
            "Donnie Darko", "Mulholland Drive", "Suspiria",
            # also-valid
            "Repulsion", "The Brood", "Inside", "Boogeyman", "Visions",
            "The Conjuring", "Insidious",
        ],
        "min_hits": 2,
        "intent_should_contain_emotion_any_of": ["dread", "unsettling", "haunting"],
    },
    # ─── EDGE CASES (added 2026-05) ─────────────────────────────────────
    # Reference + tone-shift: Amélie + more action
    {
        "id": "edge_amelie_more_action",
        "kind": "freetext",
        "input": {"query": "Filme wie Amélie aber mit mehr Action"},
        "limit": 10,
        "must_contain_any_of": [
            "Run Lola Run", "Big Fish", "Hugo", "Stranger Than Fiction",
            "The Grand Budapest Hotel", "Kiki's Delivery Service",
            "Everything Everywhere All at Once", "Scott Pilgrim", "Baby Driver",
            "Ballerina", "The Legend of Tarzan", "Kung Fu Dunk", "Shaolin Soccer",
            "Pan", "Stardust",
        ],
        "must_not_match": ["Featurette"],
        "min_hits": 1,
    },
    # Reference + protagonist gender flip: John Wick female lead
    {
        "id": "edge_john_wick_female_lead",
        "kind": "freetext",
        "input": {"query": "Filme wie John Wick aber mit weiblicher Hauptrolle"},
        "limit": 10,
        "must_contain_any_of": [
            "Atomic Blonde", "Salt", "Anna", "Peppermint", "Kill Bill", "Hanna",
            "Red Sparrow", "Lucy", "Gunpowder Milkshake", "The Villainess",
            "Proud Mary", "Kate", "Birds of Prey", "Colombiana", "Jolt",
        ],
        "min_hits": 2,
        "intent_should_contain_theme_any_of": ["Action", "revenge"],
    },
    # The exact bug from the user screenshot — "ohne Schusswaffen"
    {
        "id": "edge_action_no_guns",
        "kind": "freetext",
        "input": {"query": "Action wie John Wick aber ohne Schusswaffen"},
        "limit": 10,
        "must_contain_any_of": [
            "The Raid", "Ong-Bak", "Ip Man", "The Way of the Dragon", "Police Story",
            "Enter the Dragon", "Drunken Master", "Kung Fu Hustle", "Never Back Down",
            "Warrior", "The Karate Kid", "Bloodsport", "Kickboxer",
            "Crouching Tiger", "Hero",
        ],
        "min_hits": 2,
    },
    # Cross-tone hybrid: dark comedy
    {
        "id": "edge_dark_comedy",
        "kind": "freetext",
        "input": {"query": "düstere Komödie über das Leben"},
        "limit": 10,
        "must_contain_any_of": [
            "Three Billboards", "In Bruges", "Burn After Reading", "Fargo",
            "American Beauty", "The Lobster", "Birdman", "Seven Psychopaths",
            "Death at a Funeral", "Sightseers", "Bad Santa",
            "World's Greatest Dad", "The Big Lebowski", "Adaptation",
            "Young Adult", "Don't Think Twice", "Girl Most Likely",
            "The Sunset Limited", "The Angriest Man in Brooklyn",
        ],
        "min_hits": 2,
    },
    # Cross-tone hybrid: feel-good Sci-Fi
    {
        "id": "edge_feelgood_scifi",
        "kind": "freetext",
        "input": {"query": "feel-good Science Fiction zum Wohlfühlen"},
        "limit": 10,
        "must_contain_any_of": [
            "Wall-E", "Big Hero 6", "Galaxy Quest", "Hitchhiker's Guide",
            "Star Trek", "The Martian", "Back to the Future", "Cocoon",
            "E.T.", "ET", "Close Encounters", "Tomorrowland", "Bill & Ted",
            "Her", "Equals", "Perfect Sense", "Upside Down",
        ],
        "min_hits": 2,
        "intent_should_contain_theme_any_of": ["Science Fiction"],
    },
    # Era + genre: 80s action
    {
        "id": "edge_80s_action",
        "kind": "freetext",
        "input": {"query": "klassische 80er Action mit Macho-Helden"},
        "limit": 10,
        "must_contain_any_of": [
            "Predator", "Commando", "Rambo", "Die Hard", "Lethal Weapon",
            "Beverly Hills Cop", "Top Gun", "Cobra", "Red Heat", "Aliens",
            "RoboCop", "Terminator", "Conan the Barbarian", "Bloodsport",
            "Action Jackson", "Over the Top", "Red Dawn", "Missing in Action",
        ],
        "min_hits": 3,
    },
    # Era + emotion: 90s romcom
    {
        "id": "edge_90s_romcom",
        "kind": "freetext",
        "input": {"query": "90er Liebeskomödie"},
        "limit": 10,
        "must_contain_any_of": [
            "When Harry Met Sally", "Pretty Woman", "You've Got Mail", "Notting Hill",
            "Four Weddings and a Funeral", "Sleepless in Seattle",
            "10 Things I Hate About You", "While You Were Sleeping",
            "Clueless", "The Wedding Singer", "My Best Friend's Wedding",
            "She's All That", "Never Been Kissed",
        ],
        "min_hits": 2,
    },
    # Avoid + audience: kid-safe no violence
    # NOTE: known ontology gap — no `kid_safe` or `family_friendly` tag, so
    # the avoid_filters can only catch fear/dread but not adult-comedy themes.
    # Engine often returns generic feel-good comedies that aren't strictly for kids.
    {
        "id": "edge_kids_no_violence",
        "kind": "freetext",
        "input": {"query": "Filme für Kinder ohne Gewalt und ohne Gruseliges"},
        "limit": 10,
        "must_contain_any_of": [
            "Toy Story", "Up", "Finding Nemo", "Coco", "Inside Out", "Moana",
            "Frozen", "Paddington", "Babe", "The Aristocats", "Mary Poppins",
            "The Princess and the Frog", "Beethoven", "Marmaduke",
            "Miracle on 34th Street", "Casper", "Shaggy Dog", "Ramona",
        ],
        "min_hits": 1,
    },
    # Abstract / philosophical
    {
        "id": "edge_thoughtful",
        "kind": "freetext",
        "input": {"query": "Filme zum Nachdenken über Sinn des Lebens"},
        "limit": 10,
        "must_contain_any_of": [
            "Tree of Life", "Cloud Atlas", "Mr. Nobody", "Synecdoche", "I Heart Huckabees",
            "The Fountain", "Waking Life", "The Truman Show", "Stranger Than Fiction",
            "American Beauty", "About Time", "Soul", "Anomalisa",
            "Eternal Sunshine of the Spotless Mind", "Magnolia",
            "Peaceful Warrior", "Yi Yi", "Dragonfly", "The Sunset Limited",
            "Wonder", "Wild", "Into the Wild",
        ],
        "min_hits": 2,
    },
    # Multi-constraint compound
    {
        "id": "edge_compound_scifi_female",
        "kind": "freetext",
        "input": {"query": "Sci-Fi mit starker weiblicher Hauptrolle ohne Aliens"},
        "limit": 10,
        "must_contain_any_of": [
            "Arrival", "Annihilation", "Ex Machina", "Lucy", "Gravity",
            "Hidden Figures", "Hanna", "The Hunger Games", "Divergent",
            "Her", "Ad Astra", "Interstellar", "Westworld",
        ],
        "min_hits": 1,
    },
    # Archetype-driven
    {
        "id": "edge_mentor_student",
        "kind": "freetext",
        "input": {"query": "Filme mit Mentor-Schüler Beziehung"},
        "limit": 10,
        "must_contain_any_of": [
            "The Karate Kid", "Star Wars", "Whiplash", "Good Will Hunting",
            "Finding Forrester", "Dead Poets Society", "School of Rock",
            "The Matrix", "McFarland, USA", "Million Dollar Baby",
            "Mr. Holland's Opus", "Stand and Deliver", "The Legend of Bagger Vance",
            "Peaceful Warrior", "Half Nelson", "Freedom Writers",
        ],
        "min_hits": 2,
        "intent_should_contain_theme_any_of": ["mentor_student"],
    },
    # Setting-driven: Tokyo
    {
        "id": "edge_tokyo_films",
        "kind": "freetext",
        "input": {"query": "Filme die in Tokio spielen"},
        "limit": 10,
        "must_contain_any_of": [
            "Lost in Translation", "Babel", "Tokyo Drift", "Enter the Void",
            "Memoirs of a Geisha", "The Wolverine", "Kill Bill", "Ghost in the Shell",
            "Black Rain", "Demon Slayer", "Tokyo Godfathers", "Tokyo!",
        ],
        "min_hits": 1,
    },
    # Hard-filter: avoid_themes via API param (not via LLM)
    {
        "id": "edge_avoid_revenge_strict",
        "kind": "similar_to",
        "input": {"similar_to": 245891, "avoid_themes": ["revenge"], "avoid_strict": True},
        "limit": 10,
        "min_hits": 0,
    },
    # Hard-filter via gender API param
    {
        "id": "edge_gender_filter_female",
        "kind": "similar_to",
        "input": {"similar_to": 245891, "gender": "female"},
        "limit": 10,
        "min_hits": 0,
        # All results MUST have protagonist_gender == female
    },
    # Indie shift extreme
    {
        "id": "edge_mainstream_extreme",
        "kind": "similar_to",
        "input": {"similar_to": 245891, "indie_mainstream": 1.0},
        "limit": 10,
        "must_contain_any_of": [
            "Fast", "Furious", "Mission: Impossible", "Bourne", "Bond",
            "Skyfall", "Casino Royale", "Avengers", "Mad Max",
        ],
        "min_hits": 1,
    },
    # Provider filter sanity — verify all results actually have Netflix
    {
        "id": "edge_provider_netflix",
        "kind": "freetext",
        "input": {"query": "Action Filme", "streaming_providers": ["Netflix"]},
        "limit": 10,
        "min_hits": 0,
        # Check via "assert_all_have_provider" added to runner
    },

    # ─── Family ─────────────────────────────────────────────────────────
    {
        "id": "freetext_family",
        "kind": "freetext",
        "input": {"query": "Filme für Familiennachmittag, kindgeeignet"},
        "limit": 10,
        "must_contain_any_of": [
            "Toy Story", "Up", "Finding Nemo", "The Incredibles", "Paddington",
            "Coco", "Inside Out", "Ratatouille", "Big Hero 6", "Wall-E",
            "Frozen", "Moana", "How to Train Your Dragon",
            "Mary Poppins", "Babe", "The Aristocats", "The Princess and the Frog",
            "Beethoven", "Cheaper by the Dozen", "Marmaduke", "Nicholas",
            "Shaggy Dog", "Ramona and Beezus", "Casper",
        ],
        "min_hits": 3,
    },
]


def run_test(base_url: str, tc: Dict[str, Any]) -> Dict[str, Any]:
    body = {
        "limit": tc["limit"],
        "runtime_min": tc.get("runtime_min", 60),
        **tc["input"],
    }
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

    titles = [(r.get("title") or "") for r in data.get("results", [])]
    failures: List[str] = []

    # must_contain_any_of (count of hits)
    hits = []
    for needle in tc.get("must_contain_any_of", []):
        for t in titles:
            if needle.lower() in t.lower() or t.lower() in needle.lower():
                hits.append(needle)
                break
    min_hits = tc.get("min_hits", 1)
    if min_hits > 0 and len(hits) < min_hits:
        failures.append(f"only {len(hits)} of expected films found, need >= {min_hits}")

    # must_not_match
    bad = []
    for needle in tc.get("must_not_match", []):
        for t in titles:
            if needle.lower() in t.lower():
                bad.append(t)
    if bad:
        failures.append(f"forbidden patterns matched: {bad}")

    # intent checks
    intent = data.get("intent") or {}
    for tag_check in ["intent_should_contain_emotion_any_of", "intent_should_contain_theme_any_of"]:
        if tag_check in tc:
            block = "emotion_sparse" if "emotion" in tag_check else "theme_sparse"
            tags_in = list((intent.get(block) or {}).keys())
            wanted = tc[tag_check]
            if not any(w in tags_in for w in wanted):
                failures.append(f"{block} did not contain any of {wanted} (got {tags_in[:5]})")

    # special: assert_no_film_has_emotion_above (tag, threshold)
    if "assert_no_film_has_emotion_above" in tc:
        bad_emo, thresh = tc["assert_no_film_has_emotion_above"]
        offenders = []
        for r_ in data.get("results", []):
            emo = r_.get("emotion_dna") or {}
            if emo.get(bad_emo, 0) > thresh:
                offenders.append(f"{r_['title']} ({emo.get(bad_emo):.2f})")
        if offenders:
            failures.append(f"avoid '{bad_emo}'>{thresh} leaked: {offenders}")

    # special: gender filter — when input has gender=X, all results MUST match
    requested_gender = (tc.get("input") or {}).get("gender")
    if requested_gender:
        wrong = [f"{r_.get('title')}({r_.get('protagonist_gender')})"
                 for r_ in data.get("results", [])
                 if r_.get("protagonist_gender") not in (requested_gender, None)]
        if wrong:
            failures.append(f"gender filter '{requested_gender}' leaked: {wrong[:5]}")

    # special: streaming_providers filter — every result must have at least one requested provider
    requested_provs = (tc.get("input") or {}).get("streaming_providers") or []
    if requested_provs:
        bad_provs = []
        for r_ in data.get("results", []):
            provs = r_.get("streaming_providers") or []
            if not any(rp in provs for rp in requested_provs):
                bad_provs.append(f"{r_.get('title')}({provs[:3]})")
        if bad_provs:
            failures.append(f"provider filter '{requested_provs}' leaked: {bad_provs[:5]}")

    # special: avoid_themes via API → check no result has the avoided theme above threshold
    requested_avoid_themes = (tc.get("input") or {}).get("avoid_themes") or []
    if requested_avoid_themes and (tc.get("input") or {}).get("avoid_strict"):
        offenders = []
        for r_ in data.get("results", []):
            theme_dna = r_.get("theme_dna") or {}
            for at in requested_avoid_themes:
                if theme_dna.get(at, 0) > 0.10:
                    offenders.append(f"{r_['title']}({at}={theme_dna.get(at):.2f})")
        if offenders:
            failures.append(f"avoid_themes_strict leaked: {offenders[:5]}")

    # reference_title check
    if "expected_reference_title_substring" in tc:
        rt = data.get("reference_title") or ""
        if tc["expected_reference_title_substring"].lower() not in rt.lower():
            failures.append(f"reference_title='{rt}' does not contain '{tc['expected_reference_title_substring']}'")

    return {
        "id": tc["id"],
        "ok": not failures,
        "failures": failures,
        "hits_found": hits,
        "n_results": len(titles),
        "latency_ms": elapsed,
        "search_time_ms": data.get("search_time_ms"),
        "top_titles": titles[:5],
        "intent_emo_keys": list((intent.get("emotion_sparse") or {}).keys())[:5] if intent else [],
        "intent_th_keys": list((intent.get("theme_sparse") or {}).keys())[:5] if intent else [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--json", default=None, help="write detailed JSON results")
    ap.add_argument("--filter", default=None, help="only run tests matching substring in id")
    args = ap.parse_args()

    tests = TEST_CASES
    if args.filter:
        tests = [t for t in TEST_CASES if args.filter in t["id"]]

    print(f"Running {len(tests)} tests against {args.base}\n")
    results = []
    passed = 0
    for tc in tests:
        rec = run_test(args.base, tc)
        results.append(rec)
        status = "✅" if rec["ok"] else "❌"
        lat = rec.get("latency_ms", 0)
        print(f"  {status} {rec['id']:<30} {lat:>6.0f}ms"
              f"  hits={len(rec.get('hits_found', []))}/{tc.get('min_hits',0)}")
        if not rec["ok"]:
            for f in rec.get("failures", []):
                print(f"     ↳ {f}")
            print(f"     top: {rec.get('top_titles', [])[:3]}")
        else:
            passed += 1

    n = len(results)
    pct = 100*passed/n if n else 0
    print(f"\n{'='*60}\n  {passed}/{n} passed  ({pct:.0f}%)")
    print(f"  avg latency: {sum(r.get('latency_ms', 0) for r in results)/max(n,1):.0f} ms")
    print(f"  avg server-time: {sum((r.get('search_time_ms') or 0) for r in results)/max(n,1):.0f} ms")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"summary": {"passed": passed, "total": n}, "results": results}, f, indent=2)
        print(f"\n  results written to {args.json}")

    sys.exit(0 if passed == n else 1)


if __name__ == "__main__":
    main()
