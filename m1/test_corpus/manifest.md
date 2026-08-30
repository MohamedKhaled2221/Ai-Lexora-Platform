# Test Corpus -- Manifest

> ## THIS CORPUS CONTAINS NO FIRM DATA, BY DESIGN
>
> Everything here is either a publicly published legal document or a file this
> project fabricated for testing. Nothing came from a client, a matter, or the
> firm's archive.
>
> That is the design, not a stage. The engagement constraint is that no
> document leaves the firm, so the system was built and validated to be
> **evaluable without client material**: published Egyptian legislation supplies
> real legal Arabic and real publisher defects, and synthetic fixtures supply
> exact ground truth for the cases published documents cannot provide. **This
> pipeline has not processed a real client document and does not need to have
> done so for the numbers in the evaluation report to hold.**
>
> What the corpus cannot tell you is stated plainly in *Permanent limits of this
> corpus* below. Those are properties of the approach, not gaps awaiting data.

## Pointing the pipeline at other documents

Drop files into `test_corpus/real/` (git-ignored) and run
``python scripts/evaluate.py --corpus-dir test_corpus/real``. No code changes;
the corpus location is the only coupling. This exists so the firm can run the
evaluation **on its own hardware, on its own documents, without sending them
anywhere** -- not because the results below are provisional.


Generated: 2026-08-12 00:28:01

## `public/` -- published legal documents

Public-law texts from open repositories. Legislative text carries no copyright restriction. Downloaded by `scripts/fetch_public_corpus.py`, which re-runs idempotently.

| File | Source | Description | Format | Language | Pages | Quirks / relevance |
|---|---|---|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | Constitute Project (comparativeconstitutionsproject.org) | دستور جمهورية مصر العربية 2014 -- Egyptian Constitution 2014, Arabic | PDF / text | ar | 44 | digitally native (text layer present); real published Arabic legal drafting; article-per-section structure; two-column layout |
| `constitute_egypt_2014_en.pdf` | Constitute Project | Egyptian Constitution 2014, English translation | PDF / text | en | 53 | digitally native (text layer present); article-per-section structure; two-column layout |
| `constitute_egypt_2019_ar.pdf` | Constitute Project | دستور جمهورية مصر العربية 2019 (تعديلات) -- Egyptian Constitution as amended 2019, Arabic | PDF / text | ar | 50 | digitally native (text layer present); real published Arabic legal drafting; article-per-section structure; two-column layout |
| `eg_constitution_2014_en.pdf` | ConstitutionNet (International IDEA) | Constitution of the Arab Republic of Egypt, English translation | PDF / text | en | 47 | digitally native (text layer present) |
| `eg_official_gazette_excerpt.pdf` | ecoi.net (Austrian Red Cross) | Egyptian Official Gazette excerpt (Law 70/2017 on Associations), unofficial English translation | PDF / text | en | 29 | digitally native (text layer present); official gazette formatting; unofficial translation |
| `wipo_eg081ar_1.pdf` | WIPO Lex (wipo.int/wipolex) | Egyptian legislation, Arabic original as published by WIPO Lex | PDF / text | ar | 94 | digitally native (text layer present); real published Arabic legal drafting; statute with المادة numbering; long (up to 94pp) |
| `wipo_eg088ar_1.pdf` | WIPO Lex (wipo.int/wipolex) | Egyptian legislation, Arabic original as published by WIPO Lex | PDF / text | ar | 13 | digitally native (text layer present); real published Arabic legal drafting; statute with المادة numbering; long (up to 94pp) |

### Present on disk, excluded from every metric

Listed rather than deleted. A document dropped silently is indistinguishable from a document nobody thought to test, and the reason for an exclusion is itself a finding about the corpus.

| File | Why excluded |
|---|---|
| `wipo_eg087ar_1.pdf` | handwritten. Its text layer scores 0.33 on text_layer_quality and contains no Arabic at all despite being an Arabic statute, so it yields no usable ground truth and cannot be scored. It is also not representative: the firm's archive is typed and printed material. Kept in test_corpus/public/ as a robustness input -- the pipeline must not crash on it -- but excluded from every accuracy metric. |

## `synthetic/` -- fabricated test documents

**All data invented.** Party names, national IDs, addresses, amounts, dates and case numbers are fictional. The legal phrasing imitates the *shape* of standard-form Egyptian instruments so structure detection has something realistic to parse; it is not legal drafting.

Generated deterministically by `scripts/make_synthetic_corpus.py` (seed 20260811), so the corpus is reproducible.

| File | Format | Language mix | Structure | Expected quirks |
|---|---|---|---|---|
| `bench_constitute_egypt_2014_ar_clean.pdf` | pdf | ? | - | - |
| `bench_constitute_egypt_2014_ar_poor.pdf` | pdf | ? | - | - |
| `bench_constitute_egypt_2014_en_clean.pdf` | pdf | ? | - | - |
| `bench_constitute_egypt_2014_en_poor.pdf` | pdf | ? | - | - |
| `bench_constitute_egypt_2019_ar_clean.pdf` | pdf | ? | - | - |
| `bench_constitute_egypt_2019_ar_poor.pdf` | pdf | ? | - | - |
| `bench_eg_official_gazette_excerpt_clean.pdf` | pdf | ? | - | - |
| `bench_eg_official_gazette_excerpt_poor.pdf` | pdf | ? | - | - |
| `bench_wipo_eg081ar_1_clean.pdf` | pdf | ? | - | - |
| `bench_wipo_eg081ar_1_poor.pdf` | pdf | ? | - | - |
| `bench_wipo_eg088ar_1_clean.pdf` | pdf | ? | - | - |
| `bench_wipo_eg088ar_1_poor.pdf` | pdf | ? | - | - |
| `scan_authored_award_en_150dpi.pdf` | pdf / scanned | pure English | arbitral award with roman-numeral sections | - 150 dpi equivalent, heavy noise and JPEG artifacts<br>- NO text layer -- must be classified scanned and routed to OCR<br>- the reference has no visual-order, fragmentation or out-of-flow defect, unlike every reference derived from a source text layer. **These are the fixtures whose absolute OCR accuracy is quotable.**<br>- still optimistic against real scans: rendered glyphs, no scanner optics, no photocopy generations, no bleed-through |
| `scan_authored_award_en_300dpi.pdf` | pdf / scanned | pure English | arbitral award with roman-numeral sections | - clean 300 dpi equivalent<br>- NO text layer -- must be classified scanned and routed to OCR<br>- the reference has no visual-order, fragmentation or out-of-flow defect, unlike every reference derived from a source text layer. **These are the fixtures whose absolute OCR accuracy is quotable.**<br>- still optimistic against real scans: rendered glyphs, no scanner optics, no photocopy generations, no bleed-through |
| `scan_authored_statute_ar_150dpi.pdf` | pdf / scanned | pure Arabic | statute articles (المادة) | - 150 dpi equivalent, heavy noise and JPEG artifacts<br>- NO text layer -- must be classified scanned and routed to OCR<br>- the reference has no visual-order, fragmentation or out-of-flow defect, unlike every reference derived from a source text layer. **These are the fixtures whose absolute OCR accuracy is quotable.**<br>- still optimistic against real scans: rendered glyphs, no scanner optics, no photocopy generations, no bleed-through |
| `scan_authored_statute_ar_300dpi.pdf` | pdf / scanned | pure Arabic | statute articles (المادة) | - clean 300 dpi equivalent, minimal degradation<br>- NO text layer -- must be classified scanned and routed to OCR<br>- the reference has no visual-order, fragmentation or out-of-flow defect, unlike every reference derived from a source text layer. **These are the fixtures whose absolute OCR accuracy is quotable.**<br>- still optimistic against real scans: rendered glyphs, no scanner optics, no photocopy generations, no bleed-through |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | pdf / scanned | pure Arabic | as in the source statute/constitution (المادة / Article numbering) | - rasterized at 200 dpi, skew 0.6 deg, gaussian noise sigma 6, blur 0.4, JPEG quality 78<br>- NO text layer -- type_detection must classify this as 'scanned' and route every page to OCR<br>- character-level ground truth available, so OCR accuracy is measurable per language<br>- OPTIMISTIC vs real firm scans: clean glyph rendering, no scanner optics, no photocopy generations, no staple shadows or bleed-through<br>- GROUND TRUTH CAVEAT: the source PDF extracts with spurious intra-word spacing ('دس تور' for 'دستور'), so the reference disagrees with correctly-spaced OCR output on most word boundaries. Space-sensitive CER/WER against this file overstate the error; the space-insensitive CER is the meaningful figure. |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | pdf / scanned | pure English | as in the source statute/constitution (المادة / Article numbering) | - rasterized at 200 dpi, skew 0.5 deg, gaussian noise sigma 6, blur 0.4, JPEG quality 78<br>- NO text layer -- type_detection must classify this as 'scanned' and route every page to OCR<br>- character-level ground truth available, so OCR accuracy is measurable per language<br>- OPTIMISTIC vs real firm scans: clean glyph rendering, no scanner optics, no photocopy generations, no staple shadows or bleed-through |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | pdf / scanned | pure Arabic | - | - rasterized at 150 dpi, skew -1.2 deg, noise 11, JPEG q60<br>- page-separated ground truth (form feed), unlike the first-wave scan_* fixtures |
| `scan_eg_constitution_2014_en_150dpi.pdf` | pdf / scanned | pure English | - | - rasterized at 150 dpi, skew -0.9 deg, noise 9, JPEG q64<br>- page-separated ground truth (form feed), unlike the first-wave scan_* fixtures |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | pdf / scanned | pure English | - | - rasterized at 300 dpi, skew 0.3 deg, noise 4, JPEG q85<br>- page-separated ground truth (form feed), unlike the first-wave scan_* fixtures |
| `scan_wipo_eg081ar_1_300dpi.pdf` | pdf / scanned | pure Arabic | - | - rasterized at 300 dpi, skew 0.4 deg, noise 4, JPEG q85<br>- page-separated ground truth (form feed), unlike the first-wave scan_* fixtures |
| `scan_wipo_eg088ar_1_150dpi.pdf` | pdf / scanned | pure Arabic | as in the source statute/constitution (المادة / Article numbering) | - rasterized at 150 dpi, skew -1.1 deg, gaussian noise sigma 10, blur 0.9, JPEG quality 62<br>- NO text layer -- type_detection must classify this as 'scanned' and route every page to OCR<br>- character-level ground truth available, so OCR accuracy is measurable per language<br>- OPTIMISTIC vs real firm scans: clean glyph rendering, no scanner optics, no photocopy generations, no staple shadows or bleed-through<br>- GROUND TRUTH CAVEAT: the source PDF extracts with spurious intra-word spacing ('دس تور' for 'دستور'), so the reference disagrees with correctly-spaced OCR output on most word boundaries. Space-sensitive CER/WER against this file overstate the error; the space-insensitive CER is the meaningful figure. |
| `stress_exhibits_footnotes.pdf` | pdf / text-based | English body with Arabic headings | articles plus lettered exhibits, roman appendices, numbered schedules, and bracketed footnote references | - four parallel numbering systems in one document (Article 1.1, Exhibit A.1, Appendix II.1, Schedule S1.1) -- a detector keyed on one of them will mis-rank the others<br>- footnote markers [1][2][3] inline in clause text, with the footnote bodies collected at the end behind a rule<br>- annex headings appear after the operative text, so document order and clause-id order diverge |
| `stress_inline_bilingual.pdf` | pdf / text-based | Arabic and English alternating WITHIN single sentences | numbered memorandum paragraphs, no article markers | - the hard bidi case: direction switches mid-sentence, several times per line, around parenthesised English glosses<br>- Latin terms embedded in Arabic clauses ('عقود الـ finance lease') -- language detection must return mixed, not pick a winner<br>- quoted English inside Arabic inside brackets: nested direction runs |
| `stress_nested_clauses_ar.pdf` | pdf / text-based | bilingual, parallel Arabic/English lines | clause numbering five levels deep: 5, 5.2, 5.2.1, 5.2.1.b, 5.2.1.b.ii | - deepest numbering in the corpus -- tests whether the structure detector builds a heading path rather than flattening every level to the same rank<br>- letter and roman sub-levels mixed with numeric ones (.a, .b.i)<br>- every clause appears twice, once per language, so a chunker that cuts on markers must not treat the English restatement as a new clause |
| `stress_table_pagebreak.pdf` | pdf / text-based | bilingual table cells | a single 30-row table that spans a page boundary, with a repeated header row on the continuation page | - the table is ONE logical table but TWO page objects. Extractors that work per page report two tables; the header row appears twice; a chunker with keep_tables_whole must decide which of those is true<br>- the continuation page's first row is a repeat of the header, not data<br>- counted as 1 expected table on purpose -- reporting 2 is the failure mode this fixture exists to surface |
| `stress_table_ruled_ar.png` | png (image) | bilingual | 3-column FULLY RULED bilingual table | - every cell is boxed -- the easy case, and the control against which the borderless fixtures are read<br>- Arabic label column, English label column, Western numerals<br>- degraded: -0.3 deg skew, noise 4, JPEG q82 |
| `stress_table_sparse_bilingual.png` | png (image) | bilingual | 4-column table with EMPTY CELLS in every column | - blank cells on purpose: a reconstructor that assumes full rows will shift contents into the wrong column rather than emit a gap<br>- Arabic-Indic numerals in the case column against Western numerals in the date column<br>- most degraded of the three (JPEG q72) -- tests the table geometry under recognition noise<br>- degraded: -0.6 deg skew, noise 8, JPEG q72 |
| `stress_table_wide_en.png` | png (image) | English | 6-column BORDERLESS English table | - six columns with narrow gutters -- tests whether cell splitting survives when the inter-column gap approaches the inter-word gap<br>- no ruling lines except one header rule<br>- degraded: 0.4 deg skew, noise 6, JPEG q78 |
| `synthetic_contract_ar.docx` | docx | Arabic primary + English counterpart | Word Heading 1/2 styles carrying المادة (n) labels; 5-col Table Grid; explicit page break | - DOCX has no stored pagination -- page numbers come from the single explicit page break only; pipeline warns about this<br>- logical-order Arabic (unlike the PDF fixture) -- rtl_fix should NOT repair this one, which is the negative test<br>- Arabic-Indic digits inside table cells |
| `synthetic_contract_bilingual.pdf` | pdf / text-based | Arabic primary + English counterpart (bilingual) | المادة (1)-(9) Arabic articles; Article 1-8 English; tables; signature/stamp box | - Arabic drawn via arabic-reshaper + python-bidi, so the PDF stores PRESENTATION FORMS IN VISUAL ORDER -- realistic reproduction of Arabic DTP output and the main fixture for rtl_fix repair<br>- 5-column bilingual payment table with mixed Arabic/Latin headers<br>- Arabic-Indic digits (٢٬٤٥٠٬٠٠٠) alongside Western digits in the table<br>- mixed-direction clause bodies (English defined terms inside Arabic)<br>- signature/stamp box as a bordered table |
| `synthetic_lease_bilingual.docx` | docx | English primary with Arabic clauses interleaved (true bilingual mix) | decimal outline 1.1 / 2.3 style; bilingual headings | - clause numbering is decimal (1.1, 2.3) not المادة -- exercises the English CLAUSE marker pattern and auto-granularity at CLAUSE level<br>- Arabic and English clauses alternate inside the same section, so chunk-level language should come out 'mixed' for several chunks<br>- bilingual headings contain both scripts on one line -- an rtl_fix mixed_direction flag is expected here |
| `synthetic_memo_mixed.txt` | txt | heavily mixed Arabic/English in the same sentences | أولاً/ثانياً/ثالثاً enumerators; numbered list items | - code-switching mid-sentence ('البند (5) delay penalty cap محدد بنسبة ١٠٪')<br>- Arabic-Indic dates ١٥/٠٣/٢٠٢٦ mixed with Western dates 20/03/2026<br>- this is the primary fixture for rtl_fix mixed_direction and numeral_direction_ambiguous flags -- flags here are EXPECTED, not a bug |
| `synthetic_stamped_page.png` | png (image) | Arabic primary, one English heading line | البند (1)-(3) clause markers; signature block; two stamps | - image input -- must route straight to OCR with no text layer<br>- round company stamp and rectangular incoming-mail stamp OVERLAP the signature area; OCR is expected to emit junk boxes from the stamps<br>- handwritten-style signature squiggles (non-text ink)<br>- page degraded: 0.7 deg skew, gaussian noise, slight blur, JPEG q72<br>- Arabic-Indic digits in dates and percentages |
| `synthetic_statute_ar.txt` | txt | pure Arabic | الباب / الفصل / المادة hierarchy including 'المادة (7) مكرر'; أولاً-ثالثاً enumerators; (أ)(ب)(ج) sub-clauses | - full statute hierarchy: BOOK > CHAPTER > ARTICLE -- auto granularity should settle on ARTICLE, not sub-clause<br>- 'مكرر' (bis) article numbering, an Egyptian legislative convention that naive numeric parsers drop<br>- no pagination at all (TXT) -- every chunk should report page=1<br>- cross-references ('المادة (4)', 'المادة (7)') inside body text that must NOT be treated as boundaries |
| `synthetic_table_page.png` | png (image) | bilingual Arabic/English column headers and cells | 5-column BORDERLESS table (only a header rule and a total rule) | - borderless table -- PyMuPDF find_tables has no ruling lines to work with; this is the case Docling's TableFormer is meant to cover, and on the OCR path neither applies, so table structure is expected to degrade to reading-order text. KNOWN GAP, see evaluation report.<br>- column contents alternate direction (Arabic label, Latin milestone, Western numerals) -- worst case for line-level reading order<br>- degraded: -0.4 deg skew, noise, JPEG q80 |
| `synthetic_visual_order_ar.txt` | txt | pure Arabic | same statute as synthetic_statute_ar.txt | - DELIBERATELY DAMAGED: stored in VISUAL order with presentation forms, reproducing what broken PDF extraction and some OCR output look like<br>- ground truth for this file is synthetic_statute_ar.txt -- rtl_fix should detect presentation forms and flag/repair reading order<br>- structural markers will NOT match until presentation forms are folded, so this also tests that normalize runs before structure annotation |

## Ground truth, and how far each reference can be trusted

Ground truth here comes from one of two places, and the difference decides what a score against it means.

**Authored.** The text was written first and then painted onto a page (`scan_authored_*`). The reference is correct by construction. These are the only fixtures whose absolute OCR accuracy needs no caveat.

**Derived.** The fixture was rasterized from a public PDF and that PDF's text layer is the reference. Cheap and plentiful, but it inherits the publisher's defects -- and two publishers in this corpus have serious ones. `scripts/audit_ground_truth.py` measures which, per fixture, so a bad reference is never mistaken for bad OCR:

- `authored` -- written, not extracted. Trusted.
- `logical` -- derived, and the audit found nothing wrong. Trusted.
- `visual` -- the publisher stored each line's words in visual (right-to-left) order. Every character is correct, so the file looks fine to a reader, but a correct OCR result scores ~0.70 CER against it.
- `out_of_flow` -- all the words are present (low bag error) but the content stream emits them in a different order from the page, typically because of a marginal annotation column. Inflates CER without any recognition error.
- `unreliable` -- high error that reordering does not explain. Do not quote its absolute number.

A **head-to-head between engines stays valid on every fixture**, including the untrusted ones, because both engines face the same reference. Only absolute accuracy is affected.

| Ground truth | Scored document | Chars | Reference verdict |
|---|---|---|---|
| `bench_constitute_egypt_2014_ar_clean.groundtruth.txt` | `bench_constitute_egypt_2014_ar_clean.pdf` | 13,628 | visual |
| `bench_constitute_egypt_2014_ar_poor.groundtruth.txt` | `bench_constitute_egypt_2014_ar_poor.pdf` | 13,628 | visual |
| `bench_constitute_egypt_2014_en_clean.groundtruth.txt` | `bench_constitute_egypt_2014_en_clean.pdf` | 13,667 | out_of_flow |
| `bench_constitute_egypt_2014_en_poor.groundtruth.txt` | `bench_constitute_egypt_2014_en_poor.pdf` | 13,667 | out_of_flow |
| `bench_constitute_egypt_2019_ar_clean.groundtruth.txt` | `bench_constitute_egypt_2019_ar_clean.pdf` | 10,619 | visual |
| `bench_constitute_egypt_2019_ar_poor.groundtruth.txt` | `bench_constitute_egypt_2019_ar_poor.pdf` | 10,619 | visual |
| `bench_eg_official_gazette_excerpt_clean.groundtruth.txt` | `bench_eg_official_gazette_excerpt_clean.pdf` | 9,542 | logical |
| `bench_eg_official_gazette_excerpt_poor.groundtruth.txt` | `bench_eg_official_gazette_excerpt_poor.pdf` | 9,542 | logical |
| `bench_wipo_eg081ar_1_clean.groundtruth.txt` | `bench_wipo_eg081ar_1_clean.pdf` | 4,946 | logical |
| `bench_wipo_eg081ar_1_poor.groundtruth.txt` | `bench_wipo_eg081ar_1_poor.pdf` | 4,946 | logical |
| `bench_wipo_eg088ar_1_clean.groundtruth.txt` | `bench_wipo_eg088ar_1_clean.pdf` | 5,091 | logical |
| `bench_wipo_eg088ar_1_poor.groundtruth.txt` | `bench_wipo_eg088ar_1_poor.pdf` | 5,091 | logical |
| `scan_authored_award_en_150dpi.groundtruth.txt` | `scan_authored_award_en_150dpi.pdf` | 1,736 | authored |
| `scan_authored_award_en_300dpi.groundtruth.txt` | `scan_authored_award_en_300dpi.pdf` | 1,736 | authored |
| `scan_authored_statute_ar_150dpi.groundtruth.txt` | `scan_authored_statute_ar_150dpi.pdf` | 1,608 | authored |
| `scan_authored_statute_ar_300dpi.groundtruth.txt` | `scan_authored_statute_ar_300dpi.pdf` | 1,608 | authored |
| `scan_constitute_egypt_2014_ar_200dpi.groundtruth.txt` | `scan_constitute_egypt_2014_ar_200dpi.pdf` | 24,927 | unreliable |
| `scan_constitute_egypt_2014_en_200dpi.groundtruth.txt` | `scan_constitute_egypt_2014_en_200dpi.pdf` | 23,965 | out_of_flow |
| `scan_constitute_egypt_2019_ar_150dpi.groundtruth.txt` | `scan_constitute_egypt_2019_ar_150dpi.pdf` | 20,763 | unreliable |
| `scan_eg_constitution_2014_en_150dpi.groundtruth.txt` | `scan_eg_constitution_2014_en_150dpi.pdf` | 10,635 | logical |
| `scan_eg_official_gazette_excerpt_300dpi.groundtruth.txt` | `scan_eg_official_gazette_excerpt_300dpi.pdf` | 12,453 | logical |
| `scan_wipo_eg081ar_1_300dpi.groundtruth.txt` | `scan_wipo_eg081ar_1_300dpi.pdf` | 7,103 | logical |
| `scan_wipo_eg088ar_1_150dpi.groundtruth.txt` | `scan_wipo_eg088ar_1_150dpi.pdf` | 8,316 | logical |

> **Derived scans remain an optimistic bound on real-world OCR.** A rasterized digital PDF has clean glyph rendering and no scanner optics, photocopy generations, bleed-through, staple shadows or marginalia. Scans made on real office hardware will score worse. This is a permanent property of validating without firm data, not a gap that later data closes.

## Reference text for the non-OCR path

Built by `scripts/make_text_ground_truth.py`: 8 pages across 5 documents. This is what makes text-layer extraction accuracy measurable; before it existed, the majority path through the pipeline had no number at all.

**The reference is never the PDF's own text layer.** That is circular -- reading the text layer is the thing being measured -- and on Arabic it is wrong: the public Arabic PDFs here store presentation forms in visual order and reverse digit runs (`wipo_eg088ar_1.pdf` page 3 renders `٢٠٢٣` and extracts `٣٢٠٢`). Such a reference would penalise the pipeline for repairing the damage correctly.

| Reference | Document | Scope | Pages | Provenance |
|---|---|---|---|---|
| `synthetic_contract_bilingual.reference.txt` | `synthetic_contract_bilingual.pdf` | document | 3 | authored |
| `stress_nested_clauses_ar.reference.txt` | `stress_nested_clauses_ar.pdf` | page | 1 | authored |
| `stress_inline_bilingual.reference.txt` | `stress_inline_bilingual.pdf` | page | 1 | authored |
| `stress_exhibits_footnotes.reference.txt` | `stress_exhibits_footnotes.pdf` | page | 1 | authored |
| `eg_official_gazette_excerpt.p2.reference.txt` | `eg_official_gazette_excerpt.pdf` | page | 1 | transcribed |
| `eg_official_gazette_excerpt.p3.reference.txt` | `eg_official_gazette_excerpt.pdf` | page | 1 | transcribed |

## Coverage against the spec's required inputs

| Required input | Covered by |
|---|---|
| Text-based PDF | all `public/*.pdf`, `synthetic_contract_bilingual.pdf` |
| Scanned (image-based) PDF | `scan_*.pdf` (11 files, all with ground truth) |
| DOCX | `synthetic_contract_ar.docx`, `synthetic_lease_bilingual.docx` |
| TXT | `synthetic_statute_ar.txt`, `synthetic_memo_mixed.txt`, `synthetic_visual_order_ar.txt` |
| Image | `synthetic_stamped_page.png`, `synthetic_table_page.png`, `stress_table_*.png` |
| Pure Arabic | `constitute_egypt_*_ar.pdf`, `wipo_*.pdf`, `synthetic_statute_ar.txt` |
| Pure English | `constitute_egypt_2014_en.pdf`, `eg_constitution_2014_en.pdf` |
| Mixed Arabic/English | `synthetic_contract_bilingual.pdf`, `synthetic_lease_bilingual.docx`, `synthetic_memo_mixed.txt` |
| Tables (ruled) | `synthetic_contract_ar.docx`, `stress_table_ruled_ar.png` |
| Tables (borderless) | `synthetic_contract_bilingual.pdf`, `synthetic_table_page.png`, `stress_table_wide_en.png` |
| Tables (sparse / empty cells) | `stress_table_sparse_bilingual.png` |
| Table across a page break | `stress_table_pagebreak.pdf` |
| Multi-column layout | `constitute_egypt_*.pdf` |
| Marginal annotation column | `constitute_egypt_*.pdf` (the cause of their inflated CER; see the reference audit) |
| Stamps / signatures | `synthetic_stamped_page.png` |
| Damaged reading order | `synthetic_visual_order_ar.txt`, `synthetic_contract_bilingual.pdf` |
| Deeply nested clause numbering (5.2.1.b.ii) | `stress_nested_clauses_ar.pdf` |
| Arabic/English alternating mid-sentence | `stress_inline_bilingual.pdf`, `synthetic_memo_mixed.txt` |
| Exhibits, appendices, schedules, footnote markers | `stress_exhibits_footnotes.pdf` |
| Scan quality curve (300 dpi clean -> 150 dpi degraded) | `bench_*_clean/poor.pdf`, `scan_authored_*_300dpi/150dpi.pdf` |

## Permanent limits of this corpus

The engagement constraint is that no document leaves the firm, so this system is validated on public and synthetic material **by design**. The list below is therefore not a backlog. These are properties of the validation approach, and they will still be true after the system is in production -- they bound what the numbers in the evaluation report can be read to mean.

- **No genuine scans.** Every 'scanned' fixture is a rendered page, not paper through a scanner: no feeder skew, no photocopy generations, no bleed-through, no staple shadows. Measured OCR accuracy is an optimistic bound and should be read as one.
- **No handwriting.** The one handwritten public document available was excluded as unscoreable (see the exclusions table). Handwritten margin notes and initials are not supported by either engine as configured, and this corpus cannot measure how badly they fail.
- **No firm house style.** Letterhead, numbering conventions, defined-term formatting and clause phrasing are unknown. The structure detector's cue lists were written against published statutes and synthetic contracts; retuning them against the firm's own drafting is expected work, not a defect.
- **No multi-document bundles.** Court files arrive as one PDF containing many instruments; document-type inference assumes one type per file and will label the bundle by whichever instrument dominates.
- **No password-protected or corrupt files.** Detection reports them, but no end-to-end behaviour is tested.
- **No pre-Unicode or fax-quality typesetting.**

Two of these are closable **by the firm, on the firm's own hardware, without sending anything anywhere**: point `scripts/evaluate.py --corpus-dir` at a directory of real documents and the same report regenerates against them. That is a capability the system provides, not a dependency it has.


## How to read the "expected quirks" column

Each file was built or chosen to exercise a specific failure mode. A quirk is
**a property of the file**, not a known bug: when the pipeline flags something
on one of these documents, that is usually the correct behaviour being
demonstrated.
