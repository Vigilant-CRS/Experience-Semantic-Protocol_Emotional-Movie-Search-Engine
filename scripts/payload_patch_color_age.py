"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Direct payload-only update für Qdrant: liest die enrichten JSONL-Records
und schreibt NUR die neuen Felder `color_palette` + `protagonist_age` per
`set_payload` API in die bestehende Collection. Kein Reindex, keine
Vektor-Neuberechnung.

Usage:
  venv/bin/python3 scripts/payload_patch_color_age.py --dry-run
  venv/bin/python3 scripts/payload_patch_color_age.py --limit 100
  venv/bin/python3 scripts/payload_patch_color_age.py            # full run
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient

COLLECTION = "mindread_v3"
BATCH = 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=str(ROOT / "data" / "movies_dna_v3.jsonl"))
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = QdrantClient(url=args.qdrant, timeout=120)

    # Sanity: collection exists
    info = client.get_collection(COLLECTION)
    print(f"Collection {COLLECTION}: {info.points_count} points")

    # Load records that have at least one of the new fields populated
    candidates: List[tuple] = []
    with open(args.jsonl) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            dna = rec.get("dna_v3", {})
            cp = dna.get("color_palette")
            pa = dna.get("protagonist_age")
            if cp is None and pa is None:
                continue  # nothing to write
            candidates.append((rec["tmdb_id"], cp or {}, pa))

    print(f"JSONL records with color_palette or protagonist_age: {len(candidates)}")

    if args.limit:
        candidates = candidates[:args.limit]
        print(f"Limited to first {len(candidates)}")

    if args.dry_run:
        # Show distribution
        cp_set = sum(1 for _, cp, _ in candidates if cp)
        pa_set = sum(1 for _, _, pa in candidates if pa)
        print(f"  color_palette filled: {cp_set}")
        print(f"  protagonist_age filled: {pa_set}")
        # Sample first 5
        for tid, cp, pa in candidates[:5]:
            print(f"  tmdb={tid} cp={cp} pa={pa}")
        return

    written = 0
    t0 = time.time()
    for i in range(0, len(candidates), BATCH):
        batch = candidates[i:i + BATCH]
        # Group identical payloads to minimize calls
        for tid, cp, pa in batch:
            payload: Dict[str, Any] = {"color_palette": cp}
            if pa is not None:
                payload["protagonist_age"] = pa
            try:
                client.set_payload(
                    collection_name=COLLECTION,
                    payload=payload,
                    points=[tid],
                    wait=False,
                )
                written += 1
            except Exception as e:
                print(f"ERROR tid={tid}: {type(e).__name__}: {e}", file=sys.stderr)

        elapsed = time.time() - t0
        rate = written / max(elapsed, 1e-3)
        eta = (len(candidates) - written) / max(rate, 1e-3)
        print(f"  [{written}/{len(candidates)}] rate={rate:.0f}/s eta={eta:.0f}s",
              flush=True)

    # Final flush
    client.upsert(collection_name=COLLECTION, points=[], wait=True) if False else None
    print(f"\nDone. Wrote payload to {written} points in {time.time()-t0:.0f}s.")


if __name__ == "__main__":
    main()
