"""
Copyright (c) 2026 Damir Dulovic. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Enrich Qdrant V3 payload with TMDB poster, vote_count, popularity, release_date.

Reads tmdb_ids from the mindread_v3 collection, fetches details from TMDB API,
calls set_payload to attach the missing fields. No vector recompute needed.

Run: venv/bin/python3 scripts/enrich_payload_tmdb.py
"""
import os, time, sys, json, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.extract_dna_v3 import load_env

load_env()
TMDB_KEY = os.environ.get("TMDB_API_KEY")
assert TMDB_KEY, "TMDB_API_KEY missing in .env"

COLLECTION = os.getenv("QDRANT_COLLECTION_V3", "mindread_v3")
client = QdrantClient(host="localhost", port=6333, timeout=120.0)
session = requests.Session()
lock = threading.Lock()

POSTER_FIELDS = ["poster_path", "backdrop_path", "vote_count", "vote_average",
                 "popularity", "release_date", "runtime", "tagline"]


def fetch_one(tmdb_id: int, max_retries=4):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_KEY}"
    for attempt in range(max_retries):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "1")) or 1
                time.sleep(min(wait, 10)); continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return None


def get_tmdb_ids():
    ids = []
    offset = None
    while True:
        pts, offset = client.scroll(COLLECTION, limit=1000, offset=offset,
                                     with_payload=["tmdb_id"], with_vectors=False)
        if not pts: break
        for p in pts:
            ids.append(p.payload["tmdb_id"])
        if offset is None: break
    return ids


def main():
    ids = get_tmdb_ids()
    print(f"Films in collection: {len(ids)}")
    written = 0; missing = 0; errors = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_one, tid): tid for tid in ids}
        for fut in as_completed(futures):
            tid = futures[fut]
            try:
                data = fut.result()
                if not data:
                    missing += 1; continue
                payload_patch = {k: data.get(k) for k in POSTER_FIELDS if data.get(k) is not None}
                if payload_patch:
                    client.set_payload(COLLECTION, payload=payload_patch, points=[tid], wait=False)
                    written += 1
            except Exception as e:
                errors += 1
            done = written + missing + errors
            if done % 100 == 0 or done == len(ids):
                elapsed = time.time() - t0
                rate = done / max(elapsed, 1e-3)
                eta = (len(ids) - done) / max(rate, 1e-3)
                print(f"  [{done}/{len(ids)}] ok={written} miss={missing} err={errors} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)
    print(f"\nDone. ok={written}  missing={missing}  errors={errors}  wall={time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
