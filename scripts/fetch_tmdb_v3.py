"""
Copyright (c) 2026 Damir Dulovic. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Fetch top-N films from TMDB by popularity and save to data/movies_tmdb_v3.json.

Output schema is the same as movies_export.json so extract_dna_v3.py can pick it up.

Usage:
  venv/bin/python3 scripts/fetch_tmdb_v3.py --limit 20000
  venv/bin/python3 scripts/fetch_tmdb_v3.py --limit 5000 --out data/movies_top5k.json
"""
import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.extract_dna_v3 import load_env

load_env()
TMDB_KEY = os.environ.get("TMDB_API_KEY")
assert TMDB_KEY, "TMDB_API_KEY missing in .env"

session = requests.Session()
session.params = {"api_key": TMDB_KEY}


def discover_page(page: int, sort_by="popularity.desc", min_votes=50,
                  language="en-US"):
    """Get one page (20 films) of /discover/movie."""
    r = session.get("https://api.themoviedb.org/3/discover/movie",
                    params={"page": page, "sort_by": sort_by,
                            "vote_count.gte": min_votes,
                            "include_adult": "false",
                            "language": language},
                    timeout=15)
    if r.status_code == 429:
        time.sleep(2); return discover_page(page, sort_by, min_votes, language)
    if r.status_code != 200:
        return []
    return r.json().get("results", [])


def fetch_details(tmdb_id: int):
    """Get full details + keywords for a film."""
    for attempt in range(3):
        try:
            r = session.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                            params={"append_to_response": "keywords,credits",
                                    "language": "en-US"},
                            timeout=15)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "1")) or 1)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return None


def detail_to_record(d: Dict[str, Any]) -> Dict[str, Any]:
    """Map TMDB detail JSON → our movies_export.json schema."""
    if not d or not d.get("id"):
        return None
    keywords = []
    if d.get("keywords"):
        keywords = [k["name"] for k in (d["keywords"].get("keywords") or [])]
    credits = d.get("credits") or {}
    director = next((c["name"] for c in (credits.get("crew") or [])
                      if c.get("job") == "Director"), None)
    cast_top = [c["name"] for c in (credits.get("cast") or [])[:5]]
    year = None
    rd = d.get("release_date") or ""
    if rd and len(rd) >= 4:
        try:
            year = int(rd[:4])
        except Exception:
            pass
    return {
        "tmdb_id": d["id"],
        "imdb_id": d.get("imdb_id"),
        "title": d.get("title"),
        "original_title": d.get("original_title"),
        "year": year,
        "release_date": rd,
        "overview": d.get("overview"),
        "tagline": d.get("tagline"),
        "runtime": d.get("runtime"),
        "vote_count": d.get("vote_count"),
        "vote_average": d.get("vote_average"),
        "popularity": d.get("popularity"),
        "poster_path": d.get("poster_path"),
        "backdrop_path": d.get("backdrop_path"),
        "genres": [g["name"] for g in (d.get("genres") or [])],
        "production_companies": [c["name"] for c in (d.get("production_companies") or [])][:5],
        "production_countries": [c["iso_3166_1"] for c in (d.get("production_countries") or [])],
        "spoken_languages": [l.get("iso_639_1") for l in (d.get("spoken_languages") or [])],
        "keywords": keywords[:25],
        "director": director,
        "cast": cast_top,
        "adult": d.get("adult", False),
        "status": d.get("status"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20000)
    ap.add_argument("--min-votes", type=int, default=50)
    ap.add_argument("--out", default="data/movies_tmdb_v3.json")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--existing", default="movies_export.json",
                    help="merge with this existing file (skip duplicate tmdb_ids)")
    args = ap.parse_args()

    # Load existing IDs to skip
    existing_ids = set()
    existing_records: List[Dict[str, Any]] = []
    if args.existing and Path(args.existing).exists():
        existing_records = json.load(open(args.existing))
        existing_ids = {r["tmdb_id"] for r in existing_records if r.get("tmdb_id")}
        print(f"Existing: {len(existing_records)} films in {args.existing}")

    print(f"Discovering top-{args.limit} films from TMDB…")
    discovered_ids: List[int] = []
    page = 1
    t0 = time.time()
    # TMDB caps Discover at 500 pages × 20 = 10K results per sort.
    # To get 20K, we need to cycle through multiple sorts.
    sorts = ["popularity.desc", "vote_average.desc", "primary_release_date.desc",
              "revenue.desc"]
    seen = set()
    sort_idx = 0
    while len(discovered_ids) < args.limit:
        sort = sorts[sort_idx % len(sorts)]
        page_local = (page - 1) % 500 + 1
        if page_local == 1 and page > 1:
            sort_idx += 1
            sort = sorts[sort_idx % len(sorts)]
            print(f"  switching sort to: {sort}")
        results = discover_page(page_local, sort_by=sort, min_votes=args.min_votes)
        if not results:
            sort_idx += 1
            if sort_idx >= len(sorts):
                print(f"  exhausted all sorts at {len(discovered_ids)} ids")
                break
            page = 1
            continue
        for m in results:
            mid = m.get("id")
            if mid and mid not in seen:
                seen.add(mid)
                discovered_ids.append(mid)
        page += 1
        if len(discovered_ids) % 500 == 0 or page % 25 == 0:
            print(f"  page {page} sort={sort}: {len(discovered_ids)} unique ids "
                  f"(took {time.time()-t0:.1f}s)")
    discovered_ids = discovered_ids[:args.limit]

    # Filter out IDs we already have
    new_ids = [mid for mid in discovered_ids if mid not in existing_ids]
    print(f"\n  new IDs to fetch: {len(new_ids)}/{len(discovered_ids)} "
          f"({len(discovered_ids)-len(new_ids)} already in {args.existing})")

    if not new_ids:
        print("Nothing new to fetch.")
        return

    print(f"\nFetching details for {len(new_ids)} new films (workers={args.workers})…")
    new_records: List[Dict[str, Any]] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_details, mid): mid for mid in new_ids}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                d = fut.result()
                rec = detail_to_record(d) if d else None
                if rec and rec.get("overview"):  # only keep films with synopsis
                    new_records.append(rec)
            except Exception as e:
                pass
            if done % 200 == 0 or done == len(new_ids):
                rate = done / max(time.time()-t0, 1e-3)
                eta = (len(new_ids)-done) / max(rate, 1e-3)
                print(f"  [{done}/{len(new_ids)}] kept={len(new_records)} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s")

    # Merge + write
    merged = list(existing_records) + new_records
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(merged, f, indent=None)
    print(f"\nWritten {args.out}  total={len(merged)}  new={len(new_records)}  wall={time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
