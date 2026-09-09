"""Backfill normalized legal-identifier payload keys onto an existing collection.

Why this is needed
------------------
``legal_documents_v2`` was indexed before exact identifier search existed, so
its points carry no ``article_no`` / ``article_ref`` / ``case_no`` keys and the
collection has 7 payload indices instead of 10. Exact identifier search
therefore matches nothing against that data even though the retrieval code
supports it -- the query path is live but the index is empty.

Payload-only, by construction
-----------------------------
This rewrites **payload only**. It never touches a vector, never re-embeds, and
never creates or deletes a point. ``set_payload`` merges the supplied keys into
the existing payload rather than replacing it, so every field already on a
point survives untouched. That is what makes this safe to run against a live
collection and re-runnable without drift: deriving the same keys from the same
stored text twice produces the same result.

Reusing the indexing logic rather than restating it
---------------------------------------------------
Keys are derived by calling ``src.retrieval.identifiers.identifier_payload`` --
the same function ``DocumentIndexingService._to_qdrant_point`` calls at index
time. A backfill that computed keys its own way would be the worst possible
place for a second implementation: backfilled points and newly-indexed points
would land on different keys, and the split would be invisible until an exact
lookup silently missed half the corpus.

Most points will get nothing, and that is correct
-------------------------------------------------
Only chunks that actually contain an article or case number get keys. In a
statute corpus that is a minority of chunks -- headings and preambles carry
no article number. A low hit rate is the expected shape of the data, not a
failure; the script reports the split rather than judging it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.identifiers import identifier_payload  # noqa: E402
from src.vector_store.qdrant_manager import (  # noqa: E402
    IDENTIFIER_PAYLOAD_FIELDS,
    QdrantVectorStore,
)

log = logging.getLogger("backfill")

SCROLL_PAGE = 500


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", default="legal_documents_v2")
    parser.add_argument("--vector-size", type=int, default=1024)
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually write. Without it the script only reports what it would "
            "write, which is the right way to see the split before mutating a "
            "live collection."
        ),
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    # Going through QdrantVectorStore rather than a bare client is deliberate:
    # its _ensure_collection creates the payload indices, including the three
    # identifier ones, and is idempotent on an existing collection. That means
    # index creation uses the same code path production startup uses instead of
    # a hand-rolled copy that could drift from it.
    store = QdrantVectorStore(
        location=args.qdrant_url,
        collection_name=args.collection,
        vector_size=args.vector_size,
    )
    client = store.client

    before = client.get_collection(args.collection)
    log.info("collection %r: %s points, status=%s",
             args.collection, before.points_count, before.status)
    log.info("payload indices now present: %s",
             sorted(before.payload_schema.keys()))

    missing_indices = [
        field for field in IDENTIFIER_PAYLOAD_FIELDS
        if field not in before.payload_schema
    ]
    if missing_indices:
        log.warning("identifier indices still missing after ensure: %s",
                    missing_indices)
    else:
        log.info("all identifier indices present: %s",
                 list(IDENTIFIER_PAYLOAD_FIELDS))

    scanned = 0
    with_identifiers = 0
    without_identifiers = 0
    already_had = 0
    written = 0
    article_values = Counter()
    docs_with_articles = Counter()
    pending: list[tuple] = []

    offset = None
    while True:
        points, offset = client.scroll(
            args.collection,
            limit=SCROLL_PAGE,
            offset=offset,
            with_payload=True,
            with_vectors=False,  # never read or rewrite vectors
        )
        if not points:
            break

        for point in points:
            scanned += 1
            payload = point.payload or {}

            if any(payload.get(f) for f in IDENTIFIER_PAYLOAD_FIELDS):
                already_had += 1

            derived = identifier_payload(
                document_id=payload.get("document_id", ""),
                text=payload.get("text", "") or "",
                section=payload.get("section"),
                clause=payload.get("clause"),
            )

            if not derived:
                without_identifiers += 1
                continue

            with_identifiers += 1
            for number in derived.get("article_no", []):
                article_values[number] += 1
            if derived.get("article_no"):
                docs_with_articles[payload.get("document_id", "?")] += 1

            pending.append((point.id, derived))

        if offset is None:
            break

    log.info("scanned %d points", scanned)

    if args.apply:
        for point_id, derived in pending:
            client.set_payload(
                collection_name=args.collection,
                payload=derived,
                points=[point_id],
                wait=False,
            )
            written += 1
        # One synchronous write at the end flushes the queued ones.
        if pending:
            last_id, last_payload = pending[-1]
            client.set_payload(
                collection_name=args.collection,
                payload=last_payload,
                points=[last_id],
                wait=True,
            )
        log.info("WROTE payload to %d points", written)
    else:
        log.info("DRY RUN -- would write payload to %d points", len(pending))

    after = client.get_collection(args.collection)

    print()
    print("=" * 64)
    print("BACKFILL REPORT" + ("" if args.apply else "  (DRY RUN)"))
    print("=" * 64)
    print(f"  points scanned                 : {scanned}")
    print(f"  points WITH an identifier      : {with_identifiers}"
          f"  ({100.0*with_identifiers/max(scanned,1):.1f}%)")
    print(f"  points with NO identifier      : {without_identifiers}"
          f"  ({100.0*without_identifiers/max(scanned,1):.1f}%)")
    print(f"    (expected: headings, preambles and prose carry no article number)")
    print(f"  points that already had keys   : {already_had}")
    print(f"  distinct article numbers found : {len(article_values)}")
    print(f"  documents containing articles  : {len(docs_with_articles)}")
    print()
    print(f"  points_count before            : {before.points_count}")
    print(f"  points_count after             : {after.points_count}")
    print(f"  point count unchanged          : {before.points_count == after.points_count}")
    print(f"  collection status              : {after.status}")
    print()
    print("  payload indices after:")
    for field, schema in sorted(after.payload_schema.items()):
        marker = "  <-- new" if field in IDENTIFIER_PAYLOAD_FIELDS else ""
        print(f"    {field:24s} {schema.data_type:8s} points={schema.points}{marker}")

    if article_values:
        print()
        print("  most common article numbers:")
        for number, count in article_values.most_common(10):
            print(f"    article {number:>5s}  on {count} chunks")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
