import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchAny,
    MatchValue,
    Modifier,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
)

from src.schemas.access_control import (
    AccessScope,
    AccessScopeRequired,
)
logger = logging.getLogger(__name__)


PAYLOAD_SCHEMA_VERSION = 2
"""Version of the stored Qdrant payload shape.

v2 adds the access-control triple (client_id, matter_id,
confidentiality_level) and this marker. v1 points carry none of them, so under
fail-closed filtering they match no allowed-client set and are permanently
invisible -- correct, but it means v1 data is dead weight and a full re-index
is required rather than optional.

Deliberately *not* bumped to 3 when the sparse vector was added. The payload
shape is unchanged by sparse -- sparse lives in the vector configuration, not
the payload -- and v2 had not been indexed into anywhere when sparse landed,
so folding it into the same re-index costs nothing. See
:data:`SPARSE_VECTOR_NAME` for what that implies for anyone holding a v2
collection created before this change.
"""

DEFAULT_COLLECTION_NAME = "legal_documents_v2"
"""The v2 collection.

Renamed rather than migrated in place: every existing point would need the
three new keys backfilled, and older code never created payload indices on an
already-existing collection. Re-index into v2, cut over, then drop v1.
"""

SPARSE_VECTOR_NAME = "text_sparse"
"""Name of the named sparse vector holding BGE-M3 lexical weights.

Qdrant fixes a collection's vector configuration at creation time: sparse
vectors **cannot** be added to an existing collection (``update_collection``
rejects it with "Vector text_sparse does not exist in the collection"). A v2
collection created before this change therefore has no sparse vector, and
must be dropped and re-indexed. :meth:`QdrantVectorStore._detect_sparse_support`
detects that case at startup and says so, rather than letting it surface as a
failed upsert at the first ingest.
"""

DENSE_VECTOR_NAME = ""
"""The dense vector stays *unnamed* (Qdrant's default vector, whose name is
the empty string).

Naming it would have been tidier, but it would also have changed how every
existing point and every dense query is addressed, for no functional gain:
Qdrant is happy to serve an unnamed dense vector alongside named sparse ones,
and a dense query needs no ``using=`` argument. Keeping it unnamed means
``dense_search`` did not change at all when sparse arrived.
"""


def to_sparse_vector(
    weights: Optional[Dict[str, float]],
) -> Optional[SparseVector]:
    """
    Convert BGE-M3 lexical weights into Qdrant's sparse representation.

    M2 hands over ``{token_id_as_string: weight}`` because that is what
    survives JSON and Pydantic; Qdrant wants parallel integer-index and
    float-value lists. The conversion belongs here, at the storage boundary,
    so the M2 contract does not have to know Qdrant's wire format.

    Returns ``None`` for absent or empty weights. An empty ``SparseVector``
    is accepted by Qdrant but can never match anything, so storing one would
    add an index entry that only costs space.
    """

    if not weights:
        return None

    indices: List[int] = []
    values: List[float] = []

    for token_id, weight in weights.items():
        indices.append(int(token_id))
        values.append(float(weight))

    if not indices:
        return None

    return SparseVector(indices=indices, values=values)

UPSERT_BATCH_SIZE = 256
"""Points per upsert request.

Qdrant rejects a request body over 32 MiB. A point carries a 1024-float dense
vector, which is roughly 20 KB once serialized as JSON text, so a few thousand
points in one request is enough to cross the limit -- and a single document
now produces that many, because token-aware chunking splits a dense Arabic
statute into two to three times as many chunks as character-based chunking did.

That is how this surfaced: the two largest Arabic constitutions built 38 MB and
34 MB bodies and were refused outright with a 400, failing the whole document.
Batching keeps each request an order of magnitude clear of the ceiling and
makes upsert cost scale with corpus size rather than with the largest single
document.
"""

ACL_PAYLOAD_FIELDS = (
    "client_id",
    "matter_id",
    "confidentiality_level",
)
"""Access-control payload keys, indexed as KEYWORD so every ACL condition is a
flat exact match."""

LIFECYCLE_PAYLOAD_FIELDS = (
    "record_id",
    "validity_status",
)
VALID_LIFECYCLE_STATUSES = frozenset(
    {
        "current",
        "superseded",
        "review_required",
    }
)
"""M6 knowledge-record keys written by :mod:`src.indexing.index_sync`.

``record_id`` addresses every point belonging to one canonical record, so a
delete or re-sync is one filtered operation. ``validity_status`` carries M6's
``current`` / ``superseded`` / ``review_required``. Points indexed by the
document pipeline have neither key."""

IDENTIFIER_PAYLOAD_FIELDS = (
    "article_no",
    "article_ref",
    "case_no",
    "date_no",
    "date_ref",
    "money_no",
    "money_ref",
    "party_name",
)
"""Normalized legal-identifier keys, indexed as KEYWORD for *exact* matching.

These are the only fields in the collection that support equality rather than
similarity. Dense vectors and the ``text_sparse`` lexical weights are both
similarity signals -- neither can express "article 15, not article 51" -- so a
citation lookup had no way to be precise before these existed.

KEYWORD is correct rather than INTEGER even though ``article_no`` holds
digits: the values are lookup *tokens* produced by
``src.retrieval.identifiers``, they are multi-valued per point, and
``article_ref`` and ``case_no`` are genuinely alphanumeric. Keeping all of them
on one schema type means one matching rule to reason about.

The ``_no`` / ``_ref`` suffix pair is the same convention throughout: ``_no``
is the bare token ("article 15", "2026-05-30", "EGP:612500") and ``_ref`` is
that token scoped to one document. ``date_no`` and ``money_no`` read a little
oddly as English -- neither is a "number" -- but the payoff is that every
identifier field behaves identically, and a reader who has understood
``article_no`` has understood all seven.

KEYWORD rather than DATETIME for ``date_no`` specifically: the M2 contract
supplies *point* dates extracted from query text, never ranges, so equality is
the only predicate there is anything to answer with. A DATETIME index would
buy range queries that nothing upstream can currently ask for, at the cost of
the one uniform matching rule above. Revisit if and when M2 starts producing
date ranges.

Unlike the ACL fields, an unindexed identifier field degrades only the queries
that carry an identifier, and it degrades them to the previous behaviour
(similarity-only) rather than to something unsafe.
"""


class QdrantVectorStore:
    """
    Qdrant Vector Database Manager for M3 Retrieval Pipeline.
    """

    def __init__(
        self,
        location: str = ":memory:",
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int = 1024,
        distance: Distance = Distance.COSINE
    ):
        self.location = location
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.distance = distance

        self.sparse_enabled = False
        """Whether this collection can actually store and search sparse
        vectors. False against a collection created before sparse support
        existed -- see :meth:`_detect_sparse_support`."""

        self.client = QdrantClient(location=self.location)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """
        Create collection if it does not exist and setup payload indices.
        """
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            logger.info(f"Creating Qdrant collection '{self.collection_name}' with dim={self.vector_size}...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=self.distance
                ),
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams(
                        index=SparseIndexParams(),
                        # NOT Modifier.IDF. BGE-M3's lexical weights are
                        # already learned term weights; letting Qdrant apply
                        # its own IDF on top would weight rare terms twice.
                        modifier=Modifier.NONE,
                    )
                },
            )

        # Index creation runs on every startup, not only when the collection
        # is first created. It used to sit inside the branch above, which
        # meant an existing collection never received a newly-added index --
        # a new ACL field would then be filtered on unindexed, silently.
        # Qdrant treats re-creating an existing index as a no-op.
        self._create_payload_indices()

        self.sparse_enabled = self._detect_sparse_support()

    def _detect_sparse_support(self) -> bool:
        """
        Report whether this collection actually has the sparse vector.

        Qdrant fixes vector configuration at creation, so a collection made
        before sparse support cannot gain it. Upserting a sparse vector into
        such a collection fails outright ("Not existing vector name"), which
        would break ingestion at the first document rather than here.

        Unlike a missing access filter, a missing sparse vector is a
        *relevance* problem, not a security one: search still returns correct,
        correctly-scoped results, just without the keyword signal. So this
        degrades rather than raising -- but it says so at ERROR, because the
        fix (drop and re-index) is manual and the symptom otherwise is only
        "keyword matches seem worse than they used to".
        """
        try:
            info = self.client.get_collection(self.collection_name)
            configured = (
                getattr(info.config.params, "sparse_vectors", None)
                or {}
            )

        except Exception as exc:
            logger.warning(
                f"Could not read sparse configuration for "
                f"'{self.collection_name}': {exc}. Assuming no sparse "
                "support."
            )
            return False

        if SPARSE_VECTOR_NAME in configured:
            return True

        logger.error(
            f"Collection '{self.collection_name}' has no "
            f"'{SPARSE_VECTOR_NAME}' vector. It predates sparse support, and "
            "Qdrant cannot add a sparse vector to an existing collection. "
            "Sparse retrieval is disabled for this process; dense search and "
            "access filtering are unaffected. To enable it, drop the "
            "collection and re-index."
        )
        return False

    def _create_payload_indices(self) -> None:
        """
        Create payload index fields for high-performance metadata filtering.

        Idempotent, and safe to call against an existing collection.

        The ACL fields carry a stronger requirement than the metadata fields:
        every query filters on client_id and confidentiality_level, so an
        unindexed ACL field degrades every search rather than only the
        filtered ones.
        """
        payload_fields = [
            "document_type",
            "jurisdiction",
            "language",
            "document_id",
            *ACL_PAYLOAD_FIELDS,
            *IDENTIFIER_PAYLOAD_FIELDS,
            *LIFECYCLE_PAYLOAD_FIELDS,
        ]
        for field in payload_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                logger.warning(f"Failed to create index for {field}: {e}")

    def upsert_chunks(
        self,
        points: List[PointStruct],
        batch_size: int = UPSERT_BATCH_SIZE,
    ) -> None:
        """
        Insert or update points (embeddings + metadata payload) in Qdrant.

        Sent in batches because Qdrant refuses a request body over 32 MiB and a
        single large document can exceed that on its own -- see
        :data:`UPSERT_BATCH_SIZE`. Point ids are deterministic (derived from
        document_id + chunk_id), so a partially-applied batch sequence is
        re-runnable rather than corrupting: re-indexing the same document
        overwrites the same points.
        """
        if not points:
            return

        total = len(points)

        for start in range(0, total, max(batch_size, 1)):
            batch = points[start:start + max(batch_size, 1)]

            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )

            if total > batch_size:
                logger.debug(
                    "upserted %d-%d of %d points into %r",
                    start + 1, start + len(batch), total,
                    self.collection_name,
                )

        logger.info(f"Successfully upserted {total} points into '{self.collection_name}'.")

    @staticmethod
    def _record_filter(record_id: str) -> Filter:
        if not record_id or not str(record_id).strip():
            # A blank key would make the delete below match nothing at best;
            # refuse rather than guess what the caller meant.
            raise ValueError("record_id must not be empty")

        return Filter(
            must=[
                FieldCondition(
                    key="record_id",
                    match=MatchValue(value=str(record_id)),
                )
            ]
        )

    def delete_record_points(self, record_id: str) -> None:
        """
        Delete every point belonging to one M6 knowledge record.

        Scoped by ``record_id`` only, never by a caller-built filter, so this
        cannot be turned into a bulk delete. Idempotent: deleting a record
        with no points is a no-op.
        """
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=self._record_filter(record_id)
            ),
            wait=True,
        )

    def list_record_point_ids(self, record_id: str) -> List[str]:
        """Ids of every point belonging to one M6 knowledge record."""
        ids: List[str] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=self._record_filter(record_id),
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            ids.extend(str(point.id) for point in points)
            if offset is None:
                return ids

    def delete_point_ids(self, point_ids: List[str]) -> None:
        """Delete specific points by id. Used to drop obsolete record passages."""
        if not point_ids:
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.PointIdsList(points=list(point_ids)),
            wait=True,
        )

    def get_record_version(self, record_id: str) -> Optional[int]:
        """
        Return the ``record_version`` currently indexed for a record, or None
        when the record has no points. Used to ignore stale sync events.
        """
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=self._record_filter(record_id),
            limit=1,
            with_payload=["record_version"],
            with_vectors=False,
        )

        if not points:
            return None

        version = (points[0].payload or {}).get("record_version")
        return int(version) if version is not None else None

    def build_qdrant_filter(
        self,
        access: AccessScope,
        document_ids: Optional[
            List[str]
        ] = None,
        document_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        language: Optional[str] = None,
        extra_filters: Optional[
            Dict[str, Any]
        ] = None,
        validity_statuses: Optional[List[str]] = None,
        include_unversioned_points: bool = False,
    ) -> Filter:
        """
        Build the Qdrant filter for one query.

        ``access`` is the first parameter and has no default on purpose.
        This function used to return ``None`` when no conditions accumulated,
        which meant the default posture of every read path was *unfiltered*:
        forgetting a filter produced a silent full-collection search rather
        than an error. It now always returns a real ``Filter`` carrying at
        minimum the access conditions, so there is no longer a way to call it
        and receive something unfiltered.

        The relevance filters (document_ids, document_type, ...) are joined
        with the access conditions under ``must``, so they can only ever
        narrow the result set further. No caller-supplied value can widen
        what the access scope permits.
        """
        if access is None:
            raise AccessScopeRequired(
                "build_qdrant_filter requires an AccessScope. A retrieval "
                "path reached the vector store without one, which means the "
                "caller bypassed the intended construction; refusing rather "
                "than searching unfiltered."
            )

        if not isinstance(access, AccessScope):
            raise AccessScopeRequired(
                "access must be an AccessScope, not "
                f"{type(access).__name__}. Refusing to coerce an unvalidated "
                "value into an authorization decision."
            )

        must_conditions = [
            FieldCondition(
                key="client_id",
                match=MatchAny(
                    any=access.allowed_client_ids
                ),
            ),
            FieldCondition(
                key="confidentiality_level",
                match=MatchAny(
                    any=list(
                        access
                        .allowed_confidentiality_levels
                    )
                ),
            ),
        ]

        allowed_matter_ids = (
            access.allowed_matter_ids
        )

        if allowed_matter_ids is not None:
            must_conditions.append(
                FieldCondition(
                    key="matter_id",
                    match=MatchAny(
                        any=allowed_matter_ids
                    ),
                )
            )

        if document_ids:
            must_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(
                        any=document_ids
                    ),
                )
            )

        if document_type:
            must_conditions.append(
                FieldCondition(key="document_type", match=MatchValue(value=document_type))
            )
        if jurisdiction:
            must_conditions.append(
                FieldCondition(key="jurisdiction", match=MatchValue(value=jurisdiction))
            )
        if language:
            must_conditions.append(
                FieldCondition(key="language", match=MatchValue(value=language))
            )

        if extra_filters:
            colliding = (
                set(extra_filters)
                & set(ACL_PAYLOAD_FIELDS)
            )

            if colliding:
                # Such a condition could only narrow, never widen, since
                # everything here is ANDed. It is refused anyway: a caller
                # hand-setting an ACL key is either confused about where
                # authorization comes from or probing to find out, and both
                # are worth surfacing rather than quietly absorbing.
                raise AccessScopeRequired(
                    "extra_filters must not contain access-control fields "
                    f"({', '.join(sorted(colliding))}). Access is derived "
                    "from the authenticated caller, never from query "
                    "filters."
                )

            for k, v in extra_filters.items():
                if v is not None:
                    must_conditions.append(
                        FieldCondition(key=k, match=MatchValue(value=str(v)))
                    )

        if validity_statuses is not None:

            normalized_statuses = list(
                dict.fromkeys(
                    str(status)
                    .strip()
                    .lower()
                    for status
                    in validity_statuses
                    if str(status).strip()
                )
            )

            if not normalized_statuses:
                raise ValueError(
                    "validity_statuses must be None "
                    "or a non-empty list."
                )

            invalid_statuses = sorted(
                set(normalized_statuses)
                - VALID_LIFECYCLE_STATUSES
            )

            if invalid_statuses:
                raise ValueError(
                    "Unsupported validity_status "
                    "value(s): "
                    + ", ".join(
                        invalid_statuses
                    )
                )

            status_condition = FieldCondition(
                key="validity_status",
                match=MatchAny(
                    any=normalized_statuses
                ),
            )

            if include_unversioned_points:

                must_conditions.append(
                    Filter(
                        should=[
                            status_condition,
                            qmodels.IsEmptyCondition(
                                is_empty=(
                                    qmodels.PayloadField(
                                        key=(
                                            "validity_status"
                                        )
                                    )
                                )
                            ),
                        ]
                    )
                )

            else:
                must_conditions.append(
                    status_condition
                )

        # Always a real Filter: must_conditions can never be empty, because
        # the access conditions are unconditional.
        return Filter(must=must_conditions)

    def dense_search(
        self,
        query_vector: List[float],
        query_filter: Filter,
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Perform dense vector search under a mandatory payload filter.

        ``query_filter`` has no default. Together with build_qdrant_filter
        never returning None, that means no read path can reach Qdrant
        unfiltered -- including one added later by someone who has never read
        this file. A missing filter is a TypeError at the call site rather
        than a silent full-collection search at runtime.
        """
        self._require_filter(query_filter, "dense_search")

        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True
            )
            search_result = response.points
        else:
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True
            )

        results = []
        for res in search_result:
            payload = res.payload or {}
            results.append(
                self._project(
                    point_id=res.id,
                    payload=payload,
                    score=float(res.score),
                )
            )
        return results

    @staticmethod
    def _project(
        *,
        point_id: Any,
        payload: Dict[str, Any],
        score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Shape one stored point into the dict every read path returns.

        Single implementation on purpose. This was copied byte-for-byte in
        dense_search and get_all_chunks, and adding a third copy for sparse
        search is precisely how a read path ends up missing the ACL keys that
        the post-retrieval assertion checks against -- the search would work,
        the assertion would see None, and every query would fail (or worse, if
        the assertion were ever relaxed, would not).

        Absent keys stay absent rather than defaulting: a payload with no ACL
        must read as unverifiable, never as permitted.
        """

        projected = {
            "point_id": point_id,
            "document_id": payload.get("document_id", ""),
            "chunk_id": payload.get("chunk_id", str(point_id)),
            "text": payload.get("text", ""),
            "page": payload.get("page"),
            "section": payload.get("section"),
            "language": payload.get("language", "ar"),
            "document_type": payload.get("document_type"),
            "jurisdiction": payload.get("jurisdiction"),
            "client_id": payload.get("client_id"),
            "matter_id": payload.get("matter_id"),
            "confidentiality_level": payload.get(
                "confidentiality_level"
            ),
            # Identifier keys ride along on the candidate dict so a caller can
            # see *why* an exact-match candidate was selected. They are
            # dropped again when the M4 contract is built -- EvidenceItem is
            # unchanged by this feature.
            "article_no": payload.get("article_no"),
            "article_ref": payload.get("article_ref"),
            "case_no": payload.get("case_no"),
            "date_no": payload.get("date_no"),
            "date_ref": payload.get("date_ref"),
            "money_no": payload.get("money_no"),
            "money_ref": payload.get("money_ref"),
        }

        if score is not None:
            projected["score"] = score

        return projected

    def identifier_search(
        self,
        query_filter: Filter,
        article_numbers: Optional[List[str]] = None,
        article_refs: Optional[List[str]] = None,
        case_numbers: Optional[List[str]] = None,
        dates: Optional[List[str]] = None,
        date_refs: Optional[List[str]] = None,
        money_values: Optional[
            List[str]
        ] = None,

        money_refs: Optional[
            List[str]
        ] = None,

        party_names: Optional[
            List[str]
        ] = None,

        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Exact structured lookup on normalized legal identifiers.

        This is the third read path, and it carries the same obligation as the
        other two: ``query_filter`` has no default and an explicit ``None`` is
        refused. The identifier conditions are **added to** the caller's filter
        rather than replacing it, so the access conditions built by
        ``build_qdrant_filter`` are still applied by Qdrant during the scroll.
        There is deliberately no code path here that constructs its own filter
        -- that is exactly how a third retriever would become an ACL bypass.

        Identifier conditions are combined with ``should`` (OR) because a query
        naming two articles wants either, while the incoming ``must`` (access +
        relevance) stays intact. Qdrant applies ``must`` and ``should`` together,
        so this can only ever narrow what the access scope already permitted.

        The OR spans identifier *kinds* as well as values, so a query naming
        both an article and a date matches chunks carrying either. That is
        deliberately the looser reading. Requiring both would make the exact
        path return nothing whenever one of the two identifiers was
        mis-extracted -- and extraction is the least reliable link in this
        chain -- whereas a union hands fusion more candidates and lets the
        semantic halves sort them out. Precision is recovered by the compound
        ``_ref`` keys when the caller scopes the query, not by intersecting
        kinds.

        Uses ``scroll`` rather than ``query_points``: there is no vector to
        score against, and an exact match is boolean. Every match is equally
        exact, so results carry no similarity score -- the fusion layer ranks
        them by the order returned, which for a citation lookup is arbitrary
        but consistent. Returns ``[]`` when no identifier tokens are supplied,
        which keeps the caller's branch trivial.
        """
        self._require_filter(query_filter, "identifier_search")

        should_conditions = []

        for field, values in (
            (
                "article_ref",
                article_refs,
            ),
            (
                "article_no",
                article_numbers,
            ),
            (
                "case_no",
                case_numbers,
            ),
            (
                "date_ref",
                date_refs,
            ),
            (
                "date_no",
                dates,
            ),
            (
                "money_ref",
                money_refs,
            ),
            (
                "money_no",
                money_values,
            ),
            (
                "party_name",
                party_names,
            ),
        ):
            if values:
                should_conditions.append(
                    FieldCondition(
                        key=field,
                        match=MatchAny(any=list(values)),
                    )
                )

        if not should_conditions:
            return []

        combined = Filter(
            must=list(query_filter.must or []),
            should=should_conditions,
            # Without this, Qdrant treats `should` as a pure scoring hint and
            # returns points matching only `must` -- i.e. the entire permitted
            # corpus, unfiltered by identifier. That would silently turn exact
            # search into "everything the caller may read", which is the one
            # outcome worse than having no exact search at all.
            min_should=qmodels.MinShould(
                conditions=should_conditions,
                min_count=1,
            ),
        )

        scroll_res, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=combined,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        return [
            self._project(
                point_id=point.id,
                payload=point.payload or {},
            )
            for point in scroll_res
        ]

    def sparse_search(
        self,
        query_sparse: SparseVector,
        query_filter: Filter,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search the named sparse vector under a mandatory payload filter.

        This is a **new read path**, and it carries exactly the same
        obligations as ``dense_search``: ``query_filter`` has no default, an
        explicit ``None`` is refused, and the access conditions travel inside
        the filter Qdrant applies during the search rather than being applied
        to the results afterwards. Sparse retrieval is scoped by the same
        ``Filter`` object the dense side uses, built by the same
        ``build_qdrant_filter``, so there is one place where access conditions
        are constructed and both paths consume it.

        Returns an empty list when the collection has no sparse vector. That
        is a relevance degradation, not an access one -- the alternative is
        every query raising on a collection that predates sparse support.
        """
        self._require_filter(query_filter, "sparse_search")

        if not self.sparse_enabled:
            logger.warning(
                "sparse_search called on a collection with no "
                f"'{SPARSE_VECTOR_NAME}' vector; returning no keyword "
                "candidates. Dense retrieval is unaffected."
            )
            return []

        if query_sparse is None or not query_sparse.indices:
            return []

        if not hasattr(self.client, "query_points"):
            # Sparse search needs the query_points API. The dense path keeps
            # a legacy search() fallback; there is no equivalent for named
            # sparse vectors in this client version, so say so rather than
            # silently returning nothing and looking like a relevance bug.
            raise RuntimeError(
                "This qdrant-client build has no query_points API, which "
                "native sparse search requires."
            )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_sparse,
            using=SPARSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        return [
            self._project(
                point_id=res.id,
                payload=res.payload or {},
                score=float(res.score),
            )
            for res in response.points
        ]

    @staticmethod
    def _require_filter(
        query_filter: Optional[Filter],
        caller: str,
    ) -> None:
        """
        Refuse a read with no filter.

        The signatures already make the argument mandatory; this catches an
        explicit ``None`` being passed through from a caller that built one
        conditionally.
        """
        if query_filter is None:
            raise AccessScopeRequired(
                f"{caller} requires a query filter carrying access "
                "conditions. Reading with no filter would return every "
                "tenant's documents."
            )

    def get_all_chunks(self, query_filter: Filter) -> List[Dict[str, Any]]:
        """
        Fetch stored payload chunks for BM25/keyword indexing.

        This is the second read path, and the one most easily forgotten:
        BM25 scrolls the collection directly rather than going through
        dense_search, so an unfiltered scroll here would leak every tenant's
        text into the keyword index even while dense search stayed correctly
        scoped.
        """
        self._require_filter(query_filter, "get_all_chunks")

        scroll_res, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=query_filter,
            limit=1000,
            with_payload=True,
            with_vectors=False
        )

        results = []
        for point in scroll_res:
            payload = point.payload or {}
            results.append(
                self._project(
                    point_id=point.id,
                    payload=payload,
                )
            )
        return results
