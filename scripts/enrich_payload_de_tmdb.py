"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Enrich Qdrant V3 payload with German title + overview from TMDB.

Adds payload fields:
  title_de:     str — German title (if TMDB has it)
  overview_de:  str — German overview (if TMDB has it)

The English versions stay in `title` and `overview` (used for embedding).
This script only touches the display layer.

Run: venv/bin/python3 scripts/enrich_payload_de_tmdb.py
"""
import argparse, os, sys, time, threading
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


def fetch_de(tmdb_id: int):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_KEY}&language=de-DE"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After","1")) or 1); continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            d = r.json()
            return {
                "title_de": d.get("title") or None,
                "overview_de": d.get("overview") or None,
                "tagline_de": d.get("tagline") or None,
            }
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
        for p in pts: ids.append(p.payload["tmdb_id"])
        if offset is None: break
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    ids = get_tmdb_ids()
    print(f"Films in collection: {len(ids)}")

    written = 0; with_de = 0; errors = 0
    write_lock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_de, tid): tid for tid in ids}
        for fut in as_completed(futures):
            tid = futures[fut]
            try:
                rec = fut.result() or {}
                # Only set fields that have content
                payload_patch = {k: v for k, v in rec.items() if v}
                if payload_patch:
                    with write_lock:
                        client.set_payload(COLLECTION, payload=payload_patch,
                                            points=[tid], wait=False)
                    written += 1
                    if rec.get("overview_de"):
                        with_de += 1
            except Exception:
                errors += 1
            done = written + errors
            if done % 200 == 0 or done == len(ids):
                elapsed = time.time() - t0
                rate = done / max(elapsed, 1e-3)
                eta = (len(ids) - done) / max(rate, 1e-3)
                print(f"  [{done}/{len(ids)}] ok={written} w/de_overview={with_de} err={errors} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)
    print(f"\nDone. Films with German overview: {with_de}/{written}  wall={time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
