"""
Copyright (c) 2026 Damir Dulovic. All rights reserved.
Licensed under the MindRead Proprietary Software License (see LICENSE).

DNA-Extractor V3 — extracts ontology-v3 DNA per film via OpenAI Chat API.

Output JSONL: one line per film with fields
  tmdb_id, title, year, raw_llm, dna_v3
where dna_v3 contains L1-normalized weighted dicts per bucket.

Usage:
  venv/bin/python3 scripts/extract_dna_v3.py --pilot              # 5 test films
  venv/bin/python3 scripts/extract_dna_v3.py --limit 100          # first 100
  venv/bin/python3 scripts/extract_dna_v3.py                      # all
  venv/bin/python3 scripts/extract_dna_v3.py --workers 20         # parallelism
"""
import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
ONT_DIR = ROOT / "config" / "ontology_v3"
DATA_DIR = ROOT / "data"
SOURCE = ROOT / "movies_export.json"
OUT = DATA_DIR / "movies_dna_v3.jsonl"
ERR = DATA_DIR / "movies_dna_v3.errors.jsonl"

OPENAI_MODEL = os.getenv("OPENAI_MODEL_DNA", "gpt-5.4-mini")
OPENAI_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"


# GPT-5 / o-series use max_completion_tokens and reject custom temperature
def _is_new_model(name: str) -> bool:
    return ("gpt-5" in name) or name.startswith("o3") or name.startswith("o4") or name.startswith("o1")


class QuotaExhausted(RuntimeError):
    """Raised when the OpenAI account has insufficient quota — retry is futile."""


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_ontology() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in ["emotions", "wirkung", "plot_themes", "genres",
                 "settings", "archetypes", "moods", "pacing",
                 "content_features", "subjects",
                 "color_palette", "protagonist_age"]:
        path = ONT_DIR / f"{name}.json"
        if path.exists():
            out[name] = json.load(open(path))["tags"]
        else:
            out[name] = []  # graceful: missing optional bucket = empty
    out["definitions"] = json.load(open(ONT_DIR / "tag_definitions.json"))["definitions"]
    out["synonyms"] = json.load(open(ONT_DIR / "synonyms.json"))["groups"]
    return out


def build_system_prompt(ont: Dict[str, Any]) -> str:
    """Static system prompt — eligible for OpenAI prompt caching."""
    defs = ont["definitions"]

    def fmt(tags: List[str]) -> str:
        return "\n".join(f"  - {t}: {defs.get(t, '?')}" for t in tags)

    return f"""You are a film-DNA extractor. Given a film's title, year, overview, keywords and TMDB genres, you output a structured DNA in JSON.

CRITICAL RULES:
1. Use ONLY the canonical tags from the lists below. No new terms.
2. Each block (emotions+wirkung, themes+genres, setting, mood, pacing) is a weighted dict where weights sum to ~1.0 (don't worry about exact normalization — code will renormalize).
3. Use 3-7 tags per block. Don't fill all of them. Pick the most defining.
4. archetype is a SINGLE value from the archetype list.
5. protagonist_gender is one of: male, female, ensemble, non_binary.
6. protagonist_age is a SINGLE value from the protagonist_age list (best estimate from synopsis).
7. Return strict JSON only.

== EMOTIONS (Plutchik 8 families × 3 intensities, 24 tags) ==
{fmt(ont['emotions'])}

== WIRKUNG (viewer impact, 6 tags) ==
{fmt(ont['wirkung'])}

== PLOT_THEMES (35 tags) ==
{fmt(ont['plot_themes'])}

== GENRES (TMDB feature-film, 18 tags — distribute weights across genres that fit, even if TMDB only labels 1-2) ==
{fmt(ont['genres'])}

== SETTINGS (15 tags) ==
{fmt(ont['settings'])}

== ARCHETYPES (10 tags, pick ONE) ==
{fmt(ont['archetypes'])}

== MOODS (12 tags) ==
{fmt(ont['moods'])}

== PACING (8 tags) ==
{fmt(ont['pacing'])}

== CONTENT FEATURES ({len(ont['content_features'])} tags — content/violence advisories, only set when prominently present) ==
{fmt(ont['content_features'])}

== SUBJECTS ({len(ont['subjects'])} tags — what the film is ABOUT topically; only set when CENTRAL to the film) ==
{fmt(ont['subjects'])}

== COLOR_PALETTE ({len(ont['color_palette'])} tags — dominant visual look; pick 1-2 only when clearly inferable from genre/era/setting) ==
{fmt(ont['color_palette'])}

== PROTAGONIST_AGE ({len(ont['protagonist_age'])} tags — approximate age of main protagonist, pick ONE) ==
{fmt(ont['protagonist_age'])}

== OUTPUT SCHEMA ==
{{
  "emotions":   {{"tag": weight, ...}},     // 3-6 entries from emotions list
  "wirkung":    {{"tag": weight, ...}},     // 1-3 entries from wirkung list
  "themes":     {{"tag": weight, ...}},     // 3-6 entries from plot_themes list
  "genres":     {{"tag": weight, ...}},     // 1-3 entries from genres list (use TMDB genres as starting point)
  "setting":    {{"tag": weight, ...}},     // 1-2 entries from settings list
  "archetype":  "tag",                       // SINGLE value from archetypes list
  "mood":       {{"tag": weight, ...}},     // 1-3 entries from moods list
  "pacing":     {{"tag": weight, ...}},     // 1-2 entries from pacing list
  "content_features": {{"tag": weight, ...}}, // 0-5 entries — only PROMINENTLY featured content
  "subjects":   {{"tag": weight, ...}},     // 0-3 entries — only CENTRAL subjects (a Mafia film
                                             // gets {{"mafia": 1.0}}; a thriller with one mob scene gets {{}})
  "color_palette": {{"tag": weight, ...}},  // 0-2 entries — only when clearly inferable
  "protagonist_gender": "male|female|ensemble|non_binary",
  "protagonist_age": "child|teen|young_adult|adult|mature_adult|senior"
}}

== FEW-SHOT EXAMPLE ==
INPUT:
title: "John Wick"
year: 2014
tmdb_genres: ["Action", "Thriller"]
overview: "An ex-hit-man comes out of retirement to track down the gangsters that killed his dog and took everything from him."
keywords: ["assassin", "revenge", "dog", "hitman", "new york"]

OUTPUT:
{{
  "emotions": {{"rage": 0.3, "grief": 0.25, "anticipation": 0.2, "dread": 0.15, "frustration": 0.1}},
  "wirkung":  {{"cathartic": 0.7, "haunting": 0.3}},
  "themes":   {{"revenge": 0.5, "grief_and_loss": 0.2, "underdog_triumph": 0.15, "betrayal": 0.15}},
  "genres":   {{"Action": 0.6, "Thriller": 0.3, "Crime": 0.1}},
  "setting":  {{"urban_modern": 0.7, "criminal_underworld": 0.3}},
  "archetype": "antihero",
  "mood":     {{"dark": 0.5, "gritty": 0.3, "noir": 0.2}},
  "pacing":   {{"action_packed": 0.7, "fast_paced": 0.3}},
  "protagonist_gender": "male"
}}
"""


def build_query_user_prompt(query: str) -> str:
    """Canonical user-prompt for free-text QUERY extraction.

    Single source of truth — used by api_v3.py (OpenAI runtime),
    scripts/llm_local.py (Qwen runtime) and scripts/search_v3.py CLI.
    Keeping this function in one place prevents the drift we had between
    three divergent prompt copies (audit F-006).
    """
    return f"""The user query (search request, not film description):
"{query}"

Extract the same DNA schema as if this were a film description, representing what the
user WANTS to see/feel. 2-5 tags per block, weights reflect priority. If the user says
"without X" or "ohne X", do NOT include those tags but list them in
"avoid_emotions" and "avoid_themes" arrays. Return strict JSON.

For ambiguous genre/style words, map aggressively to canonical tags:
  - "cyberpunk" → Action, Science Fiction, identity_crisis, dystopian themes
  - "noir"      → noir mood, mystery_investigation, dark atmosphere
  - "feel-good" → comforting, inspiring, joy, light mood
  - "tearjerker"→ grief, bittersweet, sadness

For subject queries, fill the "subjects" block with the matching canonical tag(s) from
the SUBJECTS bucket above. This is the strongest signal for "give me films ABOUT X":
  - "Mafiafilme" / "Gangsterfilme" → subjects={{"mafia": 1.0}}
  - "Vampirfilme" → subjects={{"vampire": 1.0}}
  - "Spionagefilme" → subjects={{"espionage": 1.0}}
  - "Kampfsportfilme" → subjects={{"martial_arts": 1.0}}
  - "Sportfilme" → subjects={{"sports": 1.0}}
  - "Knastfilme" / "prison" → subjects={{"prison_life": 1.0}}
  - "Anime" → subjects={{"anime": 1.0}}
  - "Found-Footage Horror" → subjects={{"found_footage": 0.6}}, themes={{"Horror": 0.4}}
  - "Biopic über Musiker" → subjects={{"biopic": 0.6, "music_performance": 0.4}}

CRITICAL — Reference-film detection (3 cases):

  Case A — Pure film title only (no "wie", no "aber"):
    The query IS a film title and nothing else. Set similar_to_title and
    leave emotions/themes/subjects empty — the engine will use the reference
    film's stored DNA directly.
    Examples:
      "Fight Club"     → similar_to_title="Fight Club",   emotions={{}}, themes={{}}
      "Amélie"         → similar_to_title="Amélie",       emotions={{}}, themes={{}}
      "Die Hard"       → similar_to_title="Die Hard",     emotions={{}}, themes={{}}
      "Im Auftrag des Teufels" → similar_to_title="The Devil's Advocate", emotions={{}}, themes={{}}

  Case B — "wie X" / "like X" (similar, no modifier):
    User wants films similar to X. Same handling as Case A — let the
    engine use the reference's DNA.
    Examples:
      "Filme wie Inception"  → similar_to_title="Inception", emotions={{}}, themes={{}}
      "like John Wick"        → similar_to_title="John Wick", emotions={{}}, themes={{}}

  Case C — "wie X aber Y" (similar to X with modifier Y):
    Reference + transformation. emotions/themes/subjects you output must
    reflect ONLY the MODIFIER Y, NOT the reference film's DNA. The engine
    blends 60% reference DNA + 40% your modifier signal.

    CRITICAL: similar_to_title MUST be set whenever the user names a film,
    franchise, or iconic IP as the reference — even if the modifier is
    vague ("realistisch", "moderner", "anders"). NEVER set it to null
    when a film/franchise name is mentioned in the query.

    Examples:
      "Filme wie Amélie aber mit mehr Action" → similar_to_title="Amélie",
        emotions={{excitement: 0.5, anticipation: 0.5}}, themes={{Action: 0.7, Adventure: 0.3}}
        (do NOT include joy/wonder/Amélie tags — they come from the reference)
      "John Wick aber lustiger" → similar_to_title="John Wick",
        emotions={{joy: 0.5, amusement: 0.5}}, themes={{Comedy: 1.0}}
      "Inception aber emotional" → similar_to_title="Inception",
        emotions={{grief: 0.4, tenderness: 0.4, melancholy: 0.2}}, themes={{}}
      "Filme wie Star Wars aber realistisch" → similar_to_title="Star Wars",
        emotions={{}}, themes={{}}, mood={{gritty: 0.6, dark: 0.4}}
        (iconic franchises ALWAYS resolve — Star Wars, Marvel, Harry Potter,
         James Bond, Star Trek, Lord of the Rings, etc.)
      "Marvel-Style aber kein Marvel" → similar_to_title=null (modifier IS the title)
      "Wie Pretty Woman aber moderner" → similar_to_title="Pretty Woman", ...

  Case D — Topic/subject/mood query (NO reference film):
    Set similar_to_title=null and fill emotions/themes/subjects normally.
    Examples: "Mafiafilme", "düstere Rachegeschichte", "feel-good Sci-Fi",
              "Action mit weiblicher Hauptrolle".

    Purpose/motivation queries:
      "Filme zum Business und Startup motivieren" → similar_to_title=null,
        subjects={{biopic: 0.6}}, themes={{ambition: 0.4, underdog_triumph: 0.4,
        corporate_world: 0.5}}, emotions={{inspiring: 0.5, anticipation: 0.4,
        excitement: 0.3}}, mood={{epic: 0.3, dialogue_driven: 0.5}}
        (films like Social Network, The Founder, Steve Jobs, Moneyball,
         Wolf of Wall Street, Pirates of Silicon Valley)
      "Filme zum Mut machen vor schwieren Entscheidungen" → underdog_triumph,
        hero_journey, redemption themes; emotions={{inspiring, cathartic}}
      "Filme zum Mitgrooven mit Musik" → subjects={{music_performance: 0.7}},
        mood={{light, energetic}}, genres={{Music: 0.8}}

Additional fields:
  "translated_query": "<English translation of the user's query>"
                      ALWAYS provide a fluent English translation. If the user wrote
                      English, copy it verbatim. This is used for semantic search.
  "avoid_emotions": [tag, ...]
  "avoid_themes":   [tag, ...]   // plot_themes / mood / pacing / genre tags to AVOID
                                 // (e.g. "ohne Romanze" → ["forbidden_love","love_triangle"];
                                 //  "ohne Comedy" → ["Comedy"])
  "avoid_content":  [tag, ...]   // content features to avoid: firearms, bladed_weapons,
                                 // physical_combat, explosions, supernatural_combat,
                                 // vehicular_combat, graphic_violence, torture,
                                 // sexual_content, drug_use.
                                 // Trigger phrases:
                                 //  - "ohne Schusswaffen" / "no guns" → ["firearms"]
                                 //  - "ohne Waffen" / "no weapons" → ["firearms","bladed_weapons"]
                                 //  - "kein Kampf" / "no fighting" → ["firearms","bladed_weapons","physical_combat"]
                                 //  - "ohne Gewalt" / "no violence" → ["graphic_violence","torture"]
                                 //  - "kindgeeignet" / "for kids" → ["graphic_violence","torture","sexual_content","drug_use"]
                                 // Use [] (empty) if no avoidance phrase. Only canonical tags.
  "avoid_subjects": [tag, ...]   // subject categories to AVOID — only canonical subjects
                                 // (vampire, zombie, werewolf, ghost, alien_invasion,
                                 //  monster_creature, mafia, serial_killer, true_crime,
                                 //  martial_arts, espionage, sports, music_performance,
                                 //  prison_life, courtroom_legal, hospital_medical,
                                 //  military_ops, school_university, biopic,
                                 //  historical_event, musical, mockumentary,
                                 //  found_footage, anime).
                                 // Trigger phrases:
                                 //  - "ohne Aliens" / "no aliens" → ["alien_invasion"]
                                 //  - "ohne Zombies" → ["zombie"]
                                 //  - "ohne Vampire" → ["vampire"]
                                 //  - "kein Sport" → ["sports"]
                                 //  - "kein Musical" → ["musical"]
                                 //  - "kein Anime" → ["anime"]
                                 // Use [] when no avoidance applies.
  "similar_to_title": null | "Film Title in ENGLISH original"  (if user says "wie X" / "like X")
                     ALWAYS use the English/original-language title, never the German one.
                     Examples: "Im Auftrag des Teufels" → "The Devil's Advocate"
                              "Der Pate" → "The Godfather"
                              "Stirb langsam" → "Die Hard"
  "protagonist_gender": null | "male" | "female" | "ensemble" | "non_binary"
                       Set when the user explicitly demands a protagonist gender:
                        - "weibliche Hauptrolle", "starke Frau", "female lead" → "female"
                        - "männlicher Held", "male lead" → "male"
                        - "Ensemble-Cast", "Gruppe" → "ensemble"
                       Otherwise null. Do NOT infer from genre alone.
  "protagonist_age":   null | "child" | "teen" | "young_adult" | "adult" | "mature_adult" | "senior"
                       Set when the user explicitly demands a protagonist age group:
                        - "Kinderfilme", "kid hero", "Kind als Hauptfigur" → "child"
                        - "Teenie-Held", "high school protagonist" → "teen"
                        - "junger Held", "20-jähriger" → "young_adult"
                        - "älterer Held", "Senior-Action wie Expendables", "Rentner" → "senior"
                        - "reifer Held" → "mature_adult"
                       Otherwise null. Do NOT infer from genre alone.
  "color_palette":     {{"tag": weight, ...}}  (0-2 entries, only when query mentions a look)
                       Set when the user explicitly demands a visual style:
                        - "neon-noir", "cyberpunk look" → {{"neon_noir": 1.0}}
                        - "warme Farben", "Sonnenuntergangs-Drama" → {{"warm_palette": 1.0}}
                        - "kühl/blau", "cold blue look" → {{"cold_palette": 1.0}}
                        - "Schwarz-Weiß Klassiker" → {{"monochrome_bw": 1.0}}
                       Otherwise empty {{}}.
  "year_min": null | number   (4-digit year, inclusive)
  "year_max": null | number   (4-digit year, inclusive)
                  Set ONLY when the user means the film's RELEASE year (when
                  it was made/produced). Examples:
                   - "80er Filme" / "1980s films" → year_min=1980, year_max=1989
                   - "90er Liebeskomödie" → year_min=1990, year_max=1999
                   - "neue Filme" / "recent" → year_min=2020 (no max)
                   - "Klassiker" / "classics" → year_max=1980 (no min)

                  CRITICAL — do NOT set year_min/year_max when the user means
                  the STORY SETTING (when the plot takes place). Those go
                  into settings/themes instead:
                   - "Handlung spielt in den 1920ern" / "set in the 1920s"
                     → year_min=null, year_max=null,
                       setting/themes: period_20th_century, mood: noir
                   - "Mafiafilme im Chicago der 30er" → year filter null;
                     subjects: mafia; setting: period_20th_century
                   - "Cowboys im Wilden Westen" → year filter null;
                     setting: frontier_period_western (or similar tag).
                  Trigger phrases that indicate SETTING (no year filter):
                  "spielt in", "Handlung in", "set in", "im X der Y", "im
                  Jahr/Jahrhundert".
                  Trigger phrases that indicate RELEASE YEAR (year filter):
                  "Filme aus", "Filme von", "von X", "1990s films", "X-er
                  Klassiker" (when X is the decade).
                  Otherwise null/null.
"""


def build_anchored_query_prompt(query: str, ref_title: str, ref_year: Optional[int],
                                 ref_dna: Dict[str, Any]) -> str:
    """Prompt for Variant Z (LLM-with-anchor): the server has resolved the
    reference film and is passing its CANONICAL stored DNA to the LLM. The LLM
    sees the anchor and produces the FINAL adjusted DNA in one shot — no
    server-side blending needed.

    Used only for "wie X aber Y" queries (similar_to_title resolved AND
    has_modifier). Pure "wie X" queries don't need this — they use the stored
    DNA directly.
    """
    def _fmt(d):
        if not d:
            return "{}"
        items = sorted((d or {}).items(), key=lambda kv: -kv[1])
        return "{" + ", ".join(f'"{k}": {v:.2f}' for k, v in items) + "}"

    year_str = f" ({ref_year})" if ref_year else ""
    emo_dna = ref_dna.get("emotion_dna", {}) or {}
    th_dna  = ref_dna.get("theme_dna", {}) or {}

    return f"""The user query is a REFERENCE-PLUS-MODIFIER request:
"{query}"

The reference film {ref_title!r}{year_str} has the following canonical DNA
(extracted from our database). Treat this as ground truth — do NOT invent
different values for the reference:

  emotions:           {_fmt(emo_dna)}
  themes_and_genres:  {_fmt(th_dna)}
  setting:            {_fmt(ref_dna.get('setting'))}
  archetype:          {ref_dna.get('archetype')!r}
  mood:               {_fmt(ref_dna.get('mood'))}
  pacing:             {_fmt(ref_dna.get('pacing'))}
  subjects:           {_fmt(ref_dna.get('subjects'))}
  content_features:   {_fmt(ref_dna.get('content_features'))}
  color_palette:      {_fmt(ref_dna.get('color_palette'))}
  protagonist_gender: {ref_dna.get('protagonist_gender')!r}
  protagonist_age:    {ref_dna.get('protagonist_age')!r}

Now APPLY the user's modifier to this DNA and output the FINAL adjusted
genome — every bucket filled with the adjusted values. The reader of your
output will use the values DIRECTLY (no further server-side blending).

Guidelines for common modifiers:
  "aber lustiger"        → raise genres.Comedy substantially (≥ 0.3); raise
                           emotions.joy + emotions.amusement; lower
                           emotions.rage/grief; mood.light replaces dark;
                           keep pacing.action_packed if action element remains.
  "aber emotionaler"     → raise emotions.grief/tenderness/melancholy; lower
                           cathartic; mood softer (atmospheric > gritty).
  "aber düsterer"        → mood.dark stronger, raise dread/horror, deeper noir,
                           lower joy/comforting.
  "aber moderner"        → setting.urban_modern; raise present-day tags.
  "aber im 80s setting"  → setting.period_20th_century if available; do NOT
                           set year_min/year_max (those are release-year, not
                           story-era).
  "mit weiblicher Hauptrolle" → protagonist_gender="female"; most other DNA
                                preserved from reference.
  "ohne Schusswaffen"    → fill avoid_content with ["firearms"]; keep theme.
  "länger/kürzer"        → no DNA change; the engine handles runtime filter.

Output schema is the SAME as the regular DNA extraction (emotions, wirkung,
themes, genres, setting, archetype, mood, pacing, content_features, subjects,
color_palette, protagonist_gender, protagonist_age, plus avoid_emotions,
avoid_themes, avoid_content, translated_query, year_min, year_max).

Set similar_to_title=null in your response — the server already knows the
reference. Set translated_query to a fluent English version of the user query.

Return strict JSON only."""


def parse_query_dna(raw: Dict[str, Any], query: str, ont: Dict[str, Any],
                    content_features_tags: Optional[set] = None) -> Dict[str, Any]:
    """Canonical post-processing of LLM query output.

    Single source of truth (audit F-006). Extracts/validates all metadata fields
    the engine needs: avoid_*, similar_to_title, protagonist_gender, year_min/max,
    translated_query.
    """
    if content_features_tags is None:
        content_features_tags = set(ont.get("content_features", []))
    dna = normalize_dna(raw, ont)
    dna["avoid_emotions"] = [t for t in (raw.get("avoid_emotions") or []) if isinstance(t, str)]
    dna["avoid_themes"] = [t for t in (raw.get("avoid_themes") or []) if isinstance(t, str)]
    dna["avoid_content"] = [t for t in (raw.get("avoid_content") or [])
                             if isinstance(t, str) and t in content_features_tags]
    # avoid_subjects: validated against canonical subjects vocabulary
    subj_tags = set(ont.get("subjects", []))
    dna["avoid_subjects"] = [t for t in (raw.get("avoid_subjects") or [])
                              if isinstance(t, str) and t in subj_tags]
    dna["similar_to_title"] = raw.get("similar_to_title")
    dna["translated_query"] = raw.get("translated_query") or query
    pg = (raw.get("protagonist_gender") or "").lower() or None
    dna["protagonist_gender"] = pg if pg in {"male", "female", "ensemble", "non_binary"} else None
    pa = (raw.get("protagonist_age") or "").lower().strip() or None
    age_valid = set(ont.get("protagonist_age", []))
    dna["protagonist_age"] = pa if pa in age_valid else None
    ymin, ymax = raw.get("year_min"), raw.get("year_max")
    dna["year_min"] = int(ymin) if isinstance(ymin, (int, float)) and 1900 <= int(ymin) <= 2100 else None
    dna["year_max"] = int(ymax) if isinstance(ymax, (int, float)) and 1900 <= int(ymax) <= 2100 else None
    return dna


def build_user_prompt(film: Dict[str, Any]) -> str:
    title = film.get("title") or film.get("original_title") or "?"
    year = film.get("year") or (film.get("release_date", "")[:4] or "?")
    overview = (film.get("overview") or "").strip()
    keywords = film.get("keywords") or []
    genres = film.get("genres") or []
    director = film.get("director") or ""

    return f"""title: {title!r}
year: {year}
tmdb_genres: {json.dumps(genres)}
director: {director!r}
overview: {overview!r}
keywords: {json.dumps(keywords[:15])}

Extract the DNA. Return strict JSON, no markdown."""


def normalize_l1(d: Dict[str, float]) -> Dict[str, float]:
    if not isinstance(d, dict) or not d:
        return {}
    s = sum(float(v) for v in d.values() if isinstance(v, (int, float)) and v > 0)
    if s <= 0:
        return {}
    return {k: float(v) / s for k, v in d.items()
            if isinstance(v, (int, float)) and v > 0}


_SYNONYM_DECAY_CACHED: Optional[float] = None


def _synonym_decay() -> float:
    """Read decay factor from config/engine_params.yaml; cached.

    Decoupled from search_v3._ep to avoid import cycle (extract_dna_v3 is
    imported by api_v3 which imports search_v3).
    """
    global _SYNONYM_DECAY_CACHED
    if _SYNONYM_DECAY_CACHED is not None:
        return _SYNONYM_DECAY_CACHED
    try:
        import yaml
        cfg = yaml.safe_load(open(ROOT / "config" / "engine_params.yaml")) or {}
        _SYNONYM_DECAY_CACHED = float(cfg.get("synonym", {}).get("decay", 0.7))
    except Exception:
        _SYNONYM_DECAY_CACHED = 0.7
    return _SYNONYM_DECAY_CACHED


def filter_to_canonical(d: Dict[str, float], allowed: List[str],
                        synonyms: Dict[str, List[str]]) -> Dict[str, float]:
    """Keep only canonical tags. Map synonyms to canonical heads."""
    if not isinstance(d, dict):
        return {}
    syn_to_canonical = {}
    for canon, syns in synonyms.items():
        if canon in allowed:
            for s in syns:
                syn_to_canonical[s.lower()] = canon
    decay = _synonym_decay()
    out: Dict[str, float] = {}
    for k, v in d.items():
        if not isinstance(v, (int, float)) or v <= 0:
            continue
        kk = k.strip()
        if kk in allowed:
            out[kk] = out.get(kk, 0.0) + float(v)
        else:
            mapped = syn_to_canonical.get(kk.lower())
            if mapped and mapped in allowed:
                out[mapped] = out.get(mapped, 0.0) + float(v) * decay
    return out


_SCHEMA_VERSION_CACHED: Optional[int] = None


def _engine_schema_version() -> int:
    """Read schema.version from engine_params.yaml; cached. Default 1 (legacy)."""
    global _SCHEMA_VERSION_CACHED
    if _SCHEMA_VERSION_CACHED is not None:
        return _SCHEMA_VERSION_CACHED
    try:
        import yaml
        cfg = yaml.safe_load(open(ROOT / "config" / "engine_params.yaml")) or {}
        _SCHEMA_VERSION_CACHED = int(cfg.get("schema", {}).get("version", 1))
    except Exception:
        _SCHEMA_VERSION_CACHED = 1
    return _SCHEMA_VERSION_CACHED


def normalize_dna(raw: Dict[str, Any], ont: Dict[str, Any]) -> Dict[str, Any]:
    syns = ont["synonyms"]
    emo = filter_to_canonical(raw.get("emotions", {}), ont["emotions"], syns)
    wir = filter_to_canonical(raw.get("wirkung", {}), ont["wirkung"], syns)
    schema = _engine_schema_version()
    if schema >= 2:
        # F-016 fix: emotions and wirkung normalized SEPARATELY.
        # Two semantic axes (protagonist-feeling vs viewer-impact) → two
        # independent L1 budgets. Joint dict has total L1 = 2.
        emotion_sparse = {**normalize_l1(emo), **normalize_l1(wir)}
    else:
        # v1 legacy: jointly L1-normalized (total L1 = 1, the two axes compete).
        emotion_sparse = normalize_l1({**emo, **wir})

    # theme_sparse = themes + genres, jointly L1-normalized
    th = filter_to_canonical(raw.get("themes", {}), ont["plot_themes"], syns)
    gn = filter_to_canonical(raw.get("genres", {}), ont["genres"], syns)
    theme_sparse = normalize_l1({**th, **gn})

    setting = normalize_l1(filter_to_canonical(raw.get("setting", {}), ont["settings"], syns))
    mood = normalize_l1(filter_to_canonical(raw.get("mood", {}), ont["moods"], syns))
    pacing = normalize_l1(filter_to_canonical(raw.get("pacing", {}), ont["pacing"], syns))
    content_features = normalize_l1(filter_to_canonical(
        raw.get("content_features", {}), ont["content_features"], syns))
    subjects = normalize_l1(filter_to_canonical(
        raw.get("subjects", {}), ont["subjects"], syns))

    archetype = raw.get("archetype")
    if archetype not in ont["archetypes"]:
        archetype = None

    gender = (raw.get("protagonist_gender") or "").lower()
    if gender not in {"male", "female", "ensemble", "non_binary"}:
        gender = None

    color_palette = normalize_l1(filter_to_canonical(
        raw.get("color_palette", {}), ont.get("color_palette", []), syns))

    age_raw = (raw.get("protagonist_age") or "").lower().strip() or None
    age_valid = set(ont.get("protagonist_age", []))
    protagonist_age = age_raw if age_raw in age_valid else None

    return {
        "emotion_sparse": emotion_sparse,    # L1=1, dim=30
        "theme_sparse": theme_sparse,        # L1=1 (plot_themes+genres jointly)
        "setting": setting,                   # part of theme_sparse vector at indices 53-67
        "archetype": archetype,               # payload, single value
        "mood": mood,                         # part of theme_sparse vector at indices 68-79
        "pacing": pacing,                     # part of theme_sparse vector at indices 80-87
        "subjects": subjects,                 # part of theme_sparse vector at indices 88+ (extension)
        "content_features": content_features, # payload, NOT in any sparse vector
        "protagonist_gender": gender,         # payload
        "color_palette": color_palette,       # payload, weighted dict (L1=1), additive bucket
        "protagonist_age": protagonist_age,   # payload, single string value
    }


_session = None
_lock = threading.Lock()


def get_session() -> requests.Session:
    global _session
    with _lock:
        if _session is None:
            _session = requests.Session()
        return _session


def call_openai(system: str, user: str, max_retries: int = 6) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    is_new = _is_new_model(OPENAI_MODEL)
    payload: Dict[str, Any] = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        ("max_completion_tokens" if is_new else "max_tokens"): 1500,
        "response_format": {"type": "json_object"},
    }
    if not is_new:
        payload["temperature"] = 0.1
    last_err = "unknown"
    text = ""
    for attempt in range(max_retries):
        try:
            r = get_session().post(OPENAI_URL, headers=headers, json=payload, timeout=120)
            # Distinguish insufficient_quota from rate_limit (both are HTTP 429)
            if r.status_code == 429:
                try:
                    err = r.json().get("error", {})
                    err_type = err.get("type", "")
                    err_code = err.get("code", "") or ""
                except Exception:
                    err_type, err_code = "", ""
                if err_type == "insufficient_quota" or "quota" in err_code:
                    raise QuotaExhausted(
                        f"OpenAI quota exhausted (type={err_type}, code={err_code}) — top up account, retrying is futile."
                    )
                wait = int(r.headers.get("Retry-After", "0")) or (2 ** attempt + 3)
                last_err = f"429 rate-limit ({err_type or 'transient'}), wait {wait}s (attempt {attempt+1}/{max_retries})"
                time.sleep(min(wait, 60))
                continue
            if r.status_code in (500, 502, 503, 504):
                last_err = f"server {r.status_code}"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            return json.loads(text)
        except QuotaExhausted:
            raise
        except json.JSONDecodeError as e:
            last_err = f"JSON decode: {e} -- text was: {text[:200]}"
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            last_err = f"request: {e}"
            time.sleep(2 ** attempt)
        except Exception as e:
            last_err = f"unexpected: {type(e).__name__}: {e}"
            time.sleep(1 + attempt)
    raise RuntimeError(f"openai failed after {max_retries} retries: {last_err}")


_LOCAL_CALL = None  # set by main() when --local-llm is passed


def call_local(system: str, user: str, max_retries: int = 3) -> Dict[str, Any]:
    """Local Qwen (GGUF) drop-in for call_openai. Returns parsed JSON dict."""
    from scripts.llm_local import chat_complete
    last_err = "unknown"
    for attempt in range(max_retries):
        try:
            text = chat_complete(system, user, max_tokens=1500, temperature=0.1)
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_err = f"JSON decode: {e} -- text was: {text[:200] if 'text' in dir() else '<none>'}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5)
    raise RuntimeError(f"local LLM failed after {max_retries} retries: {last_err}")


def extract_one(film: Dict[str, Any], system: str, ont: Dict[str, Any],
                caller=None) -> Dict[str, Any]:
    """Run LLM extraction on one film record.

    Args:
        film: dict with at least tmdb_id, title, overview, genres, keywords
        system: system prompt (build via build_system_prompt(ont))
        ont: ontology dict (load via load_ontology())
        caller: function(system, user) -> dict.  Defaults to `_LOCAL_CALL or call_openai`.
                Pass explicitly when called from concurrent code (api_v3 admin endpoint)
                to avoid relying on the module-level _LOCAL_CALL global.
    """
    user = build_user_prompt(film)
    if caller is None:
        caller = _LOCAL_CALL or call_openai
    raw = caller(system, user)
    dna = normalize_dna(raw, ont)
    return {
        "tmdb_id": film["tmdb_id"],
        "title": film.get("title"),
        "year": film.get("year"),
        "dna_v3": dna,
        "raw_llm": raw,  # keep raw for debugging
    }


def main():
    global _LOCAL_CALL
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="run on 5 hand-picked test films")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--out", type=str, default=str(OUT))
    ap.add_argument("--source", type=str, default=str(SOURCE),
                    help="path to film JSON list (default: movies_export.json)")
    ap.add_argument("--local-llm", action="store_true",
                    help="use local Qwen GGUF via llama-cpp instead of OpenAI")
    ap.add_argument("--llm-size", default="4b", choices=["2b", "4b"],
                    help="local LLM size when --local-llm is set")
    args = ap.parse_args()

    load_env()
    ont = load_ontology()
    system = build_system_prompt(ont)
    print(f"System prompt: {len(system)} chars (~{len(system)//4} tokens)")

    if args.local_llm:
        os.environ["LOCAL_LLM_SIZE"] = args.llm_size
        os.environ.setdefault("LOCAL_LLM_N_GPU_LAYERS", "999")
        os.environ.setdefault("LOCAL_LLM_CTX", "4096")
        _LOCAL_CALL = call_local
        # Pre-warm the model so we fail fast on missing GGUF / OOM
        from scripts.llm_local import get_llm
        get_llm()
        if args.workers > 1:
            print(f"WARN: --local-llm forces single-thread; ignoring --workers {args.workers}")
            args.workers = 1
        print(f"Mode: LOCAL Qwen-{args.llm_size}, workers=1")
    else:
        print(f"Mode: OpenAI ({OPENAI_MODEL}), workers={args.workers}")

    movies = json.load(open(args.source))
    by_id = {m["tmdb_id"]: m for m in movies}

    if args.pilot:
        # John Wick, Amélie, Devil's Advocate, Shawshank, Get Out
        pilot_ids = [245891, 194, 1813, 278, 419430]
        targets = [by_id[i] for i in pilot_ids if i in by_id]
        out_path = ROOT / "data" / "movies_dna_v3.pilot.jsonl"
    else:
        targets = list(movies)
        if args.limit:
            targets = targets[: args.limit]
        out_path = Path(args.out)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    done_ids = set()
    if args.resume and out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                done_ids.add(json.loads(line)["tmdb_id"])
            except Exception:
                pass

    todo = [m for m in targets if m["tmdb_id"] not in done_ids and m.get("overview")]
    print(f"Total films: {len(targets)}  Already done: {len(done_ids)}  To extract: {len(todo)}")

    if not todo:
        print("Nothing to do.")
        return

    written = 0
    errors = 0
    quota_killed = False
    t0 = time.time()
    write_lock = threading.Lock()
    with open(out_path, "a") as f_out, open(ERR, "a") as f_err:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(extract_one, m, system, ont): m for m in todo}
            for fut in as_completed(futures):
                film = futures[fut]
                try:
                    rec = fut.result()
                    with write_lock:
                        f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        f_out.flush()
                    written += 1
                except QuotaExhausted as e:
                    quota_killed = True
                    print(f"\n!!! QUOTA EXHAUSTED — stopping immediately. Top up OpenAI account.\n!!! {e}", flush=True)
                    # Cancel all remaining futures
                    for f in futures:
                        f.cancel()
                    break
                except Exception as e:
                    errors += 1
                    with write_lock:
                        f_err.write(json.dumps({
                            "tmdb_id": film["tmdb_id"],
                            "title": film.get("title"),
                            "error": str(e),
                        }, ensure_ascii=False) + "\n")
                        f_err.flush()

                if (written + errors) % 25 == 0 or written + errors == len(todo):
                    elapsed = time.time() - t0
                    rate = (written + errors) / max(elapsed, 1e-3)
                    eta = (len(todo) - written - errors) / max(rate, 1e-3)
                    print(f"  [{written + errors}/{len(todo)}] ok={written} err={errors} "
                          f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    status = "QUOTA-KILLED" if quota_killed else "Done"
    print(f"\n{status}. Written: {written}  Errors: {errors}  Model: {OPENAI_MODEL}  Output: {out_path}", flush=True)


if __name__ == "__main__":
    main()
