"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Detect films where the English `overview` field contains German text
(common-words + umlauts heuristic), pull fresh English overview from
TMDB, and patch Qdrant + JSONL.

Usage:
  venv/bin/python3 scripts/fix_de_in_en_overview.py --dry-run
  venv/bin/python3 scripts/fix_de_in_en_overview.py            # patch live
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parent.parent
COLLECTION = "mindread_v3"
TMDB = "https://api.themoviedb.org/3"

_DE_WORDS = re.compile(
    r'\b(der|die|das|und|ist|nicht|sich|wird|als|von|für|über|gegen|'
    r'zwischen|während|sein|sind|hat|haben|seine|ihrer|wegen|aber|auch|'
    r'noch|schon|kleine|mädchen|familie)\b', re.IGNORECASE)
_UMLAUT = re.compile(r'[äöüßÄÖÜ]')


def looks_german(text: str) -> bool:
    if not text:
        return False
    return bool(_DE_WORDS.search(text) and _UMLAUT.search(text))


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def fetch_overview(tmdb_id: int, key: str, lang: str = "en-US"):
    try:
        r = requests.get(f"{TMDB}/movie/{tmdb_id}",
                          params={"api_key": key, "language": lang},
                          timeout=10)
        if r.status_code == 200:
            return (r.json() or {}).get("overview") or None
    except Exception:
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    load_env()
    key = os.environ.get("TMDB_API_KEY")
    if not key:
        print("TMDB_API_KEY missing in .env", file=sys.stderr)
        sys.exit(2)

    client = QdrantClient(url=args.qdrant, timeout=60)

    suspects = []
    offset = None
    while True:
        res, offset = client.scroll(collection_name=COLLECTION, limit=512,
                                     with_payload=["tmdb_id", "title", "overview", "overview_de"],
                                     with_vectors=False, offset=offset)
        if not res:
            break
        for p in res:
            ov = p.payload.get("overview") or ""
            if looks_german(ov):
                suspects.append((p.payload["tmdb_id"], p.payload.get("title"), ov))
        if offset is None:
            break

    print(f"Found {len(suspects)} films with German text in English overview field.")
    if args.limit:
        suspects = suspects[:args.limit]
        print(f"  limited to first {len(suspects)}")

    if args.dry_run:
        for tid, t, ov in suspects[:10]:
            print(f"  {tid} {t!r}: {ov[:80]}...")
        return

    fixed, skipped, errors = 0, 0, 0
    t0 = time.time()
    for i, (tid, title, _) in enumerate(suspects, 1):
        en = fetch_overview(tid, key, "en-US")
        de = fetch_overview(tid, key, "de-DE")
        if not en:
            skipped += 1
            continue
        payload = {"overview": en[:500]}
        # Restore overview_de if we got one and it's not already populated
        if de:
            payload["overview_de"] = de[:500]
        try:
            client.set_payload(collection_name=COLLECTION, payload=payload,
                                points=[tid], wait=False)
            fixed += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  err {tid}: {type(e).__name__}: {e}")
        if i % 50 == 0:
            elapsed = time.time() - t0
            rate = i / max(elapsed, 1e-3)
            eta = (len(suspects) - i) / max(rate, 1e-3)
            print(f"  [{i}/{len(suspects)}] fixed={fixed} skip={skipped} err={errors} "
                  f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)
        time.sleep(0.04)  # TMDB ~40/s

    client.upsert(collection_name=COLLECTION, points=[], wait=True)
    print(f"\nDone. fixed={fixed} skipped={skipped} errors={errors} "
          f"elapsed={time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
