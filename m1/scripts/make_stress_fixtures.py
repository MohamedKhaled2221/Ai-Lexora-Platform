"""Second-wave fixtures: table variety, layout edge cases, and more scanned pages.

The first corpus established that the pipeline runs. These fixtures exist to
break it, and to make three measurements possible that previously were not.

WHAT THIS ADDS AND WHY
======================

**Image-based tables (``stress_table_*.png``).** ``synthetic_table_page.png``
was the only image table in the corpus, it was missed, and one fixture cannot
tell a fix from a coincidence. Three more, deliberately varied: fully ruled,
borderless and wide, and sparse with empty cells. A table reconstructor that
only works on evenly-filled grids will pass the first and fail the third.

**Layout edge cases (``stress_*.pdf``).** Four documents built around the
specific things Egyptian legal drafting does that generic extraction gets
wrong: clause numbering five levels deep, a table split by a page break,
Arabic and English alternating *inside* one sentence rather than in parallel
columns, and numbered exhibits with footnote references.

**Scanned pages with authored ground truth (``scan_authored_*.pdf``).** Every
other scanned fixture derives its reference from a source PDF's text layer, and
``scripts/audit_ground_truth.py`` shows that reference is not always
trustworthy: the Constitute Project's Arabic PDFs store visual word order, so a
perfectly-read page scores ~0.70 CER. These fixtures invert the dependency --
the text is written here first, then painted onto a page, so the reference is
correct **by construction**. They are the only fixtures whose absolute OCR
accuracy needs no caveat about the reference.

EVERYTHING HERE IS FABRICATED
=============================

Party names, sums, dates and case numbers are invented. Nothing derives from a
real client matter. The statutory language imitates the register of Egyptian
legal drafting without reproducing any specific instrument.

Run::

    python scripts/make_stress_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import PUBLIC_CORPUS_DIR, SYNTHETIC_CORPUS_DIR  # noqa: E402

# Reuse the first generator's font handling, Arabic shaping and degradation, so
# these fixtures are visually consistent with the existing corpus and a change
# to the degradation model applies to both.
from make_synthetic_corpus import (  # noqa: E402
    ARABIC_FONT,
    _degrade,
    _pil_font,
    rtl_render,
)

MANIFEST: list[dict] = []


def record(name: str, **kw) -> None:
    MANIFEST.append({"file": name, **kw})


# ---------------------------------------------------------------------------
# 1. Image tables -- three shapes, to prove a table fix generalises
# ---------------------------------------------------------------------------

RULED_TABLE = [
    ["البند", "Item", "المبلغ (جنيه)"],
    ["أتعاب المرحلة الأولى", "Phase 1 fees", "180,000"],
    ["أتعاب المرحلة الثانية", "Phase 2 fees", "240,000"],
    ["مصروفات إدارية", "Administrative costs", "35,500"],
    ["الإجمالي", "Total", "455,500"],
]

WIDE_TABLE = [
    ["Ref", "Deliverable", "Owner", "Due", "Status", "Value (EGP)"],
    ["D-01", "Due diligence report", "Counsel", "2026-02-10", "Delivered", "120,000"],
    ["D-02", "Share purchase draft", "Counsel", "2026-03-05", "In review", "260,000"],
    ["D-03", "Regulatory filing", "Associate", "2026-04-18", "Pending", "95,000"],
    ["D-04", "Closing bundle", "Paralegal", "2026-05-30", "Not started", "48,000"],
    ["D-05", "Post-closing report", "Counsel", "2026-07-01", "Not started", "72,000"],
]

# Empty cells on purpose: a grid reconstructor that assumes every row fills
# every column will either drop rows or shift their contents one column left.
SPARSE_TABLE = [
    ["القضية", "Case", "الجلسة", "Outcome"],
    ["١٢٤٥/٢٠٢٥", "Nile Blue v. Delta", "2026-03-11", ""],
    ["", "Adjourned on request", "2026-04-22", "Adjourned"],
    ["١٣٠٩/٢٠٢٥", "Karnak Holdings", "", "Reserved"],
    ["١٤٠٢/٢٠٢٦", "", "2026-06-02", "Listed"],
]


def _table_image(rows, cols_x, width, height, title, ruled, y0=200, row_h=95):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (255, 254, 250))
    dr = ImageDraw.Draw(img)
    f_head = _pil_font(34, bold=True)
    f_body = _pil_font(28)

    shaped = rtl_render(title)
    dr.text((width / 2 - dr.textlength(shaped, font=f_head) / 2, 70), shaped,
            font=f_head, fill=(10, 10, 10))

    y = y0
    for r, row in enumerate(rows):
        font = f_head if r == 0 else f_body
        for x, cell in zip(cols_x, row):
            if cell:
                dr.text((x, y), rtl_render(str(cell)), font=font, fill=(15, 15, 15))
        if ruled:
            dr.line((cols_x[0] - 20, y - 18, width - 100, y - 18),
                    fill=(70, 70, 70), width=2)
        elif r == 0:
            dr.line((cols_x[0] - 20, y + 55, width - 100, y + 55),
                    fill=(60, 60, 60), width=3)
        y += row_h

    if ruled:
        dr.line((cols_x[0] - 20, y - 18, width - 100, y - 18), fill=(70, 70, 70), width=2)
        for x in list(cols_x) + [width - 100]:
            dr.line((x - 20, y0 - 18, x - 20, y - 18), fill=(70, 70, 70), width=2)
    return img


def make_table_images(dest: Path) -> None:
    specs = [
        (
            "stress_table_ruled_ar.png", RULED_TABLE, [140, 620, 1180], 1654, 800,
            "بيان الأتعاب - Fee Statement", True, -0.3, 4, 0.3, 82,
            "3-column FULLY RULED bilingual table",
            ["every cell is boxed -- the easy case, and the control against which "
             "the borderless fixtures are read",
             "Arabic label column, English label column, Western numerals"],
        ),
        (
            "stress_table_wide_en.png", WIDE_TABLE, [110, 340, 800, 1010, 1230, 1440],
            1754, 800, "Deliverables Schedule", False, 0.4, 6, 0.4, 78,
            "6-column BORDERLESS English table",
            ["six columns with narrow gutters -- tests whether cell splitting "
             "survives when the inter-column gap approaches the inter-word gap",
             "no ruling lines except one header rule"],
        ),
        (
            "stress_table_sparse_bilingual.png", SPARSE_TABLE, [140, 520, 1050, 1400],
            1654, 750, "جدول الجلسات - Hearing Schedule", False, -0.6, 8, 0.5, 72,
            "4-column table with EMPTY CELLS in every column",
            ["blank cells on purpose: a reconstructor that assumes full rows will "
             "shift contents into the wrong column rather than emit a gap",
             "Arabic-Indic numerals in the case column against Western numerals "
             "in the date column",
             "most degraded of the three (JPEG q72) -- tests the table geometry "
             "under recognition noise"],
        ),
    ]

    for (name, rows, cols_x, w, h, title, ruled,
         skew, noise, blur, q, structure, quirks) in specs:
        img = _table_image(rows, cols_x, w, h, title, ruled)
        img = _degrade(img, skew, noise, blur, q)
        img.save(dest / name)
        record(
            name, kind="synthetic", format="png (image)",
            language_mix="bilingual" if any(
                any("؀" <= c <= "ۿ" for c in str(cell)) for r in rows for cell in r
            ) else "English",
            structure=structure,
            tables_expected=1,
            expected_shape=[len(rows), len(rows[0])],
            quirks=quirks + [f"degraded: {skew} deg skew, noise {noise}, JPEG q{q}"],
            exercises=["OCR path", "table reconstruction from OCR geometry"],
        )
        print(f"  {name}  ({len(rows)}x{len(rows[0])} table)")


# ---------------------------------------------------------------------------
# 2. Layout edge cases
# ---------------------------------------------------------------------------

NESTED_CLAUSES = """عقد خدمات استشارية
Consultancy Services Agreement

المادة 5 - التزامات المستشار
Article 5 - Obligations of the Consultant

5.1 يلتزم المستشار بأداء الخدمات وفقاً للأصول المهنية المتعارف عليها.
5.1 The Consultant shall perform the Services in accordance with good professional practice.

5.2 نطاق الخدمات
5.2 Scope of Services

5.2.1 يشمل النطاق المراجعة القانونية للعقود القائمة.
5.2.1 The scope includes legal review of existing contracts.

5.2.1.a مراجعة عقود التوريد المبرمة قبل تاريخ النفاذ.
5.2.1.a Review of supply contracts concluded before the Effective Date.

5.2.1.b إعداد مذكرة بالمخاطر التعاقدية الجوهرية.
5.2.1.b Preparation of a memorandum on material contractual risks.

5.2.1.b.i تصنيف المخاطر حسب درجة الأثر المالي.
5.2.1.b.i Classification of risks by degree of financial impact.

5.2.1.b.ii اقتراح صيغ بديلة للبنود محل الاعتراض.
5.2.1.b.ii Proposal of alternative wording for the disputed clauses.

5.2.2 لا يشمل النطاق التمثيل أمام هيئات التحكيم.
5.2.2 The scope excludes representation before arbitral tribunals.

5.3 يقدم المستشار تقريراً شهرياً عن سير الأعمال.
5.3 The Consultant shall submit a monthly progress report.

المادة 6 - الأتعاب
Article 6 - Fees

6.1 تُحدد الأتعاب بمبلغ 455,500 جنيه مصري.
6.1 The fees are set at EGP 455,500.

6.1.1 تُسدد الأتعاب على أربع دفعات.
6.1.1 The fees shall be paid in four instalments.
"""

INLINE_BILINGUAL = """مذكرة داخلية - Internal Memorandum

إلى / To: إدارة الشؤون القانونية (Legal Affairs Department)
الموضوع / Subject: مراجعة عقد الإيجار التمويلي (finance lease) المبرم مع شركة Karnak Holdings

1. بمراجعة البند الثالث (Clause 3) من العقد تبين أن التزام المؤجر (the Lessor) بالصيانة الدورية
غير محدد المدة، وهو ما يخالف ما استقر عليه العمل في عقود الـ finance lease المصرية.

2. نوصي بإضافة عبارة "within thirty (30) days of written notice" إلى نهاية البند، مع مقابل
عربي صريح هو "خلال ثلاثين (30) يوماً من تاريخ الإخطار الكتابي"، حتى لا ينشأ خلاف حول
أي النصين هو المرجع (the governing text) عند التعارض.

3. البند الحادي عشر (Clause 11) يحيل إلى قانون رقم 95 لسنة 1995 بشأن التأجير التمويلي،
وهو قانون ملغى (repealed) بموجب القانون رقم 176 لسنة 2018، ويتعين تصحيح الإحالة.

4. من حيث اختصاص المحكمة (jurisdiction)، ينص العقد على التحكيم أمام مركز القاهرة الإقليمي
للتحكيم التجاري الدولي (CRCICA)، وهو اختيار مقبول، إلا أن عدد المحكمين (three arbitrators)
مبالغ فيه بالنظر إلى قيمة العقد البالغة 2,450,000 جنيه.

5. الخلاصة / Conclusion: العقد قابل للتوقيع (executable) بعد إجراء التعديلات المشار إليها
في البنود 2 و3 أعلاه.
"""

EXHIBITS_DOC = """SHARE PURCHASE AGREEMENT
اتفاقية شراء أسهم

Article 1 - Definitions
المادة 1 - التعريفات

1.1 "Completion Accounts" means the accounts prepared in accordance with
Exhibit A (Accounting Policies).[1]

1.2 "Disclosed Information" means the information listed in Appendix II
(Disclosure Letter) and the documents in the data room index at Exhibit C.[2]

Article 2 - Conditions Precedent
المادة 2 - الشروط الواقفة

2.1 Completion is conditional on the approvals listed in Schedule 1.[3]

2.2 The Seller shall deliver the documents specified in Exhibit B on or before
the Completion Date.

EXHIBIT A - ACCOUNTING POLICIES
الملحق أ - السياسات المحاسبية

A.1 The Completion Accounts shall be prepared on a going concern basis.
A.2 Inventory shall be valued at the lower of cost and net realisable value.

EXHIBIT B - CLOSING DELIVERABLES
الملحق ب - مستندات الإتمام

B.1 Executed share transfer forms.
B.2 Resignation letters of the outgoing directors.

APPENDIX II - DISCLOSURE LETTER
الملحق الثاني - خطاب الإفصاح

II.1 The Seller discloses the pending matter numbered 1245/2025.

SCHEDULE 1 - REGULATORY APPROVALS
الجدول 1 - الموافقات التنظيمية

S1.1 Egyptian Competition Authority clearance.
S1.2 General Authority for Investment notification.

--------------------------------------------------------------------------
[1] Exhibit A is incorporated by reference and forms part of this Agreement.
[2] Appendix II is qualified in its entirety by the data room index.
[3] Schedule 1 may be amended only by written agreement of both parties.
"""


def _text_pdf(dest: Path, name: str, title: str, body: str,
              page_break_after: int | None = None) -> None:
    """Render text to a real text-layer PDF with ReportLab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("ArabicBody", str(ARABIC_FONT)))
    c = canvas.Canvas(str(dest / name), pagesize=A4)
    width, height = A4
    y = height - 60
    c.setFont("ArabicBody", 10)

    for i, line in enumerate(body.splitlines()):
        if y < 60 or (page_break_after is not None and i == page_break_after):
            c.showPage()
            c.setFont("ArabicBody", 10)
            y = height - 60
        shaped = rtl_render(line)
        c.drawString(56, y, shaped)
        y -= 14
    c.save()


def make_edge_case_pdfs(dest: Path) -> None:
    _text_pdf(dest, "stress_nested_clauses_ar.pdf", "Nested clauses", NESTED_CLAUSES)
    record(
        "stress_nested_clauses_ar.pdf", kind="synthetic", format="pdf",
        pdf_type="text-based",
        language_mix="bilingual, parallel Arabic/English lines",
        structure="clause numbering five levels deep: 5, 5.2, 5.2.1, 5.2.1.b, 5.2.1.b.ii",
        expected_document_type="contract",
        quirks=[
            "deepest numbering in the corpus -- tests whether the structure "
            "detector builds a heading path rather than flattening every level "
            "to the same rank",
            "letter and roman sub-levels mixed with numeric ones (.a, .b.i)",
            "every clause appears twice, once per language, so a chunker that "
            "cuts on markers must not treat the English restatement as a new clause",
        ],
        exercises=["structure_preservation clause hierarchy", "chunking boundaries"],
    )
    print("  stress_nested_clauses_ar.pdf")

    _text_pdf(dest, "stress_inline_bilingual.pdf", "Inline bilingual", INLINE_BILINGUAL)
    record(
        "stress_inline_bilingual.pdf", kind="synthetic", format="pdf",
        pdf_type="text-based",
        language_mix="Arabic and English alternating WITHIN single sentences",
        structure="numbered memorandum paragraphs, no article markers",
        expected_document_type="correspondence",
        quirks=[
            "the hard bidi case: direction switches mid-sentence, several times "
            "per line, around parenthesised English glosses",
            "Latin terms embedded in Arabic clauses ('عقود الـ finance lease') -- "
            "language detection must return ar-en, not pick a winner",
            "quoted English inside Arabic inside brackets: nested direction runs",
        ],
        exercises=["rtl_fix mixed-direction flagging", "detect_language on bilingual text"],
    )
    print("  stress_inline_bilingual.pdf")

    _text_pdf(dest, "stress_exhibits_footnotes.pdf", "Exhibits", EXHIBITS_DOC)
    record(
        "stress_exhibits_footnotes.pdf", kind="synthetic", format="pdf",
        pdf_type="text-based",
        language_mix="English body with Arabic headings",
        structure="articles plus lettered exhibits, roman appendices, numbered "
                  "schedules, and bracketed footnote references",
        expected_document_type="contract",
        quirks=[
            "four parallel numbering systems in one document (Article 1.1, "
            "Exhibit A.1, Appendix II.1, Schedule S1.1) -- a detector keyed on "
            "one of them will mis-rank the others",
            "footnote markers [1][2][3] inline in clause text, with the footnote "
            "bodies collected at the end behind a rule",
            "annex headings appear after the operative text, so document order "
            "and clause-id order diverge",
        ],
        exercises=["structure_preservation on annexes", "chunking of exhibit blocks"],
    )
    print("  stress_exhibits_footnotes.pdf")


def make_pagebreak_table_pdf(dest: Path) -> None:
    """A table whose rows continue across a page boundary."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdfmetrics.registerFont(TTFont("ArabicBody", str(ARABIC_FONT)))
    style = ParagraphStyle("body", fontName="ArabicBody", fontSize=10, leading=14)

    rows = [["#", "Instalment / الدفعة", "Due date", "Amount (EGP)"]]
    for i in range(1, 29):
        rows.append([
            str(i),
            rtl_render(f"القسط رقم {i} / Instalment {i}"),
            f"2026-{(i % 12) + 1:02d}-15",
            f"{35_000 + i * 1_250:,}",
        ])
    rows.append(["", rtl_render("الإجمالي / Total"), "", "1,487,500"])

    doc = SimpleDocTemplate(str(dest / "stress_table_pagebreak.pdf"), pagesize=A4,
                            topMargin=48, bottomMargin=48)
    table = Table(rows, colWidths=[24, 230, 90, 100], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "ArabicBody"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
    ]))
    doc.build([
        Paragraph(rtl_render("جدول الأقساط - Instalment Schedule"), style),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph(rtl_render(
            "تُسدد الأقساط في تواريخ استحقاقها دون حاجة إلى إخطار. "
            "Instalments fall due on the dates shown without further notice."
        ), style),
    ])
    record(
        "stress_table_pagebreak.pdf", kind="synthetic", format="pdf",
        pdf_type="text-based",
        language_mix="bilingual table cells",
        structure="a single 30-row table that spans a page boundary, with a "
                  "repeated header row on the continuation page",
        tables_expected=1,
        quirks=[
            "the table is ONE logical table but TWO page objects. Extractors "
            "that work per page report two tables; the header row appears twice; "
            "a chunker with keep_tables_whole must decide which of those is true",
            "the continuation page's first row is a repeat of the header, not data",
            "counted as 1 expected table on purpose -- reporting 2 is the "
            "failure mode this fixture exists to surface",
        ],
        exercises=["table extraction across pages", "chunking keep_tables_whole"],
    )
    print("  stress_table_pagebreak.pdf")


# ---------------------------------------------------------------------------
# 3. Scanned pages whose ground truth is authored, not extracted
# ---------------------------------------------------------------------------

AUTHORED_AR_PAGES = [
    """قانون رقم 44 لسنة 2026
بإصدار قانون تنظيم عقود الاستشارات الهندسية

باسم الشعب
رئيس الجمهورية
قرر مجلس النواب القانون الآتي نصه، وقد أصدرناه:

المادة الأولى
يعمل بأحكام القانون المرافق في شأن تنظيم عقود الاستشارات الهندسية.

المادة الثانية
يصدر رئيس مجلس الوزراء اللائحة التنفيذية لهذا القانون خلال ستة أشهر من
تاريخ العمل به، وإلى أن تصدر يستمر العمل باللوائح القائمة فيما لا يتعارض
مع أحكامه.

المادة الثالثة
يلغى كل حكم يخالف أحكام القانون المرافق.

المادة الرابعة
ينشر هذا القانون في الجريدة الرسمية، ويعمل به من اليوم التالي لتاريخ نشره.""",
    """الفصل الأول
تعريفات وأحكام عامة

المادة 1
في تطبيق أحكام هذا القانون يقصد بالألفاظ والعبارات التالية المعنى المبين
قرين كل منها:

الجهة الإدارية: الوزارة أو المصلحة أو الهيئة العامة التي تبرم العقد.
المستشار: الشخص الطبيعي أو الاعتباري المرخص له بمزاولة أعمال الاستشارات.
العقد: الاتفاق المكتوب المبرم بين الجهة الإدارية والمستشار.

المادة 2
تسري أحكام هذا القانون على كل عقد استشارات هندسية تبرمه جهة إدارية،
أياً كانت قيمته، ما لم ينص قانون خاص على خلاف ذلك.

المادة 3
يجب أن يكون العقد مكتوباً، وأن يتضمن على الأخص نطاق الخدمات ومدة التنفيذ
وقيمة الأتعاب وطريقة سدادها وأحكام إنهاء العقد.""",
    """الفصل الثاني
التزامات المستشار

المادة 4
يلتزم المستشار بأداء الخدمات المتفق عليها بالدقة المهنية المعتادة، وأن
يخطر الجهة الإدارية كتابة بأي ظرف من شأنه التأثير على مواعيد التنفيذ.

المادة 5
لا يجوز للمستشار أن يتنازل عن العقد أو أن يعهد بتنفيذه كله أو بعضه إلى
الغير إلا بموافقة كتابية مسبقة من الجهة الإدارية.

المادة 6
يظل المستشار مسؤولاً عن أعمال من يستعين بهم في تنفيذ العقد كما لو كانت
صادرة عنه.

المادة 7
تسقط دعوى المسؤولية بمضي ثلاث سنوات من تاريخ اكتشاف الخطأ.""",
]

AUTHORED_EN_PAGES = [
    """ARBITRAL AWARD
Cairo Regional Centre for International Commercial Arbitration
Case No. 1402 of 2026

Between:
Nile Blue Engineering Supplies S.A.E. (Claimant)
and
Karnak Holdings for Investment S.A.E. (Respondent)

I. PROCEDURAL HISTORY

1. The Claimant filed its Request for Arbitration on 14 January 2026.
2. The Respondent filed its Answer on 27 February 2026, raising an objection
to jurisdiction on the ground that the arbitration agreement had expired.
3. The Tribunal was constituted on 11 March 2026 and held a case management
conference on 2 April 2026.

II. THE PARTIES' POSITIONS

4. The Claimant seeks payment of EGP 2,450,000 said to be outstanding under
the Supply Agreement dated 15 January 2025, together with interest.
5. The Respondent denies liability and counterclaims for EGP 610,000 in
respect of defective goods delivered in November 2025.""",
    """III. JURISDICTION

6. The Tribunal has considered the Respondent's objection and finds that the
arbitration clause at Article 19 of the Supply Agreement survives termination
of the substantive obligations, applying the principle of separability.

7. The objection is accordingly dismissed.

IV. THE MERITS

8. On the evidence, the Tribunal finds that four instalments fell due and that
three were paid. The fourth, in the sum of EGP 612,500, was not paid.

9. As to the counterclaim, the Respondent has not established that the goods
delivered on 18 November 2025 departed from the contractual specification.
The expert report relied upon was prepared without inspection of the goods.

V. COSTS

10. Costs follow the event. The Respondent shall bear the costs of the
arbitration, assessed at EGP 185,000, and shall contribute EGP 120,000
towards the Claimant's legal costs.""",
]


def _render_text_page(lines: list[str], width: int, height: int, rtl: bool,
                      font_size: int) -> "object":
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (253, 252, 248))
    dr = ImageDraw.Draw(img)
    font = _pil_font(font_size)
    y = 110
    for line in lines:
        shaped = rtl_render(line)
        if not line.strip():
            y += font_size
            continue
        if rtl:
            w = dr.textlength(shaped, font=font)
            dr.text((width - 120 - w, y), shaped, font=font, fill=(18, 18, 18))
        else:
            dr.text((120, y), shaped, font=font, fill=(18, 18, 18))
        y += int(font_size * 1.55)
    return img


def make_authored_scans(dest: Path) -> None:
    """Scanned PDFs whose ground truth was written before the pixels existed.

    This is the only ground truth in the corpus with no provenance problem. Every
    other reference is a PDF's text layer, and the audit shows those can be in
    visual word order, fragmented, or emitted out of flow.
    """
    import io

    import fitz
    from PIL import Image

    specs = [
        # (name, pages, lang, dpi-equivalent size, degradation, font size)
        ("scan_authored_statute_ar_300dpi.pdf", AUTHORED_AR_PAGES, "ar",
         (2480, 3508), (0.3, 3, 0.3, 88), 46,
         "clean 300 dpi equivalent, minimal degradation"),
        ("scan_authored_statute_ar_150dpi.pdf", AUTHORED_AR_PAGES, "ar",
         (1240, 1754), (-1.3, 12, 0.9, 55), 23,
         "150 dpi equivalent, heavy noise and JPEG artifacts"),
        ("scan_authored_award_en_300dpi.pdf", AUTHORED_EN_PAGES, "en",
         (2480, 3508), (0.4, 4, 0.3, 86), 44,
         "clean 300 dpi equivalent"),
        ("scan_authored_award_en_150dpi.pdf", AUTHORED_EN_PAGES, "en",
         (1240, 1754), (-1.1, 11, 0.8, 58), 22,
         "150 dpi equivalent, heavy noise and JPEG artifacts"),
    ]

    for name, pages, lang, (w, h), (skew, noise, blur, q), fsize, quality_note in specs:
        outdoc = fitz.open()
        gt_parts = []
        for page_text in pages:
            lines = page_text.splitlines()
            img = _render_text_page(lines, w, h, rtl=(lang == "ar"), font_size=fsize)
            img = _degrade(img, skew, noise, blur, q)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q)
            newpage = outdoc.new_page(width=595, height=842)
            newpage.insert_image(newpage.rect, stream=buf.getvalue())
            gt_parts.append(page_text)
        outdoc.save(str(dest / name))
        outdoc.close()
        gt_name = name.replace(".pdf", ".groundtruth.txt")
        (dest / gt_name).write_text("\f".join(gt_parts), encoding="utf-8")

        record(
            name, kind="synthetic", format="pdf",
            pdf_type="scanned (image-only, no text layer)",
            ground_truth=f"test_corpus/synthetic/{gt_name}",
            ground_truth_provenance="AUTHORED -- the text was written first and "
                                    "then painted onto the page, so the reference "
                                    "is correct by construction",
            language_mix={"ar": "pure Arabic", "en": "pure English"}[lang],
            structure="statute articles (المادة)" if lang == "ar"
                      else "arbitral award with roman-numeral sections",
            quirks=[
                quality_note,
                "NO text layer -- must be classified scanned and routed to OCR",
                "the reference has no visual-order, fragmentation or out-of-flow "
                "defect, unlike every reference derived from a source text layer. "
                "**These are the fixtures whose absolute OCR accuracy is quotable.**",
                "still optimistic against real scans: rendered glyphs, no scanner "
                "optics, no photocopy generations, no bleed-through",
            ],
            exercises=["type_detection: scanned", "OCR accuracy on a clean reference"],
        )
        print(f"  {name} ({len(pages)} pages, authored ground truth)")


# ---------------------------------------------------------------------------
# 4. More derived scans, to widen the sample
# ---------------------------------------------------------------------------


def make_extra_derived_scans(dest: Path) -> None:
    """Rasterize public sources not yet represented in the scanned corpus.

    Deliberately excludes ``wipo_eg087ar_1.pdf``: it is handwritten, its text
    layer contains no Arabic at all, and it is not reliably scoreable. See the
    manifest's exclusions section.
    """
    import io

    import fitz
    from PIL import Image

    from src.type_detection import text_layer_quality

    sources = [
        ("wipo_eg081ar_1.pdf", "ar", 300, 0.4, 4, 0.3, 85),
        ("constitute_egypt_2019_ar.pdf", "ar", 150, -1.2, 11, 0.8, 60),
        ("eg_official_gazette_excerpt.pdf", "en", 300, 0.3, 4, 0.3, 85),
        ("eg_constitution_2014_en.pdf", "en", 150, -0.9, 9, 0.7, 64),
    ]

    for fname, lang, dpi, skew, noise, blur, q in sources:
        src = PUBLIC_CORPUS_DIR / fname
        if not src.exists():
            print(f"  ! {fname} not present, skipped")
            continue

        with fitz.open(src) as probe:
            sample = "".join(probe[i].get_text() for i in range(min(4, probe.page_count)))
        quality, note = text_layer_quality(sample)
        if quality < 0.5:
            print(f"  ! {fname} REJECTED as ground-truth source: {note}")
            continue

        out_name = f"scan_{src.stem}_{dpi}dpi.pdf"
        gt_name = f"scan_{src.stem}_{dpi}dpi.groundtruth.txt"
        srcdoc = fitz.open(src)
        outdoc = fitz.open()
        gt_parts = []
        n = min(6, srcdoc.page_count)
        for i in range(n):
            page = srcdoc[i]
            gt_parts.append(page.get_text("text"))
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = _degrade(img, skew, noise, blur, q)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q)
            newpage = outdoc.new_page(width=page.rect.width, height=page.rect.height)
            newpage.insert_image(newpage.rect, stream=buf.getvalue())
        srcdoc.close()
        outdoc.save(str(dest / out_name))
        outdoc.close()
        # Form feed between pages, so a consumer scoring a subset of the pages
        # can slice the reference to match. The first-wave scan_* fixtures lack
        # these and must be scored whole.
        (dest / gt_name).write_text("\f".join(gt_parts), encoding="utf-8")

        record(
            out_name, kind="synthetic (derived from public)", format="pdf",
            pdf_type="scanned (image-only, no text layer)",
            derived_from=f"test_corpus/public/{fname}, first {n} pages",
            ground_truth=f"test_corpus/synthetic/{gt_name}",
            ground_truth_provenance="source PDF text layer -- see "
                                    "test_corpus/synthetic/reference_audit.json "
                                    "for whether it is trustworthy",
            language_mix={"ar": "pure Arabic", "en": "pure English"}[lang],
            source_text_layer_quality=round(quality, 3),
            quirks=[
                f"rasterized at {dpi} dpi, skew {skew} deg, noise {noise}, JPEG q{q}",
                "page-separated ground truth (form feed), unlike the first-wave "
                "scan_* fixtures",
            ],
            exercises=["type_detection: scanned", "OCR accuracy measurement"],
        )
        print(f"  {out_name} ({n} pages)")


def main() -> int:
    dest = SYNTHETIC_CORPUS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    if not ARABIC_FONT.exists():
        print(f"ERROR: Arabic-capable font not found at {ARABIC_FONT}")
        return 1

    print("Image tables:")
    make_table_images(dest)
    print("\nLayout edge cases:")
    make_edge_case_pdfs(dest)
    make_pagebreak_table_pdf(dest)
    print("\nAuthored scans (ground truth written, not extracted):")
    make_authored_scans(dest)
    print("\nAdditional derived scans:")
    make_extra_derived_scans(dest)

    (dest / "stress_manifest.json").write_text(
        json.dumps(
            {
                "note": "Second-wave stress fixtures. Fabricated content plus "
                        "renderings of PUBLIC legal PDFs. No firm data.",
                "files": MANIFEST,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {len(MANIFEST)} fixtures -> {dest / 'stress_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
