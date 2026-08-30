"""Generate the synthetic half of the interim test corpus.

ALL DATA HERE IS FABRICATED. Party names, national ID numbers, addresses,
amounts, case numbers and dates are invented for testing. Nothing is drawn from
a real client, matter, or firm document -- the firm's anonymized sample batch
has not been received. The legal phrasing imitates the *shape* of standard-form
Egyptian instruments so the structure detector has something realistic to chew
on; it is not legal drafting and must not be used as such.

What gets generated, and which pipeline path each file exercises:

  synthetic_contract_bilingual.pdf   text PDF, ar+en, tables, 2-column clause
                                     layout, stamp box  -> PyMuPDF/Docling path
  synthetic_contract_ar.docx         DOCX, Arabic, styled headings + table
                                     -> Docling/python-docx path
  synthetic_lease_bilingual.docx     DOCX, mixed ar/en, nested clause numbering
  synthetic_statute_ar.txt           TXT, Arabic, المادة numbering -> plaintext
  synthetic_memo_mixed.txt           TXT, mixed script, Arabic-Indic digits
  synthetic_visual_order_ar.txt      TXT deliberately stored in VISUAL order
                                     -> exercises rtl_fix repair + flagging
  synthetic_stamped_page.png         image -> straight to OCR
  synthetic_table_page.png           image, borderless table -> OCR + tables
  scan_<name>.pdf                    rasterized derivations of the public text
                                     PDFs, with skew/noise/JPEG artifacts
                                     -> OCR path, WITH ground truth

The ``scan_*`` files are the important ones for OCR evaluation: because they are
derived from a text PDF whose true text we can read directly, they give real
character-level ground truth for Arabic and English OCR accuracy. Genuine
scanned Arabic legal PDFs are not reliably obtainable from public sources, and
one without ground truth could only be eyeballed, not measured.

They are a *stand-in for*, not equivalent to, real firm scans: a rasterized
digital PDF has clean glyph shapes and no camera/scanner optics, so OCR numbers
measured here should be read as an optimistic bound.

Run::

    python scripts/make_synthetic_corpus.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PUBLIC_CORPUS_DIR, SYNTHETIC_CORPUS_DIR  # noqa: E402

random.seed(20260811)  # reproducible corpus

FONT_DIR = Path(r"C:\Windows\Fonts")
ARABIC_FONT = FONT_DIR / "arial.ttf"
ARABIC_FONT_BOLD = FONT_DIR / "arialbd.ttf"

MANIFEST: list[dict] = []


def record(name: str, **kw) -> None:
    MANIFEST.append({"file": name, **kw})


# ---------------------------------------------------------------------------
# Fabricated content
# ---------------------------------------------------------------------------

FAKE_PARTY_A_AR = "شركة النيل الأزرق للتوريدات الهندسية ش.م.م"
FAKE_PARTY_A_EN = "Blue Nile Engineering Supplies S.A.E."
FAKE_PARTY_B_AR = "شركة دلتا طنطا للمقاولات العامة"
FAKE_PARTY_B_EN = "Delta Tanta General Contracting Co."

CONTRACT_CLAUSES_AR = [
    ("تمهيد",
     "حيث أن الطرف الأول شركة مساهمة مصرية مقيدة بالسجل التجاري بالقاهرة تحت رقم "
     "٤٤١٢٩ ويرغب في التعاقد مع الطرف الثاني على النحو المبين بهذا العقد، وحيث أن "
     "الطرف الثاني يقر بأن لديه الخبرة الفنية والملاءة المالية اللازمة لتنفيذ الأعمال "
     "محل التعاقد، فقد اتفق الطرفان على ما يلي."),
    ("المادة (1) : التعريفات",
     "يقصد بالكلمات والعبارات الآتية المعاني الموضحة قرين كل منها ما لم يقتض سياق "
     "النص خلاف ذلك: العقد: يقصد به هذا المحرر وملاحقه وجميع مستنداته. الأعمال: "
     "يقصد بها كافة الأعمال والتوريدات المبينة بالملحق رقم (1) المرفق. "
     "مدة التنفيذ: يقصد بها المدة المحددة بالمادة (4) من هذا العقد."),
    ("المادة (2) : محل العقد",
     "يلتزم الطرف الثاني بأن يورد للطرف الأول كامل المهمات والمواد الموضحة بالملحق "
     "رقم (1)، وذلك طبقاً للمواصفات الفنية المعتمدة، وعلى مسئوليته الكاملة، وبما لا "
     "يخل بأحكام القانون المدني المصري وتعديلاته."),
    ("المادة (3) : قيمة العقد وطريقة السداد",
     "حدد الطرفان قيمة هذا العقد بمبلغ إجمالي وقدره ٢٬٤٥٠٬٠٠٠ جنيه مصري (فقط مليونان "
     "وأربعمائة وخمسون ألف جنيه مصري لا غير) شاملة ضريبة القيمة المضافة. ويتم السداد "
     "على الدفعات المبينة بالجدول المرفق بالمادة (3) مكرر."),
    ("المادة (4) : مدة التنفيذ",
     "مدة تنفيذ هذا العقد ثمانية عشر شهراً تبدأ من تاريخ استلام الطرف الثاني لأمر بدء "
     "الأعمال كتابةً. ولا يجوز مد هذه المدة إلا باتفاق مكتوب بين الطرفين."),
    ("المادة (5) : غرامة التأخير",
     "في حالة تأخر الطرف الثاني عن التنفيذ في المواعيد المتفق عليها، يستحق الطرف الأول "
     "غرامة تأخير مقدارها ٠٫٥٪ من قيمة الأعمال المتأخرة عن كل أسبوع تأخير، بحد أقصى "
     "١٠٪ من إجمالي قيمة العقد، وذلك دون حاجة إلى تنبيه أو إنذار."),
    ("المادة (6) : إنهاء العقد",
     "يحق للطرف الأول إنهاء هذا العقد من طرف واحد ودون اللجوء إلى القضاء في أي من "
     "الحالات الآتية: (أ) إذا أخل الطرف الثاني بأي التزام جوهري من التزاماته ولم يتدارك "
     "الإخلال خلال خمسة عشر يوماً من تاريخ إخطاره. (ب) إذا شهر إفلاس الطرف الثاني أو "
     "دخل في تصفية. (ج) إذا تنازل الطرف الثاني عن العقد للغير دون موافقة كتابية مسبقة."),
    ("المادة (7) : السرية",
     "يلتزم كل طرف بالمحافظة على سرية كافة المعلومات والبيانات التي يطلع عليها بمناسبة "
     "تنفيذ هذا العقد، وعدم إفشائها للغير، ويظل هذا الالتزام قائماً لمدة خمس سنوات من "
     "تاريخ انتهاء العقد لأي سبب."),
    ("المادة (8) : القانون الواجب التطبيق وتسوية المنازعات",
     "يخضع هذا العقد وتفسيره لأحكام القانون المصري. وفي حالة نشوء أي نزاع بشأن تفسير "
     "أو تنفيذ هذا العقد يسعى الطرفان لتسويته ودياً خلال ثلاثين يوماً، فإذا تعذر ذلك "
     "يكون الاختصاص لمحكمة شمال القاهرة الابتدائية."),
    ("المادة (9) : الإخطارات",
     "تكون جميع الإخطارات المتبادلة بين الطرفين كتابةً على العناوين المبينة بصدر هذا "
     "العقد بموجب خطاب موصى عليه بعلم الوصول أو على يد محضر."),
]

CONTRACT_CLAUSES_EN = [
    ("Article 1. Definitions",
     "In this Agreement, unless the context otherwise requires: \"Agreement\" means this "
     "instrument together with its annexes; \"Works\" means the supplies and works "
     "described in Annex 1; \"Execution Period\" means the period specified in Article 4."),
    ("Article 2. Scope",
     "The Second Party shall supply to the First Party all equipment and materials set "
     "out in Annex 1 in accordance with the approved technical specifications and at its "
     "sole responsibility, without prejudice to the Egyptian Civil Code."),
    ("Article 5. Delay Penalty",
     "Should the Second Party fail to perform within the agreed dates, the First Party "
     "shall be entitled to a delay penalty of 0.5% of the value of the delayed works for "
     "each week of delay, capped at 10% of the total Agreement value, without need of "
     "notice or warning."),
    ("Article 6. Termination",
     "Termination may occur at the option of the First Party without recourse to the "
     "courts in any of the following cases: (a) material breach by the Second Party not "
     "remedied within fifteen (15) days of notice; (b) bankruptcy or liquidation of the "
     "Second Party; (c) assignment of this Agreement without prior written consent."),
    ("Article 8. Governing Law and Dispute Resolution",
     "This Agreement shall be governed by and construed in accordance with the laws of "
     "the Arab Republic of Egypt. Any dispute shall first be settled amicably within "
     "thirty (30) days, failing which the North Cairo Court of First Instance shall have "
     "exclusive jurisdiction."),
]

PAYMENT_TABLE = [
    ["الدفعة", "Milestone", "النسبة %", "القيمة (جنيه)", "تاريخ الاستحقاق"],
    ["الأولى", "Advance on signature", "25", "612,500", "2026-01-15"],
    ["الثانية", "Delivery of phase 1", "30", "735,000", "2026-05-30"],
    ["الثالثة", "Delivery of phase 2", "30", "735,000", "2026-11-30"],
    ["الرابعة", "Final acceptance", "15", "367,500", "2027-06-30"],
]

STATUTE_AR = """قانون رقم 17 لسنة 2026
بإصدار قانون تنظيم التوريدات الحكومية

باسم الشعب
رئيس الجمهورية
بعد الاطلاع على الدستور؛
وعلى القانون المدني الصادر بالقانون رقم 131 لسنة 1948؛
قرر مجلس النواب القانون الآتي نصه، وقد أصدرناه:

الباب الأول
أحكام عامة

الفصل الأول
في التعريفات والنطاق

المادة (1)
يعمل بأحكام القانون المرفق في شأن تنظيم التوريدات الحكومية، ويلغى كل حكم يخالف أحكامه.

المادة (2)
يقصد في تطبيق أحكام هذا القانون بالكلمات والعبارات الآتية المعنى المبين قرين كل منها:
أولاً: الجهة الإدارية: كل وحدة من وحدات الجهاز الإداري للدولة.
ثانياً: المورد: كل شخص طبيعي أو اعتباري يتعاقد مع الجهة الإدارية.
ثالثاً: العقد: الاتفاق المبرم بين الجهة الإدارية والمورد.

المادة (3)
تسري أحكام هذا القانون على جميع عمليات التوريد التي تجريها الجهات الإدارية، وذلك فيما لم يرد بشأنه نص خاص.

الفصل الثاني
في إجراءات التعاقد

المادة (4)
لا يجوز التعاقد إلا بعد الإعلان عن العملية بإحدى الطرق المبينة باللائحة التنفيذية لهذا القانون، وذلك فيما عدا حالات التعاقد المباشر المنصوص عليها في المادة (7).

المادة (5)
يجب أن يتضمن الإعلان البيانات الآتية:
(أ) موضوع العملية ومواصفاتها الفنية.
(ب) قيمة التأمين الابتدائي وطريقة أدائه.
(ج) الموعد النهائي لتقديم العطاءات.

المادة (6)
تشكل لجنة البت بقرار من السلطة المختصة، وتتولى فحص العطاءات وترسية العملية على صاحب العطاء الأفضل.

المادة (7)
استثناءً من حكم المادة (4)، يجوز التعاقد المباشر في حالات الضرورة العاجلة، وبشرط صدور قرار مسبب من السلطة المختصة.

المادة (7) مكرر
يجوز للجهة الإدارية في حالات الطوارئ المعلنة أن تتجاوز الحدود المالية المقررة، على أن تعرض الأمر على مجلس الوزراء خلال ثلاثين يوماً.

الباب الثاني
في تنفيذ العقد

المادة (8)
يلتزم المورد بتنفيذ العقد طبقاً للمواصفات والمدد المتفق عليها، ويكون مسئولاً عن أي إخلال.

المادة (9)
يعاقب بغرامة لا تقل عن خمسين ألف جنيه ولا تجاوز خمسمائة ألف جنيه كل من خالف أحكام المادة (4) من هذا القانون.
"""

MEMO_MIXED = """مذكرة داخلية / Internal Memorandum
إلى: إدارة الشئون القانونية - Legal Affairs Department
من: Ahmed Farouk, Senior Associate
التاريخ: ١٥/٠٣/٢٠٢٦
الموضوع: مراجعة عقد التوريد رقم CTR-2026-0147

أولاً: الخلفية
تم استلام مسودة العقد من العميل Blue Nile Engineering Supplies بتاريخ ١٢/٠٣/٢٠٢٦.
وقد راجعنا البنود من (1) إلى (9) على ضوء أحكام Law No. 182 of 2018 والقانون المدني.

ثانياً: الملاحظات الجوهرية
1. البند (5) delay penalty cap محدد بنسبة ١٠٪ وهو أقل من السقف المعتاد في هذا النوع of contracts.
2. البند (6) termination clause لا يتضمن cure period واضحة للطرف الأول.
3. البند (8) governing law يحيل إلى محكمة شمال القاهرة، ونقترح تعديله إلى Cairo Regional
   Centre for International Commercial Arbitration (CRCICA).

ثالثاً: التوصية
نوصي بعدم التوقيع قبل تعديل البنود (5) و (6) و (8) على النحو المبين أعلاه.
We recommend escalating clause 8 to the partner in charge before the 20/03/2026 deadline.
"""


# ---------------------------------------------------------------------------
# Arabic shaping for RENDERING ONLY
# ---------------------------------------------------------------------------


def shape_for_render(text: str) -> str:
    """Reshape + bidi Arabic so a PDF/image canvas draws it correctly.

    This is the *legitimate* use of arabic-reshaper + python-bidi: painting
    glyphs onto a surface with no bidi engine. Note that a PDF produced this way
    stores presentation forms in visual order -- which is exactly the damage
    :mod:`src.rtl_fix` exists to detect and repair, so these fixtures also
    exercise that path realistically.
    """
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


def has_arabic(s: str) -> bool:
    return any("\u0600" <= c <= "\u06ff" for c in s)


def rtl_render(s: str) -> str:
    return shape_for_render(s) if has_arabic(s) else s


# ---------------------------------------------------------------------------
# 1. Bilingual contract PDF (text-based)
# ---------------------------------------------------------------------------


def make_contract_pdf(dest: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    pdfmetrics.registerFont(TTFont("Ar", str(ARABIC_FONT)))
    pdfmetrics.registerFont(TTFont("ArB", str(ARABIC_FONT_BOLD)))

    path = dest / "synthetic_contract_bilingual.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title="Synthetic Bilingual Supply Contract (TEST DATA)",
    )
    ss = getSampleStyleSheet()
    ar_head = ParagraphStyle("ArHead", parent=ss["Heading2"], fontName="ArB",
                             fontSize=13, alignment=TA_RIGHT, leading=20, spaceBefore=10)
    ar_body = ParagraphStyle("ArBody", parent=ss["BodyText"], fontName="Ar",
                             fontSize=10.5, alignment=TA_RIGHT, leading=18)
    ar_title = ParagraphStyle("ArTitle", parent=ss["Title"], fontName="ArB",
                              fontSize=17, alignment=TA_CENTER, leading=26)
    en_head = ParagraphStyle("EnHead", parent=ss["Heading2"], fontSize=12, spaceBefore=10)
    en_body = ParagraphStyle("EnBody", parent=ss["BodyText"], fontSize=10, leading=15)

    story = []
    story.append(Paragraph(rtl_render("عقد توريد وتركيب"), ar_title))
    story.append(Paragraph("SUPPLY AND INSTALLATION AGREEMENT", ss["Title"]))
    story.append(Paragraph("<i>[SYNTHETIC TEST DOCUMENT - FABRICATED DATA]</i>",
                           ParagraphStyle("note", parent=ss["Normal"], alignment=TA_CENTER,
                                          textColor=colors.grey, fontSize=8)))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(
        rtl_render(f"إنه في يوم الأحد الموافق ١٥ يناير ٢٠٢٦ تحرر هذا العقد بين كل من: "
                   f"أولاً: {FAKE_PARTY_A_AR}، ومقرها ١٢ شارع النيل، الدقي، الجيزة "
                   f"(طرف أول). ثانياً: {FAKE_PARTY_B_AR}، ومقرها ٤٤ شارع الجيش، طنطا، "
                   f"الغربية (طرف ثان)."), ar_body))
    story.append(Paragraph(
        f"Made on 15 January 2026 between {FAKE_PARTY_A_EN} (the \"First Party\") and "
        f"{FAKE_PARTY_B_EN} (the \"Second Party\").", en_body))
    story.append(Spacer(1, 0.4 * cm))

    for i, (head, body) in enumerate(CONTRACT_CLAUSES_AR):
        story.append(Paragraph(rtl_render(head), ar_head))
        story.append(Paragraph(rtl_render(body), ar_body))
        if i == 3:
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph(rtl_render("جدول الدفعات - Payment Schedule"), ar_head))
            tbl = Table(
                [[rtl_render(c) for c in row] for row in PAYMENT_TABLE],
                colWidths=[2.6 * cm, 4.6 * cm, 2.0 * cm, 3.2 * cm, 3.2 * cm],
            )
            tbl.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Ar"),
                ("FONTNAME", (0, 0), (-1, 0), "ArB"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
                ("ALIGN", (2, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.3 * cm))

    story.append(PageBreak())
    story.append(Paragraph("ENGLISH COUNTERPART", ss["Heading1"]))
    for head, body in CONTRACT_CLAUSES_EN:
        story.append(Paragraph(head, en_head))
        story.append(Paragraph(body, en_body))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(rtl_render("التوقيعات - Signatures"), ar_head))
    sig = Table(
        [[rtl_render("الطرف الأول / First Party"), rtl_render("الطرف الثاني / Second Party")],
         [rtl_render(FAKE_PARTY_A_AR), rtl_render(FAKE_PARTY_B_AR)],
         ["______________________", "______________________"],
         [rtl_render("خاتم الشركة"), rtl_render("خاتم الشركة")]],
        colWidths=[7.8 * cm, 7.8 * cm], rowHeights=[0.9 * cm, 0.9 * cm, 1.1 * cm, 1.6 * cm],
    )
    sig.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Ar"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sig)

    doc.build(story)
    record(
        "synthetic_contract_bilingual.pdf",
        kind="synthetic", format="pdf", pdf_type="text-based (digitally native)",
        language_mix="Arabic primary + English counterpart (bilingual)",
        structure="المادة (1)-(9) Arabic articles; Article 1-8 English; tables; signature/stamp box",
        quirks=[
            "Arabic drawn via arabic-reshaper + python-bidi, so the PDF stores "
            "PRESENTATION FORMS IN VISUAL ORDER -- realistic reproduction of "
            "Arabic DTP output and the main fixture for rtl_fix repair",
            "5-column bilingual payment table with mixed Arabic/Latin headers",
            "Arabic-Indic digits (٢٬٤٥٠٬٠٠٠) alongside Western digits in the table",
            "mixed-direction clause bodies (English defined terms inside Arabic)",
            "signature/stamp box as a bordered table",
        ],
        exercises=["type_detection: text", "extract_pymupdf_docling", "rtl_fix",
                   "normalize", "chunking (structural)", "tables"],
    )


# ---------------------------------------------------------------------------
# 2/3. DOCX
# ---------------------------------------------------------------------------


def make_contract_docx(dest: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    d = Document()
    style = d.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)

    t = d.add_heading("عقد توريد وتركيب - SYNTHETIC TEST DOCUMENT", level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = d.add_paragraph("[بيانات مختلقة بالكامل لأغراض الاختبار / FABRICATED TEST DATA]")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    d.add_paragraph(
        f"تحرر هذا العقد بين {FAKE_PARTY_A_AR} (طرف أول) و {FAKE_PARTY_B_AR} (طرف ثان)."
    ).alignment = WD_ALIGN_PARAGRAPH.RIGHT

    for head, body in CONTRACT_CLAUSES_AR:
        h = d.add_heading(head, level=1)
        h.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        para = d.add_paragraph(body)
        para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    d.add_heading("جدول الدفعات - Payment Schedule", level=1)
    table = d.add_table(rows=0, cols=5)
    table.style = "Table Grid"
    for row in PAYMENT_TABLE:
        cells = table.add_row().cells
        for c, val in zip(cells, row):
            c.text = val

    d.add_page_break()
    d.add_heading("ENGLISH COUNTERPART", level=1)
    for head, body in CONTRACT_CLAUSES_EN:
        d.add_heading(head, level=2)
        d.add_paragraph(body)

    d.save(str(dest / "synthetic_contract_ar.docx"))
    record(
        "synthetic_contract_ar.docx",
        kind="synthetic", format="docx",
        language_mix="Arabic primary + English counterpart",
        structure="Word Heading 1/2 styles carrying المادة (n) labels; 5-col Table Grid; explicit page break",
        quirks=[
            "DOCX has no stored pagination -- page numbers come from the single "
            "explicit page break only; pipeline warns about this",
            "logical-order Arabic (unlike the PDF fixture) -- rtl_fix should "
            "NOT repair this one, which is the negative test",
            "Arabic-Indic digits inside table cells",
        ],
        exercises=["type_detection: docx", "docling/python-docx path", "chunking (structural)", "tables"],
    )


def make_lease_docx(dest: Path) -> None:
    """Deeply nested bilingual clause numbering -- stresses granularity choice."""
    from docx import Document
    from docx.shared import Pt

    d = Document()
    d.styles["Normal"].font.size = Pt(11)
    d.add_heading("LEASE AGREEMENT / عقد إيجار - SYNTHETIC TEST DOCUMENT", level=0)
    d.add_paragraph("[FABRICATED TEST DATA - no real parties or premises]")

    blocks = [
        ("1. Definitions and Interpretation", [
            "1.1 In this Lease the following expressions have the meanings given below.",
            "1.2 \"Premises\" means the third floor of 44 El Geish Street, Tanta, Gharbia.",
            "1.3 \"Term\" means five (5) years commencing 1 February 2026.",
        ]),
        ("2. Grant and Rent / منح الإيجار والأجرة", [
            "2.1 The Landlord lets and the Tenant takes the Premises for the Term.",
            "2.2 الأجرة السنوية مبلغ ٤٨٠٬٠٠٠ جنيه مصري تدفع على أقساط ربع سنوية مقدماً.",
            "2.3 Rent shall increase by seven percent (7%) on each anniversary of the "
            "Commencement Date.",
        ]),
        ("3. Tenant Covenants / التزامات المستأجر", [
            "3.1 The Tenant shall not assign, sublet or part with possession without "
            "the Landlord's prior written consent.",
            "3.2 يلتزم المستأجر بسداد كافة فواتير المرافق في مواعيد استحقاقها.",
            "3.3 The Tenant shall keep the Premises in good and substantial repair.",
        ]),
        ("4. Termination / الإنهاء", [
            "4.1 Termination may occur on six (6) months' written notice by either party "
            "after the third anniversary.",
            "4.2 يحق للمؤجر إنهاء العقد فوراً إذا تأخر المستأجر في سداد الأجرة مدة تجاوز "
            "ستين يوماً من تاريخ الاستحقاق.",
        ]),
        ("5. Governing Law / القانون الواجب التطبيق", [
            "5.1 This Lease is governed by the laws of the Arab Republic of Egypt.",
            "5.2 تختص محاكم طنطا الابتدائية بنظر أي نزاع ينشأ عن هذا العقد.",
        ]),
    ]
    for head, items in blocks:
        d.add_heading(head, level=1)
        for item in items:
            d.add_paragraph(item)

    d.save(str(dest / "synthetic_lease_bilingual.docx"))
    record(
        "synthetic_lease_bilingual.docx",
        kind="synthetic", format="docx",
        language_mix="English primary with Arabic clauses interleaved (true bilingual mix)",
        structure="decimal outline 1.1 / 2.3 style; bilingual headings",
        quirks=[
            "clause numbering is decimal (1.1, 2.3) not المادة -- exercises the "
            "English CLAUSE marker pattern and auto-granularity at CLAUSE level",
            "Arabic and English clauses alternate inside the same section, so "
            "chunk-level language should come out 'ar-en' for several chunks",
            "bilingual headings contain both scripts on one line -- an rtl_fix "
            "mixed_direction flag is expected here",
        ],
        exercises=["docx path", "chunking granularity=CLAUSE", "rtl_fix flagging", "language detection"],
    )


# ---------------------------------------------------------------------------
# 4/5/6. TXT
# ---------------------------------------------------------------------------


def make_txt_files(dest: Path) -> None:
    (dest / "synthetic_statute_ar.txt").write_text(STATUTE_AR, encoding="utf-8")
    record(
        "synthetic_statute_ar.txt",
        kind="synthetic", format="txt", language_mix="pure Arabic",
        structure="الباب / الفصل / المادة hierarchy including 'المادة (7) مكرر'; "
                  "أولاً-ثالثاً enumerators; (أ)(ب)(ج) sub-clauses",
        quirks=[
            "full statute hierarchy: BOOK > CHAPTER > ARTICLE -- auto granularity "
            "should settle on ARTICLE, not sub-clause",
            "'مكرر' (bis) article numbering, an Egyptian legislative convention "
            "that naive numeric parsers drop",
            "no pagination at all (TXT) -- every chunk should report page=1",
            "cross-references ('المادة (4)', 'المادة (7)') inside body text that "
            "must NOT be treated as boundaries",
        ],
        exercises=["type_detection: txt", "plaintext path", "marker detection",
                   "chunking (structural, ARTICLE level)"],
    )

    (dest / "synthetic_memo_mixed.txt").write_text(MEMO_MIXED, encoding="utf-8")
    record(
        "synthetic_memo_mixed.txt",
        kind="synthetic", format="txt", language_mix="heavily mixed Arabic/English in the same sentences",
        structure="أولاً/ثانياً/ثالثاً enumerators; numbered list items",
        quirks=[
            "code-switching mid-sentence ('البند (5) delay penalty cap محدد بنسبة ١٠٪')",
            "Arabic-Indic dates ١٥/٠٣/٢٠٢٦ mixed with Western dates 20/03/2026",
            "this is the primary fixture for rtl_fix mixed_direction and "
            "numeral_direction_ambiguous flags -- flags here are EXPECTED, not a bug",
        ],
        exercises=["plaintext path", "rtl_fix flagging", "language detection: ar-en",
                   "digit normalization"],
    )

    # Deliberately damaged: stored in visual order, as broken extraction produces.
    lines = []
    for para in STATUTE_AR.strip().split("\n"):
        lines.append(shape_for_render(para) if has_arabic(para) else para)
    (dest / "synthetic_visual_order_ar.txt").write_text("\n".join(lines), encoding="utf-8")
    record(
        "synthetic_visual_order_ar.txt",
        kind="synthetic", format="txt", language_mix="pure Arabic",
        structure="same statute as synthetic_statute_ar.txt",
        quirks=[
            "DELIBERATELY DAMAGED: stored in VISUAL order with presentation forms, "
            "reproducing what broken PDF extraction and some OCR output look like",
            "ground truth for this file is synthetic_statute_ar.txt -- rtl_fix "
            "should detect presentation forms and flag/repair reading order",
            "structural markers will NOT match until presentation forms are folded, "
            "so this also tests that normalize runs before structure annotation",
        ],
        exercises=["rtl_fix repair path", "normalize (presentation forms)",
                   "ordering of pipeline stages"],
        ground_truth="synthetic_statute_ar.txt",
    )


# ---------------------------------------------------------------------------
# 7/8. Images -> OCR
# ---------------------------------------------------------------------------


def _pil_font(size: int, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(str(ARABIC_FONT_BOLD if bold else ARABIC_FONT), size)


def make_stamped_page_image(dest: Path) -> None:
    """A signed-and-stamped Arabic page as an image -- the classic scanned exhibit."""
    from PIL import Image, ImageDraw, ImageFilter

    W, H = 1654, 2339  # A4 at 200 dpi
    img = Image.new("RGB", (W, H), (252, 251, 246))
    dr = ImageDraw.Draw(img)

    f_title = _pil_font(46, bold=True)
    f_head = _pil_font(34, bold=True)
    f_body = _pil_font(28)
    f_small = _pil_font(22)

    def rt(y, text, font, margin=120, fill=(15, 15, 15)):
        s = rtl_render(text)
        w = dr.textlength(s, font=font)
        dr.text((W - margin - w, y), s, font=font, fill=fill)

    def lt(y, text, font, margin=120, fill=(15, 15, 15)):
        dr.text((margin, y), text, font=font, fill=fill)

    y = 120
    rt(y, "محضر تسليم واستلام", f_title); y += 80
    lt(y, "DELIVERY AND ACCEPTANCE MINUTES", f_head); y += 70
    dr.line((120, y, W - 120, y), fill=(90, 90, 90), width=3); y += 50

    lines = [
        "إنه في يوم الثلاثاء الموافق ١٠ فبراير ٢٠٢٦، وبمقر الشركة الكائن",
        "بـ ١٢ شارع النيل، الدقي، الجيزة، اجتمع كل من:",
        "",
        "أولاً: ممثل الطرف الأول / المهندس/ كريم عبد الرحمن سالم",
        "ثانياً: ممثل الطرف الثاني / المهندس/ هشام محمود الشناوي",
        "",
        "وذلك لإثبات تسليم واستلام الأعمال المنفذة طبقاً للعقد رقم",
        "CTR-2026-0147 المؤرخ ١٥ يناير ٢٠٢٦، وقد تم الاتفاق على الآتي:",
        "",
        "البند (1) : تم استلام كامل التوريدات المبينة بالملحق رقم (1).",
        "البند (2) : لم يبد الطرف الأول أية تحفظات فنية على الأعمال.",
        "البند (3) : تستحق الدفعة الثانية بنسبة ٣٠٪ من قيمة العقد.",
        "",
        "وقد حرر هذا المحضر من نسختين بيد كل طرف نسخة للعمل بموجبها.",
    ]
    for ln in lines:
        if ln:
            rt(y, ln, f_body)
        y += 54

    y += 60
    rt(y, "الطرف الأول", f_head, margin=250)
    lt(y, "الطرف الثاني".join([]) or "", f_head)
    dr.text((300, y), rtl_render("الطرف الثاني"), font=f_head, fill=(15, 15, 15))
    y += 90

    # signature squiggles
    for cx in (1200, 450):
        pts = [(cx + i * 9, y + 40 + int(38 * random.uniform(-1, 1))) for i in range(22)]
        dr.line(pts, fill=(20, 30, 120), width=4)
    y += 150

    # round stamp
    cx, cy, r = 1180, y + 40, 150
    dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(30, 60, 160), width=7)
    dr.ellipse((cx - r + 22, cy - r + 22, cx + r - 22, cy + r - 22), outline=(30, 60, 160), width=3)
    for i, t in enumerate(["شركة النيل الأزرق", "للتوريدات الهندسية", "ش.م.م", "القاهرة"]):
        s = rtl_render(t)
        w = dr.textlength(s, font=f_small)
        dr.text((cx - w / 2, cy - 55 + i * 32), s, font=f_small, fill=(30, 60, 160))

    # rectangular receipt stamp
    dr.rectangle((260, cy - 110, 760, cy + 110), outline=(160, 40, 40), width=6)
    for i, t in enumerate(["وارد", f"رقم: {random.randint(1000, 9999)}", "١٠ / ٢ / ٢٠٢٦"]):
        s = rtl_render(t)
        w = dr.textlength(s, font=f_head)
        dr.text((510 - w / 2, cy - 80 + i * 60), s, font=f_head, fill=(160, 40, 40))

    img = _degrade(img, skew_deg=0.7, noise=7, blur=0.6, jpeg_quality=72)
    img.save(dest / "synthetic_stamped_page.png")
    record(
        "synthetic_stamped_page.png",
        kind="synthetic", format="png (image)",
        language_mix="Arabic primary, one English heading line",
        structure="البند (1)-(3) clause markers; signature block; two stamps",
        quirks=[
            "image input -- must route straight to OCR with no text layer",
            "round company stamp and rectangular incoming-mail stamp OVERLAP the "
            "signature area; OCR is expected to emit junk boxes from the stamps",
            "handwritten-style signature squiggles (non-text ink)",
            "page degraded: 0.7 deg skew, gaussian noise, slight blur, JPEG q72",
            "Arabic-Indic digits in dates and percentages",
        ],
        exercises=["type_detection: image -> OCR", "PaddleOCR + Tesseract fallback",
                   "ocr confidence metadata", "marker detection on OCR output"],
    )


def make_table_page_image(dest: Path) -> None:
    """A borderless bilingual table -- where PyMuPDF's ruling-line heuristic fails."""
    from PIL import Image, ImageDraw

    W, H = 1654, 1200
    img = Image.new("RGB", (W, H), (255, 254, 250))
    dr = ImageDraw.Draw(img)
    f_head = _pil_font(34, bold=True)
    f_body = _pil_font(28)

    s = rtl_render("جدول الدفعات المستحقة - Outstanding Payment Schedule")
    dr.text((W / 2 - dr.textlength(s, font=f_head) / 2, 70), s, font=f_head, fill=(10, 10, 10))

    cols = [140, 460, 800, 1080, 1360]
    y = 200
    for x, head in zip(cols, PAYMENT_TABLE[0]):
        dr.text((x, y), rtl_render(head), font=f_head, fill=(10, 10, 10))
    dr.line((120, y + 55, W - 120, y + 55), fill=(60, 60, 60), width=3)

    y += 100
    for row in PAYMENT_TABLE[1:]:
        for x, cell in zip(cols, row):
            dr.text((x, y), rtl_render(cell), font=f_body, fill=(20, 20, 20))
        y += 90

    dr.line((120, y + 10, W - 120, y + 10), fill=(60, 60, 60), width=3)
    dr.text((cols[0], y + 40), rtl_render("الإجمالي / Total"), font=f_head, fill=(10, 10, 10))
    dr.text((cols[3], y + 40), "2,450,000", font=f_head, fill=(10, 10, 10))

    img = _degrade(img, skew_deg=-0.4, noise=5, blur=0.4, jpeg_quality=80)
    img.save(dest / "synthetic_table_page.png")
    record(
        "synthetic_table_page.png",
        kind="synthetic", format="png (image)",
        language_mix="bilingual Arabic/English column headers and cells",
        structure="5-column BORDERLESS table (only a header rule and a total rule)",
        quirks=[
            "borderless table -- PyMuPDF find_tables has no ruling lines to work "
            "with; this is the case Docling's TableFormer is meant to cover, and "
            "on the OCR path neither applies, so table structure is expected to "
            "degrade to reading-order text. KNOWN GAP, see evaluation report.",
            "column contents alternate direction (Arabic label, Latin milestone, "
            "Western numerals) -- worst case for line-level reading order",
            "degraded: -0.4 deg skew, noise, JPEG q80",
        ],
        exercises=["OCR path", "table extraction limits", "rtl_fix reading order on table rows"],
    )


def _degrade(img, skew_deg: float, noise: int, blur: float, jpeg_quality: int):
    """Apply scan-like degradation: skew, noise, blur, JPEG artifacts."""
    import io

    import numpy as np
    from PIL import Image, ImageFilter

    if skew_deg:
        img = img.rotate(skew_deg, resample=Image.BICUBIC, expand=False, fillcolor=(252, 251, 246))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        arr = np.asarray(img).astype(np.int16)
        arr += np.random.normal(0, noise, arr.shape).astype(np.int16)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if jpeg_quality:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality)
        buf.seek(0)
        img = Image.open(buf).convert("RGB")
    return img


# ---------------------------------------------------------------------------
# 9. Rasterized "scans" of the public text PDFs -- OCR with ground truth
# ---------------------------------------------------------------------------


def _has_broken_word_spacing(text: str, threshold: float = 0.25) -> bool:
    """Detect spurious intra-word spacing in extracted Arabic.

    Some Arabic PDFs place every glyph individually, so extraction yields
    "دس تور" for "دستور" and "إ ن ش اء" for "إنشاء". The text is *correct*
    character-for-character but shredded into fragments.

    This matters for a ground-truth file: the reference then disagrees with
    correctly-spaced OCR output on almost every word boundary, and the reported
    error rate measures the reference's defect rather than the OCR's.

    Heuristic: a high proportion of one- and two-character Arabic tokens.
    Genuine Arabic prose has few, since most particles are 2+ letters and
    content words are longer.
    """
    tokens = [t for t in text.split() if any("؀" <= c <= "ۿ" for c in t)]
    if len(tokens) < 50:
        return False
    fragments = sum(1 for t in tokens if len(t) <= 2)
    return fragments / len(tokens) > threshold


def make_scanned_derivations(dest: Path, max_pages: int = 6) -> None:
    """Rasterize the first pages of public text PDFs into image-only PDFs.

    Because the source has a real text layer, the extracted text is exact
    ground truth for the OCR output -- which is what makes Arabic-vs-English
    OCR accuracy measurable at all on interim data.
    """
    import io

    import fitz
    from PIL import Image

    from src.type_detection import text_layer_quality

    sources = [
        ("constitute_egypt_2014_ar.pdf", "ar", 200, 0.6, 6, 0.4, 78),
        ("wipo_eg088ar_1.pdf", "ar", 150, -1.1, 10, 0.9, 62),
        ("constitute_egypt_2014_en.pdf", "en", 200, 0.5, 6, 0.4, 78),
    ]

    for fname, lang, dpi, skew, noise, blur, quality in sources:
        src = PUBLIC_CORPUS_DIR / fname
        if not src.exists():
            print(f"  ! {fname} not present, skipping scan derivation")
            continue

        # A derived scan is only useful as an OCR benchmark if its source text
        # layer is trustworthy -- that text IS the ground truth. Deriving from a
        # PDF with a broken font encoding produces a "ground truth" file of pure
        # mojibake, and scoring against it yields numbers that describe the
        # reference's defects rather than OCR quality.
        #
        # This caught wipo_eg087ar_1.pdf, whose text layer scores 0.33 and
        # contains zero Arabic characters despite being an Arabic statute.
        with fitz.open(src) as probe:
            sample = "".join(probe[i].get_text() for i in range(min(4, probe.page_count)))
        source_quality, note = text_layer_quality(sample)
        if source_quality < 0.5:
            print(f"  ! {fname} SKIPPED as a ground-truth source: {note}")
            continue

        out_name = f"scan_{src.stem}_{dpi}dpi.pdf"
        gt_name = f"scan_{src.stem}_{dpi}dpi.groundtruth.txt"

        srcdoc = fitz.open(src)
        outdoc = fitz.open()
        spacing_warning = _has_broken_word_spacing(sample)
        gt_parts = []
        n = min(max_pages, srcdoc.page_count)
        for i in range(n):
            page = srcdoc[i]
            gt_parts.append(page.get_text("text"))
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = _degrade(img, skew, noise, blur, quality)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            newpage = outdoc.new_page(width=page.rect.width, height=page.rect.height)
            newpage.insert_image(newpage.rect, stream=buf.getvalue())
        srcdoc.close()
        outdoc.save(str(dest / out_name))
        outdoc.close()

        (dest / gt_name).write_text("\n".join(gt_parts), encoding="utf-8")

        record(
            out_name,
            kind="synthetic (derived from public)", format="pdf",
            pdf_type="scanned (image-only, no text layer)",
            derived_from=f"test_corpus/public/{fname}, first {n} pages",
            ground_truth=f"test_corpus/synthetic/{gt_name}",
            language_mix={"ar": "pure Arabic", "en": "pure English"}[lang],
            structure="as in the source statute/constitution (المادة / Article numbering)",
            quirks=[
                f"rasterized at {dpi} dpi, skew {skew} deg, gaussian noise sigma "
                f"{noise}, blur {blur}, JPEG quality {quality}",
                "NO text layer -- type_detection must classify this as 'scanned' "
                "and route every page to OCR",
                "character-level ground truth available, so OCR accuracy is "
                "measurable per language",
                "OPTIMISTIC vs real firm scans: clean glyph rendering, no scanner "
                "optics, no photocopy generations, no staple shadows or bleed-through",
            ] + ([
                "GROUND TRUTH CAVEAT: the source PDF extracts with spurious "
                "intra-word spacing ('دس تور' for 'دستور'), so the reference "
                "disagrees with correctly-spaced OCR output on most word "
                "boundaries. Space-sensitive CER/WER against this file overstate "
                "the error; the space-insensitive CER is the meaningful figure.",
            ] if spacing_warning else []),
            ground_truth_spacing_defect=spacing_warning,
            source_text_layer_quality=round(source_quality, 3),
            exercises=["type_detection: scanned", "PaddleOCR primary",
                       "Tesseract fallback", "OCR accuracy measurement"],
        )
        print(f"  {out_name} ({n} pages) + ground truth")


# ---------------------------------------------------------------------------


def main() -> int:
    dest = SYNTHETIC_CORPUS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    if not ARABIC_FONT.exists():
        print(f"ERROR: Arabic-capable font not found at {ARABIC_FONT}")
        return 1

    print("Generating synthetic corpus (ALL DATA FABRICATED)...")
    print("  contract PDF ...");      make_contract_pdf(dest)
    print("  contract DOCX ...");     make_contract_docx(dest)
    print("  lease DOCX ...");        make_lease_docx(dest)
    print("  TXT files ...");         make_txt_files(dest)
    print("  stamped page PNG ...");  make_stamped_page_image(dest)
    print("  table page PNG ...");    make_table_page_image(dest)
    print("  scanned derivations ..."); make_scanned_derivations(dest)

    (dest / "synthetic_manifest.json").write_text(
        json.dumps(
            {
                "note": "ALL DATA FABRICATED. No firm documents were used. "
                        "Interim stand-in corpus only.",
                "seed": 20260811,
                "files": MANIFEST,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {len(MANIFEST)} entries to {dest / 'synthetic_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
