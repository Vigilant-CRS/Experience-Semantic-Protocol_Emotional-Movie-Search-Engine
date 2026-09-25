"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Enrich Qdrant V3 payload with TMDB watch_providers (per region).

Adds payload field:
  streaming_providers: list[str]   — provider names available in target region (default DE)
                                     e.g. ["Netflix", "Amazon Prime Video", "Magenta TV"]

Run:
  venv/bin/python3 scripts/enrich_providers_tmdb.py
  venv/bin/python3 scripts/enrich_providers_tmdb.py --region DE --type flatrate
"""
import argparse
import os
import sys
import time
import threading
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


def fetch_providers(tmdb_id: int, region: str = "DE",
                     types=("flatrate", "ads")):
    """Returns list of provider names for the region across the given access types."""
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_KEY}"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After","1")) or 1); continue
            if r.status_code == 404:
                return []
            r.raise_for_status()
            data = r.json().get("results", {}).get(region, {}) or {}
            providers = []
            for t in types:
                for p in data.get(t, []) or []:
                    name = p.get("provider_name")
                    if name and name not in providers:
                        providers.append(name)
            return providers
        except Exception:
            time.sleep(1 + attempt)
    return []


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="DE")
    ap.add_argument("--type", action="append", default=None,
                    help="flatrate (default) | ads | rent | buy. Repeatable.")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    types = tuple(args.type) if args.type else ("flatrate", "ads")
    ids = get_tmdb_ids()
    print(f"Films in collection: {len(ids)}")
    print(f"Region: {args.region}, types: {types}")

    written = 0; with_provider = 0; errors = 0
    write_lock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_providers, tid, args.region, types): tid for tid in ids}
        for fut in as_completed(futures):
            tid = futures[fut]
            try:
                providers = fut.result()
                with write_lock:
                    client.set_payload(COLLECTION,
                                        payload={"streaming_providers": providers},
                                        points=[tid], wait=False)
                written += 1
                if providers:
                    with_provider += 1
            except Exception:
                errors += 1
            done = written + errors
            if done % 200 == 0 or done == len(ids):
                elapsed = time.time() - t0
                rate = done / max(elapsed, 1e-3)
                eta = (len(ids) - done) / max(rate, 1e-3)
                print(f"  [{done}/{len(ids)}] ok={written} w/prov={with_provider} err={errors} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)
    print(f"\nDone. Films with at least one provider in {args.region}: {with_provider}/{written}")


if __name__ == "__main__":
    main()
