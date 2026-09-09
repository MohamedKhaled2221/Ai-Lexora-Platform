"""Bulk re-index of a document corpus into ``legal_documents_v2``.

One pass, three outstanding changes
----------------------------------
This exists because three separate pieces of work each required a full
re-index, and doing them separately would have meant re-encoding the corpus
three times:

* **ACL / tenancy** -- every point needs ``client_id``, ``matter_id`` and
  ``confidentiality_level`` in its payload, plus ``schema_version``. Points
  without them match no allowed-client set and are invisible to every query.
* **Sparse vectors** -- BGE-M3's lexical weights are now stored as a named
  sparse vector and searched natively. Qdrant fixes vector configuration at
  collection creation, so this cannot be backfilled in place.
* **Token-bounded chunks** -- M1 previously chunked by characters while BGE-M3
  truncates at 512 tokens, so 78% of Arabic chunks had their tails silently
  dropped from both vectors while remaining keyword-searchable. Fixing that
  changes chunk boundaries, so every chunk must be re-derived from source.

Not the normal ingestion path
-----------------------------
Real firm documents go through ``POST /documents/ingest`` with a per-document
ACL derived from the authenticated caller. This script is for bulk-loading a
corpus whose access policy is uniform and known in advance -- public statutes,
synthetic benchmark data -- and it takes that policy as an explicit argument
rather than inferring one. It refuses to run without it.

It still routes chunks through the real ``ChunkACL`` stamping and the real
``DocumentIndexingService``, so the trust boundary and the token-budget checks
are exercised rather than bypassed. Only the HTTP hop to M1 is skipped, which
M1's own API docstring recommends for in-process callers.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Only the repo root goes on the path. M1 and M3 both expose a top-level
# package called ``src``; putting ``m1/`` on sys.path as well makes M1's copy
# shadow M3's, and the failure is a confusing ModuleNotFoundError for
# ``src.schemas``. M1 is reached as ``m1.src.*`` instead.


INGESTIBLE_SUFFIXES = {
    ".pdf", ".docx", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
}

log = logging.getLogger("reindex")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Re-index a corpus into the v2 collection.",
    )
    parser.add_argument(
        "corpus",
        type=Path,
        help="Directory to walk for ingestible documents.",
    )
    parser.add_argument(
        "--client-id",
        required=True,
        help=(
            "Owning tenant for every document in this run. Use '_shared' for "
            "a cross-tenant corpus such as public statutes."
        ),
    )
    parser.add_argument(
        "--matter-id",
        default="_none",
        help="Owning matter, or '_none' for client-level documents.",
    )
    parser.add_argument(
        "--confidentiality-level",
        required=True,
        choices=["public", "internal", "privileged"],
        help="Classification applied to every document in this run.",
    )
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", default=None)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Substring; files whose path contains it are skipped. Repeatable. "
            "Use for ground-truth and reference text that is evaluation "
            "material rather than corpus content."
        ),
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help=(
            "Drop the collection first. Required when it predates sparse "
            "support, because Qdrant cannot add a sparse vector to an "
            "existing collection."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def purge_document(store, document_id: str) -> int:
    """Delete every existing point for one document. Returns how many.

    Called before re-indexing a document so the result is a replacement, not
    a merge with whatever boundaries the previous run produced.
    """
    from qdrant_client.http.models import (
        FieldCondition,
        Filter,
        FilterSelector,
        MatchValue,
    )

    selector = Filter(
        must=[
            FieldCondition(
                key="document_id",
                match=MatchValue(value=document_id),
            )
        ]
    )

    existing = store.client.count(
        collection_name=store.collection_name,
        count_filter=selector,
        exact=True,
    ).count

    if existing:
        store.client.delete(
            collection_name=store.collection_name,
            points_selector=FilterSelector(filter=selector),
            wait=True,
        )
        log.info("        purged %d stale point(s) for %s", existing, document_id)

    return existing


def discover(corpus: Path, exclude: list[str]) -> list[Path]:
    found = []
    for path in sorted(corpus.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in INGESTIBLE_SUFFIXES:
            continue
        if any(token in str(path) for token in exclude):
            continue
        found.append(path)
    return found


def main(argv=None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    from src.schemas.access_control import ChunkACL
    from src.vector_store.qdrant_manager import (
        DEFAULT_COLLECTION_NAME,
        PAYLOAD_SCHEMA_VERSION,
        SPARSE_VECTOR_NAME,
        QdrantVectorStore,
    )

    collection = args.collection or DEFAULT_COLLECTION_NAME

    acl = ChunkACL(
        client_id=args.client_id,
        matter_id=args.matter_id,
        confidentiality_level=args.confidentiality_level,
    )

    documents = discover(args.corpus, args.exclude)

    log.info("corpus         : %s", args.corpus)
    log.info("documents found: %d", len(documents))
    log.info("collection     : %s @ %s", collection, args.qdrant_url)
    log.info(
        "acl            : client_id=%s matter_id=%s confidentiality=%s",
        acl.client_id, acl.matter_id, acl.confidentiality_level,
    )

    if args.dry_run:
        for path in documents:
            log.info("  would ingest %s", path.relative_to(args.corpus))
        return 0

    if not documents:
        log.error("nothing to ingest; refusing to report an empty re-index as success")
        return 1

    # --- runtime -----------------------------------------------------------
    from qdrant_client import QdrantClient

    if args.recreate:
        probe = QdrantClient(url=args.qdrant_url)
        if collection in [c.name for c in probe.get_collections().collections]:
            log.warning("dropping existing collection %r", collection)
            probe.delete_collection(collection)
        probe.close()

    from src.embedding_service import EmbeddingService
    from src.indexing.ingestion_service import DocumentIngestionService
    from src.indexing.service import DocumentIndexingService

    log.info("loading BGE-M3 ...")
    embedding_service = EmbeddingService()

    store = QdrantVectorStore(
        location=args.qdrant_url,
        collection_name=collection,
        vector_size=1024,
    )

    if not store.sparse_enabled:
        log.error(
            "collection %r has no %r vector. Re-run with --recreate: Qdrant "
            "cannot add a sparse vector to an existing collection.",
            collection, SPARSE_VECTOR_NAME,
        )
        return 1

    indexing = DocumentIndexingService(
        embedding_service=embedding_service,
        vector_store=store,
    )

    # Imported by fully-qualified path: M1's ``src`` package would otherwise
    # be ambiguous with M3's.
    import importlib

    m1_pipeline = importlib.import_module("m1.src.pipeline")
    m1_config = importlib.import_module("m1.src.config")

    counts = Counter()
    total_chunks = 0
    failures: list[tuple[Path, str]] = []
    started = time.perf_counter()

    for number, path in enumerate(documents, start=1):
        log.info("[%d/%d] %s", number, len(documents), path.name)

        try:
            result = m1_pipeline.process_document(
                str(path), m1_config.PipelineConfig()
            )

            if not result.succeeded or not result.chunks:
                failures.append((path, "M1 produced no chunks"))
                counts["failed"] += 1
                continue

            # Remove the document's existing points before writing the new
            # ones. Point ids are derived from document_id + chunk_id, so
            # re-indexing overwrites matching ids -- but a chunking change
            # alters how many chunks a document produces, and any point whose
            # chunk_id no longer exists would survive as an orphan: stale
            # text, correctly ACL-stamped, indefinitely retrievable. Deleting
            # first makes a re-index a replacement rather than a merge.
            purge_document(store, result.document_id)

            stamped = DocumentIngestionService._stamp(result.chunks, acl)
            indexed = indexing.index_document(stamped)

            total_chunks += indexed.chunks_indexed
            counts["ok"] += 1
            log.info(
                "        -> %s  %d chunks",
                indexed.document_id, indexed.chunks_indexed,
            )

        except Exception as exc:  # noqa: BLE001 -- one bad file must not stop the run
            failures.append((path, f"{type(exc).__name__}: {exc}"))
            counts["failed"] += 1
            log.exception("        FAILED")

    elapsed = time.perf_counter() - started

    # --- verification ------------------------------------------------------
    client = QdrantClient(url=args.qdrant_url)
    info = client.get_collection(collection)

    log.info("=" * 66)
    log.info("documents ingested : %d", counts["ok"])
    log.info("documents failed   : %d", counts["failed"])
    log.info("chunks indexed     : %d", total_chunks)
    log.info("points in Qdrant   : %s", info.points_count)
    log.info("elapsed            : %.1fs", elapsed)
    log.info("schema_version     : %d", PAYLOAD_SCHEMA_VERSION)

    sparse_config = info.config.params.sparse_vectors or {}
    log.info("sparse vector      : %s", SPARSE_VECTOR_NAME in sparse_config)

    for name, schema in sorted(
        (info.payload_schema or {}).items()
    ):
        log.info("payload index      : %-22s %s", name, schema.data_type)

    if failures:
        log.warning("-" * 66)
        for path, reason in failures:
            log.warning("FAILED %s -- %s", path.name, reason)

    if info.points_count != total_chunks:
        log.warning(
            "points_count (%s) != chunks indexed (%d). Re-indexing the same "
            "document is idempotent by design (point ids are derived from "
            "document_id+chunk_id), so this is expected only if the same "
            "document appears twice in the corpus.",
            info.points_count, total_chunks,
        )

    client.close()

    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
