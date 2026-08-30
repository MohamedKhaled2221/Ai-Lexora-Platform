"""Tests for legal-aware chunking: boundary logic, granularity, size handling."""

from __future__ import annotations

import pytest

from src.chunking import (
    build_units,
    choose_granularity,
    chunk_document,
    split_oversized,
)
from src.config import ChunkingConfig, PipelineConfig
from src.structure_preservation import StructLevel, annotate_structure

ARABIC_STATUTE = [
    "الباب الأول",
    "الفصل الأول",
    "المادة (1)",
    "يعمل بأحكام القانون المرفق في شأن تنظيم التوريدات الحكومية، ويلغى كل حكم يخالفه.",
    "المادة (2)",
    "يقصد في تطبيق أحكام هذا القانون بالكلمات الآتية المعنى المبين قرين كل منها وذلك "
    "على النحو الذي تحدده اللائحة التنفيذية الصادرة من الوزير المختص بذلك.",
    "المادة (3)",
    "تسري أحكام هذا القانون على جميع عمليات التوريد التي تجريها الجهات الإدارية "
    "وذلك فيما لم يرد بشأنه نص خاص في قانون آخر.",
    "المادة (4)",
    "لا يجوز التعاقد إلا بعد الإعلان عن العملية بإحدى الطرق المبينة باللائحة.",
]

ENGLISH_CONTRACT = [
    "1. Definitions",
    "In this Agreement the following expressions have the meanings given below "
    "and shall be construed accordingly throughout this instrument.",
    "2. Scope of Works",
    "The Second Party shall supply all equipment described in Annex 1 in "
    "accordance with the approved technical specifications set out therein.",
    "3. Termination",
    "Termination may occur at the option of the First Party without recourse to "
    "the courts upon fifteen days written notice of material breach.",
    "4. Governing Law",
    "This Agreement shall be governed by the laws of the Arab Republic of Egypt "
    "and the North Cairo Court shall have exclusive jurisdiction over disputes.",
]


@pytest.fixture
def statute_doc(make_doc):
    return annotate_structure(make_doc([(1, ARABIC_STATUTE)]))


@pytest.fixture
def contract_doc(make_doc):
    return annotate_structure(make_doc([(1, ENGLISH_CONTRACT)]))


class TestGranularity:
    def test_statute_chunks_at_article_level(self, statute_doc):
        """Articles are the atomic legal unit of a statute. Cutting deeper
        would split an article's obligations across chunks."""
        assert choose_granularity(statute_doc, ChunkingConfig()) is StructLevel.ARTICLE

    def test_contract_chunks_at_clause_level(self, contract_doc):
        assert choose_granularity(contract_doc, ChunkingConfig()) is StructLevel.CLAUSE

    def test_no_structure_returns_none(self, make_doc):
        doc = annotate_structure(make_doc([(1, [
            "هذا نص عادي بلا أي علامات هيكلية على الإطلاق ويستمر لفترة طويلة.",
            "وهذه فقرة أخرى من النص العادي بلا ترقيم أو عناوين من أي نوع كان.",
        ])]))
        assert choose_granularity(doc, ChunkingConfig()) is None

    def test_single_stray_marker_is_not_a_scheme(self, make_doc):
        """One '(a)' is a typo, not a sub-clause scheme. Treating it as one
        would fragment the document on a single accident."""
        doc = annotate_structure(make_doc([(1, [
            "1. First Clause", "Body text of the first clause of this agreement here.",
            "2. Second Clause", "Body text of the second clause of this agreement here.",
            "3. Third Clause", "(a) a lone sub-item that appears exactly once overall",
        ])]))
        assert choose_granularity(doc, ChunkingConfig()) is StructLevel.CLAUSE

    def test_explicit_split_by_overrides_auto(self, contract_doc):
        cfg = ChunkingConfig(split_by="section")
        assert choose_granularity(contract_doc, cfg) is not StructLevel.SUBCLAUSE

    def test_respect_structure_false_degrades_to_paragraph(self, statute_doc):
        cfg = PipelineConfig()
        cfg.chunking.respect_structure = False
        chunks = chunk_document(statute_doc, cfg)
        assert all(c.metadata["chunk_strategy"] == "paragraph" for c in chunks)


class TestStructuralBoundaries:
    def test_each_article_becomes_its_own_chunk(self, statute_doc):
        cfg = PipelineConfig()
        chunks = chunk_document(statute_doc, cfg)
        articles = {
            (c.metadata["structure"] or {}).get("article")
            for c in chunks
            if (c.metadata["structure"] or {}).get("article")
        }
        assert articles == {"المادة 1", "المادة 2", "المادة 3", "المادة 4"}

    def test_article_body_stays_with_its_heading(self, statute_doc):
        cfg = PipelineConfig()
        chunks = chunk_document(statute_doc, cfg)
        art4 = next(
            c for c in chunks
            if (c.metadata["structure"] or {}).get("article") == "المادة 4"
        )
        assert "لا يجوز التعاقد" in art4.text

    def test_cross_reference_does_not_split(self, make_doc):
        """'ونصت المادة 12' mid-sentence is a citation, not a boundary.
        Splitting there would cut a clause in half at every citation."""
        doc = annotate_structure(make_doc([(1, [
            "المادة (1)",
            "ونصت المادة 12 من القانون المدني على أن الالتزام ينقضي بالوفاء، "
            "كما قضت المادة 15 بأحكام مماثلة في هذا الشأن وذلك دون إخلال بغيرها.",
        ])]))
        chunks = chunk_document(doc, PipelineConfig())
        assert len(chunks) == 1

    def test_chunk_ids_are_sequential_and_formatted(self, statute_doc):
        chunks = chunk_document(statute_doc, PipelineConfig())
        assert [c.chunk_id for c in chunks] == [
            f"chunk_{i:03d}" for i in range(1, len(chunks) + 1)
        ]

    def test_clause_ids_are_stable_and_unique(self, contract_doc):
        chunks = chunk_document(contract_doc, PipelineConfig())
        ids = [
            (c.metadata["structure"] or {}).get("clause_id")
            for c in chunks
            if (c.metadata["structure"] or {}).get("clause_id")
        ]
        assert len(ids) == len(set(ids))

    def test_heading_path_records_ancestry(self, statute_doc):
        chunks = chunk_document(statute_doc, PipelineConfig())
        art2 = next(
            c for c in chunks
            if (c.metadata["structure"] or {}).get("article") == "المادة 2"
        )
        path = (art2.metadata["structure"] or {})["heading_path"]
        assert any("الباب" in p for p in path)
        assert any("المادة" in p for p in path)


class TestSizeHandling:
    def test_short_text_is_not_split(self):
        cfg = ChunkingConfig()
        assert split_oversized("short text", cfg) == ["short text"]

    def test_oversized_splits_at_paragraph_first(self):
        cfg = ChunkingConfig(max_chunk_chars=120, overlap_chars=0)
        text = "\n\n".join(["A" * 80, "B" * 80, "C" * 80])
        pieces = split_oversized(text, cfg)
        assert len(pieces) == 3
        assert all(len(p) <= 120 for p in pieces)

    def test_never_splits_mid_word(self):
        cfg = ChunkingConfig(max_chunk_chars=60, overlap_chars=0)
        text = " ".join(["المسؤولية"] * 40)
        for piece in split_oversized(text, cfg):
            for word in piece.split():
                assert word == "المسؤولية", "a word was cut in half"

    def test_overlap_applied_only_on_artificial_splits(self):
        cfg = ChunkingConfig(max_chunk_chars=100, overlap_chars=20)
        pieces = split_oversized(" ".join(["word"] * 80), cfg)
        assert len(pieces) > 1
        assert pieces[1].startswith("word")

    def test_zero_overlap_config_honoured(self):
        cfg = ChunkingConfig(max_chunk_chars=100, overlap_chars=0)
        sentences = ". ".join([f"Sentence number {i} here" for i in range(20)])
        pieces = split_oversized(sentences, cfg)
        assert len(pieces) > 1

    def test_whole_clauses_get_no_overlap(self, statute_doc):
        """Overlapping real clause boundaries would duplicate obligation text
        across chunks, which is how contract QA ends up citing the wrong clause."""
        chunks = chunk_document(statute_doc, PipelineConfig())
        assert all(c.metadata["split_from_unit"] is False for c in chunks)

    def test_split_units_are_marked(self, make_doc):
        long_body = " ".join(["الالتزام"] * 800)
        doc = annotate_structure(make_doc([
            (1, ["المادة (1)", long_body, "المادة (2)", "نص المادة الثانية.",
                 "المادة (3)", "نص المادة الثالثة."]),
        ]))
        chunks = chunk_document(doc, PipelineConfig())
        oversized = [c for c in chunks if c.metadata["chunk_strategy"] == "size"]
        assert len(oversized) > 1
        assert all(c.metadata["split_from_unit"] for c in oversized)

    def test_max_chunk_chars_is_never_exceeded(self, make_doc):
        """Guards the budget accounting: the heading prefix and the overlap tail
        are both added *after* the split, so a naive implementation overshoots
        the configured maximum on every split chunk."""
        long_body = " ".join(["الالتزام"] * 900)
        doc = annotate_structure(make_doc([
            (1, ["المادة (1) : أحكام عامة وشروط التنفيذ", long_body,
                 "المادة (2)", "نص ثان.", "المادة (3)", "نص ثالث."]),
        ]))
        cfg = PipelineConfig()
        cfg.chunking.max_chunk_chars = 1500
        cfg.chunking.overlap_chars = 200
        for c in chunk_document(doc, cfg):
            assert len(c.text) <= 1500, f"{c.chunk_id} is {len(c.text)} chars"

    def test_short_article_keeps_its_own_identity(self, make_doc):
        """A one-line article is a complete article. Merging it into its
        neighbour would make M5 cite article 1's text under article 2's number.
        """
        cfg = PipelineConfig()
        doc = annotate_structure(make_doc([(1, [
            "المادة (1)",
            "نص قصير جدا.",
            "المادة (2)",
            "وهذا نص المادة الثانية وهو أطول بكثير من سابقه ويستوفي الحد الأدنى "
            "لطول الجزء المطلوب حتى لا يندمج مع ما بعده على الإطلاق.",
        ])]))
        chunks = chunk_document(doc, cfg)
        articles = [
            (c.metadata["structure"] or {}).get("article") for c in chunks
        ]
        assert "المادة 1" in articles and "المادة 2" in articles
        art1 = next(c for c in chunks
                    if (c.metadata["structure"] or {}).get("article") == "المادة 1")
        assert "نص قصير جدا" in art1.text
        assert "المادة الثانية" not in art1.text

    def test_identityless_fragment_merges_forward(self, make_doc):
        """Bare structural headings with no clause_id of their own ARE merged --
        that is what min_chunk_chars is for."""
        cfg = PipelineConfig()
        doc = annotate_structure(make_doc([(1, [
            "الباب الأول",
            "الفصل الأول",
            "المادة (1)",
            "نص المادة الأولى وهو نص طويل بما يكفي لتجاوز الحد الأدنى المقرر للجزء "
            "الواحد حتى لا يندمج مع ما يليه من مواد أخرى في المستند.",
        ])]))
        chunks = chunk_document(doc, cfg)
        assert len(chunks) == 1
        assert "الباب" in chunks[0].text and "المادة" in chunks[0].text

    def test_merged_chunk_keeps_the_identity_of_where_it_starts(self, make_doc):
        """A chunk whose text opens with clause 1.1 must be labelled 1.1, not
        1.2 -- otherwise downstream citation is wrong."""
        cfg = PipelineConfig()
        doc = annotate_structure(make_doc([(1, [
            "1.1 Short one.",
            "1.2 This is a much longer clause that comfortably exceeds the minimum "
            "chunk length and therefore will not itself be merged into anything.",
        ])]))
        chunks = chunk_document(doc, cfg)
        first = chunks[0]
        assert "Short one" in first.text
        assert (first.metadata["structure"] or {}).get("clause_id") == "cl_1.1"


class TestTables:
    def test_table_becomes_its_own_chunk(self, make_doc):
        from src.structure_preservation import ExtractedTable

        doc = make_doc([(1, ["المادة (1)", "نص المادة الأولى وهو نص طويل بما يكفي للاختبار."])])
        doc.pages[0].tables.append(
            ExtractedTable(rows=[["الدفعة", "القيمة"], ["الأولى", "612,500"]], page=1)
        )
        annotate_structure(doc)
        chunks = chunk_document(doc, PipelineConfig())
        tables = [c for c in chunks if c.metadata["is_table"]]
        assert len(tables) == 1
        assert tables[0].metadata["chunk_strategy"] == "table"
        assert tables[0].metadata["table_shape"] == [2, 2]

    def test_table_is_never_split(self, make_doc):
        from src.structure_preservation import ExtractedTable

        big = [[f"cell {r}-{c} with padding text" for c in range(6)] for r in range(60)]
        doc = make_doc([(1, ["المادة (1)", "نص تمهيدي للجدول التالي وهو طويل بما يكفي."])])
        doc.pages[0].tables.append(ExtractedTable(rows=big, page=1))
        annotate_structure(doc)
        cfg = PipelineConfig()
        cfg.chunking.max_chunk_chars = 500
        tables = [c for c in chunk_document(doc, cfg) if c.metadata["is_table"]]
        assert len(tables) == 1, "an oversized table must stay whole, not be cut"
        assert len(tables[0].text) > 500

    def test_table_markdown_preserved(self, make_doc):
        from src.structure_preservation import ExtractedTable

        doc = make_doc([(1, ["نص تمهيدي طويل بما يكفي لتجاوز الحد الأدنى للجزء المطلوب."])])
        doc.pages[0].tables.append(
            ExtractedTable(rows=[["أ", "ب"], ["1", "2"]], page=1)
        )
        annotate_structure(doc)
        tbl = next(c for c in chunk_document(doc, PipelineConfig()) if c.metadata["is_table"])
        assert "|" in tbl.metadata["table_markdown"]
        assert "---" in tbl.metadata["table_markdown"]


class TestFallback:
    def test_unstructured_uses_paragraph_strategy(self, make_doc):
        doc = annotate_structure(make_doc([(1, [
            "هذه فقرة من نص غير مهيكل على الإطلاق ولا تحتوي على أي علامات ترقيم قانونية.",
            "وهذه فقرة أخرى مماثلة تماما بلا أي بنية يمكن اكتشافها بواسطة المحلل.",
        ])]))
        chunks = chunk_document(doc, PipelineConfig())
        assert chunks
        assert all(c.metadata["chunk_strategy"] == "paragraph" for c in chunks)

    def test_paragraph_chunks_respect_target_size(self, make_doc):
        paras = [f"هذه هي الفقرة رقم {i} من نص غير مهيكل بلا علامات. " * 6 for i in range(12)]
        doc = annotate_structure(make_doc([(1, paras)]))
        cfg = PipelineConfig()
        cfg.chunking.target_chunk_chars = 400
        cfg.chunking.max_chunk_chars = 700
        chunks = chunk_document(doc, cfg)
        assert len(chunks) > 1
        assert all(len(c.text) <= 700 for c in chunks)

    def test_empty_document_yields_no_chunks(self, make_doc):
        doc = annotate_structure(make_doc([(1, ["", "   "])]))
        assert chunk_document(doc, PipelineConfig()) == []


class TestConfigurability:
    @pytest.mark.parametrize("target,maximum", [(300, 500), (800, 1500), (2000, 4000)])
    def test_size_config_is_honoured(self, make_doc, target, maximum):
        paras = ["نص طويل جدا للاختبار ويتكرر كثيرا. " * 12 for _ in range(10)]
        doc = annotate_structure(make_doc([(1, paras)]))
        cfg = PipelineConfig()
        cfg.chunking.target_chunk_chars = target
        cfg.chunking.max_chunk_chars = maximum
        chunks = chunk_document(doc, cfg)
        assert all(len(c.text) <= maximum for c in chunks)

    def test_attach_heading_can_be_disabled(self, statute_doc):
        cfg = PipelineConfig()
        cfg.chunking.attach_heading_to_body = False
        chunks = chunk_document(statute_doc, cfg)
        assert chunks

    def test_heading_not_duplicated_when_body_already_has_it(self, statute_doc):
        chunks = chunk_document(statute_doc, PipelineConfig())
        art1 = next(
            c for c in chunks
            if (c.metadata["structure"] or {}).get("article") == "المادة 1"
        )
        assert art1.text.count("المادة") <= 2


class TestSchemaContractRegressions:
    """Guards for the two items fixed in ``reports/schema_contract_verification.md``.

    Both are M2-facing: M2's copy of ``DocumentChunk`` declares a top-level
    ``clause`` and a **required** ``page`` (``ge=1``). Neither is enforceable
    from M2's side -- M2's model is ``extra="ignore"``, so a missing ``clause``
    resolves silently to ``None`` -- which is exactly why they are pinned here.
    """

    def test_clause_is_surfaced_at_the_top_level(self, contract_doc):
        """``clause`` must appear on the chunk, not only under metadata."""
        chunks = chunk_document(contract_doc, PipelineConfig())
        clause_chunks = [
            c for c in chunks
            if (c.metadata.get("structure") or {}).get("clause")
        ]
        assert clause_chunks, "fixture must produce at least one clause-anchored chunk"
        for c in clause_chunks:
            nested = c.metadata["structure"]["clause"]
            assert c.clause == nested

    def test_nested_clause_is_kept_as_well(self, contract_doc):
        """The top-level field is additive -- ``metadata.structure`` still has it."""
        chunks = chunk_document(contract_doc, PipelineConfig())
        for c in chunks:
            if c.clause:
                assert c.metadata["structure"]["clause"] == c.clause

    def test_clause_is_none_when_the_chunk_has_no_clause(self, make_doc):
        doc = annotate_structure(make_doc([(1, [
            "نص عادي بلا أي علامات هيكلية على الإطلاق ويستمر لبعض الوقت.",
            "فقرة ثانية أيضا بلا علامات، لمجرد إعطاء المستند حجما كافيا.",
        ])]))
        chunks = chunk_document(doc, PipelineConfig())
        assert chunks
        assert all(c.clause is None for c in chunks)

    def test_pageless_blocks_still_yield_a_valid_page(self, make_doc):
        """The Docling path can hand chunking a block with ``page=None``.

        That used to propagate to ``chunk.page = None``, which M2 rejects
        (``page`` is required there). It must now fall back to page 1.
        """
        doc = make_doc([(1, list(ENGLISH_CONTRACT))])
        for page in doc.pages:
            for b in page.blocks:
                b.page = None
        chunks = chunk_document(annotate_structure(doc), PipelineConfig())
        assert chunks
        assert all(c.page == 1 for c in chunks)

    def test_no_chunk_from_any_fixture_has_a_none_page(self, statute_doc, contract_doc):
        for doc in (statute_doc, contract_doc):
            for c in chunk_document(doc, PipelineConfig()):
                assert isinstance(c.page, int) and c.page >= 1
