"""
Copyright (c) 2026 Damir Dulovic. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Audit overview integrity by sampling against TMDB.

Usage:
  venv/bin/python3 scripts/audit_overviews.py --sample 200      # sample top-N
  venv/bin/python3 scripts/audit_overviews.py --sample 50 --threshold 0.4  # stricter
  venv/bin/python3 scripts/audit_overviews.py --fix 245891      # patch one id
  venv/bin/python3 scripts/audit_overviews.py --fix-all-suspect # fix all flagged
  venv/bin/python3 scripts/audit_overviews.py --hot 200         # audit top-200 by popularity

A "suspect" overview is one where the local string and the TMDB string
have a low character-trigram Jaccard similarity. Threshold 0.5 is
conservative — anything below is almost certainly wrong.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, Range

ROOT = Path(__file__).resolve().parent.parent
COLLECTION = "mindread_v3"
TMDB = "https://api.themoviedb.org/3"


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def jaccard_trigrams(a: str, b: str) -> float:
    """Character-trigram Jaccard. Robust to small wording differences."""
    def grams(s):
        s = "  " + (s or "").lower() + "  "
        return {s[i:i+3] for i in range(len(s) - 2)}
    A, B = grams(a), grams(b)
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def fetch_tmdb_overview(tmdb_id: int, api_key: str) -> Optional[str]:
    try:
        r = requests.get(f"{TMDB}/movie/{tmdb_id}",
                          params={"api_key": api_key, "language": "en-US"},
                          timeout=10)
        if r.status_code == 200:
            return (r.json() or {}).get("overview")
    except Exception:
        return None
    return None


def fetch_top_films(client: QdrantClient, n: int):
    """Pull top-N films by vote_count from Qdrant."""
    out = []
    offset = None
    while len(out) < n * 4:  # over-fetch and sort
        res, offset = client.scroll(
            collection_name=COLLECTION, limit=512,
            with_payload=["tmdb_id", "title", "overview", "vote_count", "popularity"],
            with_vectors=False, offset=offset,
        )
        if not res:
            break
        out.extend(res)
        if offset is None:
            break
    out.sort(key=lambda p: (p.payload.get("vote_count") or 0,
                            p.payload.get("popularity") or 0.0), reverse=True)
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200,
                    help="Audit top-N films by vote_count")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="Jaccard trigram threshold below which an overview is suspect")
    ap.add_argument("--fix", type=int, default=None,
                    help="Skip audit, patch one specific tmdb_id with fresh TMDB overview")
    ap.add_argument("--fix-all-suspect", action="store_true",
                    help="After audit, write fresh overview for every suspect film")
    ap.add_argument("--qdrant", default="http://localhost:6333")
    args = ap.parse_args()

    load_env()
    key = os.environ.get("TMDB_API_KEY")
    if not key:
        print("TMDB_API_KEY missing in .env", file=sys.stderr)
        sys.exit(2)

    client = QdrantClient(url=args.qdrant, timeout=60)

    if args.fix is not None:
        ov = fetch_tmdb_overview(args.fix, key)
        if not ov:
            print(f"TMDB returned no overview for {args.fix}")
            sys.exit(1)
        client.set_payload(collection_name=COLLECTION,
                           payload={"overview": ov[:500]},
                           points=[args.fix], wait=True)
        print(f"Patched tmdb_id={args.fix}\n  new overview: {ov[:160]}...")
        return

    print(f"Auditing top-{args.sample} films by vote_count against TMDB...")
    top = fetch_top_films(client, args.sample)
    print(f"  fetched {len(top)} candidates from Qdrant\n")

    suspect = []
    for i, p in enumerate(top, 1):
        pl = p.payload
        tid = pl["tmdb_id"]
        local = (pl.get("overview") or "").strip()
        remote = fetch_tmdb_overview(tid, key)
        if remote is None:
            continue
        sim = jaccard_trigrams(local, remote)
        if sim < args.threshold:
            suspect.append((tid, pl.get("title"), sim, local[:90], remote[:90]))
            print(f"  ⚠ {tid} {pl.get('title')!r} sim={sim:.2f}")
            print(f"      LOCAL : {local[:140]}")
            print(f"      TMDB  : {remote[:140]}")
        if i % 50 == 0:
            print(f"    [{i}/{len(top)}] suspect={len(suspect)}", flush=True)
        time.sleep(0.04)  # TMDB rate limit ~40/s

    print(f"\nDone. {len(suspect)} suspect overviews out of {len(top)} sampled "
          f"({len(suspect)/max(1,len(top))*100:.1f}%).")

    if args.fix_all_suspect and suspect:
        print("\nPatching all suspects...")
        for tid, title, _, _, _ in suspect:
            ov = fetch_tmdb_overview(tid, key)
            if ov:
                client.set_payload(collection_name=COLLECTION,
                                   payload={"overview": ov[:500]},
                                   points=[tid], wait=False)
                print(f"  patched {tid} {title!r}")
            time.sleep(0.04)
        client.upsert(collection_name=COLLECTION, points=[], wait=True)
        print(f"\nPatched {len(suspect)} payloads.")


if __name__ == "__main__":
    main()
