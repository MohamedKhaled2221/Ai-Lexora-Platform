# M3 Known Issues

Open, scoped, and deliberately **not** fixed. Each entry states what was
measured, how far it reaches, and roughly what a fix would involve. Nothing
here is speculative — every number was read off the live `legal_documents_v2`
collection on 2026-09-08.

---

## ISSUE-1: Reversed RTL digit order defeats article extraction

**Status:** open, not fixed. Needs a deliberate regex design decision, not a
patch.
**Severity:** medium — silent loss of exact-identifier retrieval for one whole
document.
**Owner:** unassigned (M3, with an M2 sign-off on the pattern).

### The pattern

`QueryProcessor.ARTICLE_RE` expects the number to **follow** the keyword:

```
\b(?:article|art\.?|المادة|مادة)\s*[-:#]?\s*([0-9٠-٩]+)\b
```

Text extracted from `constitute_egypt_2019_ar.pdf` puts the number **before**
it. The PDF's RTL text runs were emitted in visual rather than logical order,
so `المادة 204` came out as `204 المادة`.

Real examples, verbatim from the live payloads:

| chunk | text fragment |
|---|---|
| `chunk_144` | `... القضاء .الثالث الفرع  204 المادة.  كافة في بالفصل غيره دون يختص ...` |
| `chunk_104` | `... نوابه احد او ،الوزراء مجلس.  134 المادة. رئيس الي ،عاج بيا نا او احاطة طلب ...` |
| `chunk_116` | `... الستفتاءات  157 المادة.  بمصالح تتصل التي المسائل في لالس ...` |
| `chunk_038` | `... 20 99 المادة. . . . . . . . . ...` (contents line) |

Note the whole line is reversed, not just the number — `الفرع الثالث` appears
as `الثالث الفرع`. This is a text-extraction ordering problem that surfaces as
a regex miss; it is not a digit-encoding problem.

### Measured reach

Counting `<number> المادة` (reversed) against `المادة <number>` (normal) across
all 1,945 live chunks:

| document | chunks | reversed | normal | article_no populated |
|---|---|---|---|---|
| `doc_0422a112599d` (2019 constitution, AR) | 279 | **306** | **0** | **0 / 279** |
| `doc_e88a137f4d25` (IP authority law) | 27 | 12 | 36 | 21 |
| `doc_7983400b1672` (WIPO eg081ar) | 279 | 1 | 465 | 251 |
| all other documents | — | 0 | — | — |

- **279 chunks (14.3% of the collection) carry zero article identifiers** and
  are unreachable by exact identifier search. They remain fully reachable by
  dense and sparse retrieval, so this is a precision loss on citation lookups,
  not a disappearance.
- Two other documents are lightly contaminated (13 occurrences total) and are
  *mostly* fine, which matters: a fix must not assume a document is either
  wholly reversed or wholly clean.

### Why it was not fixed here

Widening the pattern to accept a leading number is a two-line change and a bad
idea unmeasured. `([0-9٠-٩]+)\s*المادة` would match the trailing page number of
every contents line in the corpus (`20 99 المادة` → article "20" as well as
"99"), and article numbers already sit next to page numbers, cross-references
and dates. The change belongs with M2, whose extraction contract it is, and it
needs to be measured against false positives across the whole corpus rather
than against the one document it is meant to rescue.

### Sketch of a fix (for a future session)

1. Decide where it belongs. Extraction is M2's contract, so a widened
   `ARTICLE_RE` is M2's call. A retrieval-side alternative already exists as
   precedent: `src/retrieval/identifiers.py::_SUBJECT_DECLARATION` is a
   deliberately more permissive pattern used for *ranking only*, so
   the indexed payload keeps M2's definition.
2. Detect reversal per document rather than globally — compare reversed vs
   normal occurrence counts, as the table above does. A document scoring
   `reversed >> normal` gets the alternate pattern; the other 18 do not.
3. Guard against contents lines. The leader-dot detector already built for
   ranking (`identifiers.is_contents_line`, ≥20% `.` characters, measured
   bimodal with an empty 10–20% band) removes the largest false-positive class
   before extraction rather than after.
4. Re-run `scripts/backfill_identifiers.py` — payload-only, no re-embedding,
   already proven on 1,120 points.
5. Add the affected chunks as identifier cases in
   `evaluation/benchmark_cases_v2.json`. There are deliberately **none** today,
   because writing cases against a document whose identifiers cannot be
   extracted would have baked the defect into the ground truth.

### Related

`evaluation/benchmark_cases_v2.json` → `adv_contract_article_4_vs_definitions`
fails for the same underlying reason in a different guise: its ground-truth
chunks head with `المادة (4)` — parenthesised — which `ARTICLE_RE` also does
not match, so those chunks carry no `article_no` and are reachable only
semantically. Any fix should cover the parenthesised form as well as the
reversed one.

---

## ISSUE-2: RRF weights remain unvalidated

**Status:** open. A recommendation exists; production defaults are unchanged
pending a human decision.

Current defaults `dense 0.9 / keyword 0.1 / identifier 1.0`. A 27-combo grid
over the 32 scorable cases in `benchmark_cases_v2.json` produced a best
full-coverage combo of `0.5 / 0.1 / 2.0` (MRR 0.683 vs 0.671).

**That result did not validate.** A stratified split of the 32 cases into two
halves picked *different* winners (`0.5/0.1/2.0` on one half, `0.9/0.3/1.0` on
the other), and the disagreement between halves (~0.10 MRR) is several times
larger than the improvement being chased (~0.012 MRR). The eval set is too
small to choose between these combos.

One finding *is* robust across every split and every combo: **identifier
weight 0.0 is clearly worse** — coverage drops from 32/32 to 28/32 and MRR from
~0.67 to ~0.55. The identifier path earns its place; its exact weight does not
yet have an answer.

Fix: grow the eval set (60–100 cases, weighted toward semantic and adversarial)
before revisiting.

---

## ISSUE-3: Arabic thousands separator defeats monetary extraction

**Status:** resolved in M2.

`IdentifierPreserver.NUMBER` now accepts both the ASCII
thousands separator `,` and Arabic U+066C `٬`, and the
money extractor supports currency-code prefixes. The
historical notes below describe the pre-fix behavior.
**Severity:** medium — every genuine monetary amount in the corpus is
unreachable by exact value lookup, and was briefly indexed *wrongly*.
**Owner:** unassigned (M2 owns the pattern; M3 consumes it).
**Found:** 2026-09-09, while wiring `ProcessedQuery.identifiers.monetary_values`
into retrieval.

### The pattern

`QueryProcessor.MONEY_RE` accepts ASCII `,` as the only thousands separator:

```
(?:[$€£]\s?[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s?(?:EGP|USD|EUR|GBP|جنيه|دولار|يورو))
```

The Egyptian contracts in this collection write amounts with **U+066C ARABIC
THOUSANDS SEPARATOR** (`٬`), not ASCII comma. The character class does not
match it, so extraction starts at the last separator and returns only the
final group.

Verbatim from the live payloads:

| document / chunk | source text | M2 extracts | true value |
|---|---|---|---|
| `doc_7f50f934ecc4` `chunk_005` | `قيمة هذا العقد بمبلغ اجمالي وقدره 2٬450٬000 جنيه مصري` | `"000 جنيه"` | 2,450,000 EGP |
| `doc_694f11671c02` `chunk_006` | same schedule, near-duplicate contract | `"000 جنيه"` | 2,450,000 EGP |
| `doc_041cd3837c44` `chunk_007` | `الاجرة السنوية مبلغ 480٬000 جنيه مصري` | `"000 جنيه"` | 480,000 EGP |

### Why this was worse than a miss

Normalized naively, all three become the key `EGP:0` — so a wrong amount, and
the **same** wrong amount on three unrelated agreements, silently joining a
2.45 M supply contract to a 480 K lease. `normalize_money` therefore refuses
zero amounts (as `normalize_article_number` refuses article 0), turning a wrong
answer into an absent one. The three `EGP:0` keys were written once during
backfill and have been deleted from the live collection.

### Measured reach

Running M2's extractor over all 1,945 live chunks:

- **3 chunks** contain a genuine monetary amount. All three are mis-extracted.
- **4 chunks** yield money keys that survive normalization (`GBP:2`, `GBP:4`
  ×2, `USD:2`, `USD:4`) — all from `doc_9a12cb861d01`, which is OCR failure
  (`REY RAP I ie PP ore hare IP pee Ik Key`), not currency. These are the only
  `money_no` values in the live index.
- **Net: zero real amounts are retrievable by value today.**

A second gap, same pattern, independent of the separator: a currency **prefix**
in code form is not matched at all — `EGP 3,000,000` and `USD 2,000` return
nothing, because the alternation allows a prefix only for the symbols `$€£`.
And the payment-schedule tables (`| 735,000 |`) carry no adjacent currency
token, so they are not matched either, correctly.

### What a fix involves

Widening the character class to `[\d,٬]` (and `[.٫]` for decimals) fixes the
truncation; adding a currency-code prefix alternative fixes `EGP 3,000,000`.
Both are M2 changes and alter what is extracted on **every** query and every
indexed chunk, so they need M2's sign-off and a re-run of `backfill_identifiers.py`.

Deliberately **not** worked around in M3. `src/retrieval/identifiers.py` folds
U+066C in `normalize_money`, so this layer is correct the moment extraction is
— but re-extracting from raw text inside M3 would put a second money pattern in
the codebase, and the index side and query side would then drift silently.
That is the precise failure the `identifiers` module docstring argues against
for article numbers.

### Consequence for the retrieval feature

Dates and monetary values are both wired through the identifier path
(`date_no`/`date_ref`, `money_no`/`money_ref`, KEYWORD-indexed, fused via RRF).
The **date half is live and measured** — 17 chunks indexed, 4 benchmark cases
in `benchmark_cases_v2.json`, all at rank 1. The **money half is wired and
unit-tested but unverified against this corpus**, and no monetary benchmark
case exists, because authoring one would mean asserting behaviour that is wrong
upstream.
