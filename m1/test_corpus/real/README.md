# `test_corpus/real/` -- your own documents

**Empty, and the system is validated without it.** The engagement constraint is
that no document leaves the firm, so M1 was built and measured against
published Egyptian legal documents and synthetic fixtures. The numbers in
`reports/evaluation_report.md` stand on their own; nothing here is a
placeholder for a missing input.

This directory exists so the firm can run the same evaluation against its own
material **on its own hardware, with nothing leaving the building**:

```bash
cp /path/to/your/documents/* test_corpus/real/
python scripts/evaluate.py --corpus-dir test_corpus/real
```

No code changes. `--corpus-dir` recurses into subdirectories and accepts PDF,
DOCX, TXT and image files. The report's banner switches automatically to record
that a supplied corpus was used.

## What this would tell you that the public corpus cannot

Three things, all named as permanent limits in the main README:

1. **OCR accuracy on real paper.** Every scanned fixture in the corpus is a
   rendered page degraded with skew, noise and JPEG artifacts. That models
   compression and geometry, not scanner optics, photocopy generations,
   bleed-through or staple shadows. The reported OCR figures are an optimistic
   bound; only your own scans can say by how much.
2. **Whether the structure cues match your house style.** The marker patterns
   were written against published statutes and synthetic contracts. Your
   numbering conventions and defined-term formatting will differ in ways that
   are cheap to add once seen.
3. **Whether the OCR engine ordering holds.** Tesseract is primary on the
   evidence in `reports/ocr_engine_comparison.md`. Rendered pages and scanner
   output are not the same input, and the two engines may not degrade at the
   same rate.

## Before you put anything here

- **Confirm the documents are anonymized** if that matters for your use.
  Nothing in this repo redacts client names, national ID numbers, or matter
  references. The pipeline reproduces whatever it is given, including into
  `metadata.raw_text`.
- **This directory is git-ignored** apart from this README. Check that before
  the first real file lands.
- **Everything stays local.** No stage contacts the network at runtime — but
  model weights *are* downloaded on first use, so complete provisioning (see
  the main README's setup section) before loading firm material.

## Ground truth (optional, and the highest-value thing you can add)

If you can produce a correct plain-text transcription of any scanned document,
save it beside the file as `<name>.groundtruth.txt`. The harness picks it up
automatically and reports character and word error rates split by Arabic and
English.

Three or four transcribed pages spanning your worst scan quality are worth far
more than a large untranscribed batch: they turn "OCR produced plausible
output" into a number, on exactly the material that matters.

The corpus already contains fixtures with this property — `scan_authored_*.pdf`,
whose reference text was written before the page was rendered — which is why an
Arabic OCR figure can be quoted at all. What they cannot supply is *your*
scanner and *your* archive's condition.
