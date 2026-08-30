"""Does the 150 dpi result hold on genuinely 300 dpi material, and on small print?

``reports/arabic_preprocess_sweep.md`` found that rendering scans at 150 dpi
reads Arabic better than the pipeline's previous 300 dpi default. That report
also named the two things which could make the finding narrower than it looks,
and this script exists to test both of them rather than leave them as caveats:

1. **Half the sweep corpus is natively 150 dpi**, so for those fixtures a 300
   dpi render was pure upsampling -- interpolating pixels that carry no
   information. If that were the whole effect, the win should vanish on scans
   whose raster really is 300 dpi.

2. **The sweep's print is ~11 pt.** Downscaling costs nothing when glyphs are
   large. Small print is where losing pixels should hurt, and Arabic small print
   most of all: the dots separating ب ت ث are a couple of pixels across at 8 pt
   and 150 dpi.

METHOD
======

Fresh authored fixtures, generated here rather than reused: new Arabic legal
text, painted onto a **2480x3508 page -- a true 300 dpi A4** -- at four print
sizes from 7 pt to 14 pt, then degraded like a real scan. The reference is
authored, so it is correct by construction and carries none of the
visual-order/fragmentation defects that afflict references derived from a
publisher's text layer.

Then the same resolution ladder the sweep used, scored the same way, per print
size. What matters is not the absolute CER (this is new material, so it is not
comparable with 0.130) but **where each curve puts its minimum**.

These fixtures are written with a ``probe_`` prefix and are deliberately NOT
added to any manifest: they answer one question and must not silently join the
corpus that other reports average over.

Run::

    python scripts/dpi_probe_300.py
    python scripts/dpi_probe_300.py --keep      # leave the fixtures on disk
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from evaluate import _split_by_script, bag_error, cer  # noqa: E402
from make_synthetic_corpus import _degrade, _pil_font, rtl_render  # noqa: E402

from src.config import REPORTS_DIR, SYNTHETIC_CORPUS_DIR, PipelineConfig  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.ocr_pipeline import render_pdf_page, run_tesseract  # noqa: E402

# The ladder from the sweep, trimmed at the ends -- 75 dpi was already shown to
# be past the cliff, and above 400 dpi nothing improved.
LADDER = [100, 125, 150, 175, 200, 250, 300, 400]

# Print sizes in points. 11 pt is what the existing authored fixtures use and is
# ordinary legal body text; 7 pt is the footnote/schedule size where any
# downscale should hurt most, and is the real test of the recommendation.
POINT_SIZES = [7, 9, 11, 14]

# A true 300 dpi A4 raster. Every probe fixture is generated at this size,
# whatever the print size -- that is the point: the *paper* is 300 dpi and only
# the type gets smaller.
NATIVE_W, NATIVE_H = 2480, 3508

# Mild, realistic degradation. Deliberately gentler than the corpus's "poor"
# level: a heavily degraded page would confound print size with noise, and the
# question here is about resolution and type size.
DEGRADE = (0.4, 4, 0.35, 88)   # skew deg, noise sigma, blur, JPEG quality


# New text, not reused from the corpus, so this is independent material.
PROBE_PAGES = [
    """قانون تنظيم التعاقدات العامة

المادة الأولى
تسري أحكام هذا القانون على العقود التي تبرمها الجهات الخاضعة لأحكامه، وعلى
وجه الخصوص عقود التوريد والمقاولات والخدمات الاستشارية، أياً كانت قيمتها.

المادة الثانية
يقصد بالجهة المتعاقدة كل وزارة أو مصلحة أو هيئة عامة أو وحدة من وحدات
الإدارة المحلية، وكذلك الشركات التي تساهم الدولة في رأس مالها بنسبة تجاوز
واحداً وخمسين في المائة.

المادة الثالثة
يجب أن تتم التعاقدات وفقاً لمبادئ العلانية وتكافؤ الفرص والمساواة وحرية
المنافسة، وبما يحقق أفضل قيمة مقابل الإنفاق العام.

المادة الرابعة
تلتزم الجهة المتعاقدة بنشر إعلان الطرح في البوابة الإلكترونية المخصصة لذلك
قبل الموعد المحدد لفتح المظاريف بخمسة عشر يوماً على الأقل، ويجوز خفض هذه
المدة إلى سبعة أيام في حالات الاستعجال المسببة كتابة.

المادة الخامسة
لا يجوز تجزئة الارتباط بقصد التهرب من قواعد الاختصاص المقررة في هذا القانون،
ويقع باطلاً كل تصرف يخالف ذلك.""",
    """المادة السادسة
تشكل لجنة البت بقرار من السلطة المختصة، وتضم في عضويتها مندوباً عن الشئون
القانونية ومندوباً عن الشئون المالية، ولا يكون انعقادها صحيحاً إلا بحضور
أغلبية أعضائها.

المادة السابعة
يودع مقدم العطاء تأميناً مؤقتاً لا يقل عن واحد في المائة ولا يزيد على اثنين
في المائة من القيمة التقديرية، ويرد التأمين خلال خمسة عشر يوماً من تاريخ
البت في العطاءات لمن لم يرس عليه التعاقد.

المادة الثامنة
لا يجوز للمتعاقد التنازل عن العقد أو عن جزء منه للغير إلا بموافقة كتابية
مسبقة من الجهة المتعاقدة، وإلا جاز فسخ العقد ومصادرة التأمين النهائي.

المادة التاسعة
تسري على المنازعات الناشئة عن تنفيذ هذا العقد أحكام قانون التحكيم رقم سبعة
وعشرين لسنة أربع وتسعين، ويكون مقر التحكيم مدينة القاهرة.

المادة العاشرة
ينشر هذا القانون في الجريدة الرسمية، ويعمل به من اليوم التالي لتاريخ نشره.""",
]


def _px(points: float) -> int:
    """Point size -> pixel size on a 300 dpi page."""
    return max(6, round(points / 72.0 * 300))


def render_probe(dest: Path, points: int) -> tuple[Path, Path]:
    """Write one probe fixture: authored Arabic at ``points`` on 300 dpi paper."""
    import fitz
    from PIL import Image, ImageDraw

    size_px = _px(points)
    margin = _px(54)          # a 0.75 inch margin, whatever the type size
    outdoc = fitz.open()
    for page_text in PROBE_PAGES:
        img = Image.new("RGB", (NATIVE_W, NATIVE_H), (253, 252, 248))
        dr = ImageDraw.Draw(img)
        font = _pil_font(size_px)
        y = margin
        for line in page_text.splitlines():
            if not line.strip():
                y += size_px
                continue
            shaped = rtl_render(line)
            w = dr.textlength(shaped, font=font)
            dr.text((NATIVE_W - margin - w, y), shaped, font=font, fill=(18, 18, 18))
            y += int(size_px * 1.55)
        img = _degrade(img, *DEGRADE)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=DEGRADE[3])
        page = outdoc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buf.getvalue())

    pdf = dest / f"probe_dpi_ar_{points}pt_300dpi.pdf"
    gt = dest / f"probe_dpi_ar_{points}pt_300dpi.groundtruth.txt"
    outdoc.save(str(pdf))
    outdoc.close()
    gt.write_text("\f".join(PROBE_PAGES), encoding="utf-8")
    return pdf, gt


def score(pdf: Path, gt: Path, dpi: int, config: PipelineConfig) -> dict:
    """OCR every page of ``pdf`` at ``dpi`` and score Arabic against ``gt``."""
    import fitz

    doc = fitz.open(pdf)
    collected, seconds, errors = [], 0.0, 0
    try:
        for i in range(doc.page_count):
            t0 = time.perf_counter()
            try:
                img, scale = render_pdf_page(doc[i], dpi, 0)
                res = run_tesseract(img, i + 1, scale, config.ocr)
                text, err = res.text, res.error
            except Exception as exc:  # noqa: BLE001
                text, err = "", f"{type(exc).__name__}: {exc}"
            seconds += time.perf_counter() - t0
            errors += bool(err)
            collected.append(text)
    finally:
        doc.close()

    reference, _ = normalize_text(gt.read_text(encoding="utf-8"), config.normalization)
    hypothesis, _ = normalize_text("\n".join(collected), config.normalization)
    ref_ar, _ = _split_by_script(reference)
    hyp_ar, _ = _split_by_script(hypothesis)
    return {
        "dpi": dpi,
        "cer": cer(ref_ar, hyp_ar, ignore_spaces=True),
        "bag": bag_error(ref_ar, hyp_ar),
        "seconds_per_page": round(seconds / max(len(collected), 1), 2),
        "errors": errors,
    }


def build_report(results: dict[int, list[dict]], elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Does the 150 dpi finding hold on true 300 dpi scans, and on small print?")
    add("")
    add("> Follow-up to [`arabic_preprocess_sweep.md`](arabic_preprocess_sweep.md), "
        "testing the two caveats that report raised about its own result.")
    add("")
    add("**The concern.** Half the sweep corpus is natively 150 dpi, so a 300 dpi "
        "render was upsampling it -- interpolating pixels carrying no "
        "information. If that were the whole story, 150 dpi should stop winning "
        "on genuinely 300 dpi scans. And the sweep's print is ~11 pt, where "
        "throwing away pixels is cheap; small print is where it should hurt.")
    add("")
    add("**The fixtures.** New authored Arabic legal text (not reused from the "
        "corpus), painted onto a **true 300 dpi A4 raster (2480x3508)** at four "
        "print sizes, then degraded like a scan (0.4 deg skew, sigma-4 noise, "
        "0.35 px blur, JPEG q88). The reference is authored -- written before "
        "the pixels existed -- so it carries none of the publisher defects that "
        "inflate absolute CER elsewhere in this project.")
    add("")
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Wall clock: {elapsed / 60:.1f} min | Tesseract, CPU")
    add("")

    add("## The curves")
    add("")
    add("CER (space-insensitive) per render DPI, per print size. **The paper is "
        "300 dpi in every column** -- only the type gets smaller.")
    add("")
    sizes = sorted(results)
    add("| Render DPI | " + " | ".join(f"{s} pt" for s in sizes) + " |")
    add("|---" * (len(sizes) + 1) + "|")
    for dpi in LADDER:
        cells = []
        for s in sizes:
            row = next((r for r in results[s] if r["dpi"] == dpi), None)
            value = row["cer"] if row else None
            best = min((r["cer"] for r in results[s] if r["cer"] is not None),
                       default=None)
            if value is None:
                cells.append("n/a")
            elif best is not None and abs(value - best) < 1e-9:
                cells.append(f"**{value:.3f}**")
            else:
                cells.append(f"{value:.3f}")
        add(f"| {dpi}" + (" **(shipped)**" if dpi == 150 else
                          " *(previous default)*" if dpi == 300 else "")
            + " | " + " | ".join(cells) + " |")
    add("")
    add("Bold marks the best rung for that print size.")
    add("")

    add("## Verdict")
    add("")
    for s in sizes:
        scored = [r for r in results[s] if r["cer"] is not None]
        if not scored:
            add(f"- **{s} pt:** not scored (reference too short after splitting).")
            continue
        best = min(scored, key=lambda r: r["cer"])
        at150 = next((r for r in scored if r["dpi"] == 150), None)
        at300 = next((r for r in scored if r["dpi"] == 300), None)
        if at150 and at300:
            delta = at300["cer"] - at150["cer"]
            verdict = ("150 dpi still wins" if delta > 0.01 else
                       "**300 dpi wins**" if delta < -0.01 else
                       "the two are level")
            add(f"- **{s} pt:** best rung {best['dpi']} dpi (CER "
                f"{best['cer']:.3f}). 150 dpi {at150['cer']:.3f} vs 300 dpi "
                f"{at300['cer']:.3f} -- {verdict} ({delta:+.3f}).")
    add("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true",
                        help="leave the probe fixtures on disk for inspection")
    parser.add_argument("--out", default=str(REPORTS_DIR / "dpi_probe_300.md"))
    parser.add_argument("--json", default=str(REPORTS_DIR / "dpi_probe_300.json"))
    args = parser.parse_args()

    config = PipelineConfig()
    config.ocr.preprocess.enabled = False
    dest = SYNTHETIC_CORPUS_DIR
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    made: list[tuple[Path, Path]] = []
    results: dict[int, list[dict]] = {}
    start = time.perf_counter()
    try:
        for points in POINT_SIZES:
            pdf, gt = render_probe(dest, points)
            made.append((pdf, gt))
            print(f"\n{points} pt on 300 dpi paper ({_px(points)} px type) "
                  f"-> {pdf.name}", flush=True)
            results[points] = []
            for dpi in LADDER:
                row = score(pdf, gt, dpi, config)
                results[points].append(row)
                mark = " <- shipped" if dpi == 150 else (
                    " <- previous default" if dpi == 300 else "")
                print(f"    render {dpi:>3} dpi  CER="
                      f"{row['cer'] if row['cer'] is not None else 'n/a':<8} "
                      f"bag={row['bag']}  {row['seconds_per_page']}s/pg{mark}",
                      flush=True)
    finally:
        if not args.keep:
            for pdf, gt in made:
                pdf.unlink(missing_ok=True)
                gt.unlink(missing_ok=True)

    elapsed = time.perf_counter() - start
    Path(args.json).write_text(json.dumps({
        "warning": "Synthetic authored fixtures. No firm document processed.",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "native_raster": f"{NATIVE_W}x{NATIVE_H} (300 dpi A4)",
        "degradation": {"skew_deg": DEGRADE[0], "noise_sigma": DEGRADE[1],
                        "blur": DEGRADE[2], "jpeg_quality": DEGRADE[3]},
        "results": {str(k): v for k, v in results.items()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out).write_text(build_report(results, elapsed), encoding="utf-8")
    print(f"\nReport : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
