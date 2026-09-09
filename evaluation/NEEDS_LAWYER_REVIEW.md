# Cases needing legal review before production ground truth

Generated 2026-09-08 against live `legal_documents_v2` (1945 points).

**4 of 37 cases** are flagged. The other 33 are factual or structural (e.g. "does this chunk contain the text of Article 9") and were verified by reading the chunk directly - those need no legal sign-off.

Everything below is a judgment about legal correctness or completeness, which is not mine to make.

---

## `sem_memo_recommendation`  (semantic, ar)

**Query:** ما هي توصية المذكرة القانونية بشان بند تسوية المنازعات؟

**Proposed ground truth:**

- `doc_094209645c75` / `chunk_003`
- `doc_094209645c75` / `chunk_004`

**Why it needs review:** chunk_003 proposes replacing the North Cairo forum with CRCICA arbitration; chunk_004 is the formal recommendation not to sign before amending clauses 5, 6 and 8. Which chunk is 'the' recommendation, and whether both belong in ground truth, is an editorial/legal judgment.

---

## `sem_press_freedom`  (semantic, en)

**Query:** What does the Egyptian constitution guarantee regarding freedom of the press?

**Proposed ground truth:**

- `doc_6450dfd093f8` / `chunk_145`

**Why it needs review:** chunk_145 is the Article 70 body text. Article 71 (chunk_146, prohibition on censorship/confiscation) is arguably part of a complete answer. Whether the correct ground truth is Article 70 alone needs legal judgment.

---

## `adv_contract_article_4_vs_definitions`  (adversarial, en)

**Query:** Article 4 execution period of the agreement

**Proposed ground truth:**

- `doc_694f11671c02` / `chunk_007`
- `doc_7f50f934ecc4` / `chunk_006`

**Why it needs review:** Article 1 (Definitions, chunk_013/chunk_012) is tagged article_no ['1','4'] because it says 'Execution Period means the period specified in Article 4'. The substantive Article 4 text exists only in the ARABIC chunks. Whether the English definitions chunk is an acceptable answer for an English query is a judgment call.

---

## `neg_environmental_impact`  (negative, ar)

**Query:** ما هي اجراءات تقييم الاثر البيئي المطلوبة قبل الترخيص للمشروعات الصناعية؟

**Proposed ground truth:** _(empty - asserted to have no answer in this corpus)_

**Why it needs review:** Verified absent as a procedure: zero occurrences of 'environmental impact' or 'تقييم الاثر البيئي'. FLAGGED: the 2014 constitution does contain a general environmental-protection provision adjacent to Article 43, so a lawyer should confirm that 'no answer' is the right label rather than 'partial answer'.

---

