# Extraction spot-check

> Manual verification aid. Open each source document alongside this table and confirm the pipeline neither lost nor reordered text.

Corpus: interim corpus (public + synthetic, text-layer documents only)  
Excerpt length: 400 characters  
Config: OCR off, Docling off (text-layer path only)

**What to look for.** `SOURCE` is raw extractor output with no processing. `PIPELINE` is the finished chunk text after RTL repair and normalization. Differences between them should be *only*: folded Arabic orthography (أ→ا), folded digits (١٢→12), stripped tatweel and diacritics, collapsed whitespace, and an attached heading. Anything else -- missing sentences, reordered words, mangled numbers -- is a defect worth reporting.

## `constitute_egypt_2014_ar.pdf`

- type: `pdf` / `text`
- detected: law, ar, 44 pages, 273 chunks
- warnings: 2 (first: document appears to have been laid out VISUALLY (Arabic words correct, neutral characters mirrored). Evidence: 1 mirrore)

**SOURCE** (raw extractor output)

```
15:09 ,2026 ما يو PDF: 27 فمل إ ن ش اء تم constituteproject.org 2014 عام الصادر مصر دس تور constituteproject.org مو قع على تو ز يعه و تم ،ةالم قار ن الدسا ت ير م ش روع مس تودع نم ال نصوص نم م قاطع نم الكام الدس تور ه ذا إ ن ش اء تم constituteproject.org 15:09 ,2026 ما يو PDF: 27 فمل إ ن ش اء تم 2 ةالص ف ح2014 مصر تالمح تو يا 4 5 5 5 5 5 6 6 6 6 9 11 12 12 12 12 12 12 13 13 13 13 13 13 13 13 14 14 ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
15:09 ،2026 ما يو PDF: 27 فمل ا ن ش اء تم constituteproject.org
```

- `section`: 'constituteproject.org' | `clause_id`: 'sec_constituteproject.org' | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef', 'normalize_punctuation']

## `constitute_egypt_2014_en.pdf`

- type: `pdf` / `text`
- detected: law, en, 53 pages, 343 chunks

**SOURCE** (raw extractor output)

```
PDF generated: 11 Nov 2023, 09:45 constituteproject.org Egypt's Constitution of 2014 This complete constitution has been generated from excerpts of texts from the repository of the Comparative Constitutions Project, and distributed on constituteproject.org. constituteproject.org PDF generated: 11 Nov 2023, 09:45 Egypt 2014 Page 2 Table of contents 4 6 6 6 6 6 6 6 7 7 10 13 14 14 14 14 14 15 15 15 ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
PDF generated: 11 Nov 2023, 09:45 constituteproject.org
```

- `section`: 'constituteproject.org' | `clause_id`: 'sec_constituteproject.org' | `chunk_strategy`: 'structural'
- normalization applied: []

## `constitute_egypt_2019_ar.pdf`

- type: `pdf` / `text`
- detected: law, ar, 50 pages, 100 chunks
- warnings: 1 (first: 55 RTL/reading-order flags raised across 50 pages; see chunk metadata.rtl_flags for detail)

**SOURCE** (raw extractor output)

```
ملف إنشاء تم PDF: 28 Apr 2022, 18:04 constituteproject.org 2014 عام الصادر مصر دستور 2019 عام لغاية تعديالته شامال وتم ،المقارنة الدساتير مشروع مستودع من النصوص من مقاطع من كامال الدستور هذا إنشاء تم موقع على توزيعه constituteproject.org constituteproject.orgملف إنشاء تم PDF: 28 Apr 2022, 18:04 2019 المعدل( 2014 مصر) 2 الصفحة المحتويات 4 5 5 6 6 6 6 6 6 6 9 12 13 13 13 13 13 14 14 14 14 14 14 14 1...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
ملف انشاء تم PDF: 28 Apr 2022، 18:04 constituteproject.org
```

- `section`: 'constituteproject.org' | `clause_id`: 'sec_constituteproject.org' | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef', 'normalize_punctuation']

## `eg_constitution_2014_en.pdf`

- type: `pdf` / `text`
- detected: law, en, 47 pages, 228 chunks

**SOURCE** (raw extractor output)

```
THE CONSTITUTION OF THE ARAB REPUBLIC OF EGYPT, 1971 (as Amended to 2007) Table of Contents PART I THE STATE PART II BASIC FOUNDATIONS OF SOCIETY CHAPTER I Social and Moral Foundations CHAPTER II Economic Foundations PART III PUBLIC FREEDOMS, RIGHTS AND DUTIES PART IV RULE OF LAW PART V SYSTEM OF GOVERNMENT CHAPTER I The Head of State CHAPTER II The Legislature CHAPTER III The Executive Section I ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
THE CONSTITUTION OF THE ARAB REPUBLIC OF EGYPT, 1971 (as Amended to 2007) Table of Contents
```

- `section`: 'THE CONSTITUTION OF THE ARAB REPUBLIC OF EGYPT, 1971' | `clause_id`: 'sec_THE_CONSTITUTION_OF_THE_ARAB_REPUBLIC_OF' | `chunk_strategy`: 'structural'
- normalization applied: ['collapse_whitespace']

## `eg_official_gazette_excerpt.pdf`

- type: `pdf` / `text`
- detected: law, en, 29 pages, 134 chunks

**SOURCE** (raw extractor output)

```
UNOFFICIAL TRANSLATION 1 Arab Republic of Egypt Presidency of the Republic Official Gazette Volume No. 20 Issued on 27 Shaban 1438 Hijria Corresponding to 24 May 2017 UNOFFICIAL TRANSLATION 2 Law No (70) of 2017 The Law of Associations And Other Foundations Working in the Field of Civil Work In the name of the People President of the Republic The Parliament has issued the following law and we prom...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
Arab Republic of Egypt
```

- `section`: 'Arab Republic of Egypt' | `clause_id`: 'sec_Arab_Republic_of_Egypt' | `chunk_strategy`: 'structural'
- normalization applied: []

## `wipo_eg081ar_1.pdf`

- type: `pdf` / `text`
- detected: law, ar, 94 pages, 145 chunks
- warnings: 1 (first: 2 RTL/reading-order flags raised across 94 pages; see chunk metadata.rtl_flags for detail)

**SOURCE** (raw extractor output)

```
حمكمة النقض مركز املعلومات 1 اجلريدة الرمسية- العدد22 مكرر - يف2 يونية سنة2002 ___________________________________________ قانون رقم82 لسنة2002 بشأن إصدار قانون محاية حقوق امللكية الفكرية ( وفقاً آلخر تعديل صادر في5 سبتمبر عام2020 ) باسم الشعب رئيس اجلمهورية قرر مجلس الشعب القان:ون اآلتي نصه، وقد أصدرناه ( املادة)األوىل .يعمل بأحكام القانون المرافق في شأن حماية حقوق الملكية الفكرية ( املادة)الثاني...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
اجلريدة الرمسية- العدد22 مكرر - يف2 يونية سنة2002
```

- `section`: 'اجلريدة الرمسية-' | `clause_id`: 'sec_اجلريدة_الرمسية-' | `chunk_strategy`: 'structural'
- normalization applied: ['collapse_whitespace']

## `wipo_eg087ar_1.pdf`

- type: `pdf` / `scanned`
- detected: unknown, unknown, 0 pages, 0 chunks
- warnings: 13 (first: page 1: text layer rejected as garbled (33% letters/digits); routed to OCR)

**SOURCE** (raw extractor output)

```
----------------- •• • • • • • • \ '\'\A ;.;..J Yo (.J wj\i ~JbJl.1 -;_,;.u.1 ,1}1 j ..:..t::~I .;jli Jl.l.oi ;..~, r~ •• '!..i,;);1 crJJ : .tJ,.._l .u; , ,,.; ._j"':/1 ,:i_,;\;JI l..',I .,-1,,- _,; J,'':11 r' J' J;:11 y\:Q .,- .,..,u1 yl,11 _A - I ;;l, ,,:..\..,\}\ ,:i_,;\i .:,• J):il .,-l:>JI v' c_U yl,JI; ,J.ul iljlill..:,, ✓l-· :,.·,: \\t\ U vv t,.Jj\.ill~l..11, ~,t,.:11, J.,:.ul _,:T ._,.,;-J...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
<no chunks produced>
```


## `wipo_eg088ar_1.pdf`

- type: `pdf` / `text`
- detected: law, ar, 13 pages, 24 chunks
- warnings: 2 (first: document appears to have been laid out VISUALLY (Arabic words correct, neutral characters mirrored). Evidence: 35 mirror)

**SOURCE** (raw extractor output)

```
اﻟﺠﺮﯾﺪة اﻟﺮﺳﻤﯿﺔ– اﻟﻌﺪد ١٣ ﻣﻜﺮر)ب( ﻓ ٦ﻰ أﻏﺴﻄﺲ ﺳﻨﺔ ٣٢٠٢ ٢ ﻗﺎﻧﻮﻥ ﺭﻗﻢ ٣٦١ ﻟﺴﻨﺔ ٣٢٠٢ ﺑﺈﺻﺪﺍﺭ ﻗﺎﻧﻮﻥ ﺇﻧﺸﺎء ﺍﳉﻬﺎﺯ ﺍﳌﺼﺮﻯ ﻟﻠﻤﻠﻜﻴﺔ ﺍﻟﻔﻜﺮﻳﺔ ﺑﺎﺳﻢ ﺍﻟﺸﻌﺐ ﺭﺋﻴﺲ ﺍﳉﻤﻬﻮﺭﻳﺔ ﻗﺭﺭ ﻤﺠﻠﺱ ﺍﻟﻨﻭﺍﺏ ﺍﻟﻘﺎﻨﻭﻥ ﺍﻵﺘﻲ ﻨﺼﻪ ، ﻭﻗﺩ ﺃﺼﺩﺭﻨﺎﻩ: ) ﺍﳌﺎﺩﺓ ﺍﻷﻭﱃ( ﻴﻌﻤل ﺒﺄﺤﻜﺎﻡ ﻫﺫﺍ ﺍﻟﻘﺎﻨﻭﻥ ﻭﺍﻟﻘﺎﻨﻭﻥ ﺍﻟﻤﺭﺍﻓﻕ ﻟﻪ ﻓﻲ ﺸﺄﻥ ﺇﻨﺸﺎﺀ ﺍﻟﺠﻬـﺎﺯ ﺍﻟﻤـﺼﺭﻯ ﻟﻠﻤﻠﻜﻴﺔ ﺍﻟ ﻔﻜﺭﻴﺔ ﻭﻴﻠﻐﻰ ﻜل ﺤﻜﻡ ﻴﺨﺎﻟﻑ ﺃﺤﻜﺎﻡ ﻫﺫﺍ ﺍﻟﻘﺎﻨﻭﻥ ﻭﺍﻟﻘﺎﻨﻭﻥ ﺍﻟﻤﺭﺍﻓﻕ . )ﺍﳌﺎﺩﺓ ﺍﻟﺜﺎﻧﻴﺔ ( ﻴﺤل ﺍﻟﺠﻬﺎﺯ ﺍﻟﻤﺼﺭﻯ ﻟﻠﻤﻠﻜ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
الجریدة الرسمیة- العدد 13 مكرر(ب) ف 6ي اغسطس سنة 3202 2 قانون رقم 361 لسنة 3202
```

- `section`: 'قانون' | `clause_id`: 'sec_قانون' | `chunk_strategy`: 'structural'
- normalization applied: ['collapse_whitespace', 'normalize_alef', 'normalize_alef_maksura', 'normalize_digits:to_western', 'normalize_punctuation']

## `synthetic_contract_ar.docx`

- type: `docx`
- detected: contract, mixed, 2 pages, 17 chunks
- warnings: 2 (first: DOCX has no stored pagination; page numbers are derived from explicit page breaks and are not comparable to PDF page num)

**SOURCE** (raw extractor output)

```
عقد توريد وتركيب - SYNTHETIC TEST DOCUMENT [بيانات مختلقة بالكامل لأغراض الاختبار / FABRICATED TEST DATA] تحرر هذا العقد بين شركة النيل الأزرق للتوريدات الهندسية ش.م.م (طرف أول) و شركة دلتا طنطا للمقاولات العامة (طرف ثان). تمهيد حيث أن الطرف الأول شركة مساهمة مصرية مقيدة بالسجل التجاري بالقاهرة تحت رقم ٤٤١٢٩ ويرغب في التعاقد مع الطرف الثاني على النحو المبين بهذا العقد، وحيث أن الطرف الثاني يقر بأن...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
عقد توريد وتركيب - SYNTHETIC TEST DOCUMENT [بيانات مختلقة بالكامل لاغراض الاختبار / FABRICATED TEST DATA] تحرر هذا العقد بين شركة النيل الازرق للتوريدات الهندسية ش.م.م (طرف اول) و شركة دلتا طنطا للمقاولات العامة (طرف ثان).
```

- `section`: None | `clause_id`: None | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef']

## `synthetic_contract_bilingual.pdf`

- type: `pdf` / `text`
- detected: contract, mixed, 3 pages, 22 chunks
- warnings: 2 (first: document appears to have been laid out VISUALLY (Arabic words correct, neutral characters mirrored). Evidence: 11 line(s)

**SOURCE** (raw extractor output)

```
ﻋﻘﺪ ﺗﻮﺭﻳﺪ ﻭﺗﺮﻛﻴﺐ SUPPLY AND INSTALLATION AGREEMENT [SYNTHETIC TEST DOCUMENT - FABRICATED DATA] .(٢١ ﺷﺎﺭﻉ ﺍﻟﻨﻴﻞ، ﺍﻟﺪﻗﻲ، ﺍﻟﺠﻴﺰﺓ )ﻃﺮﻑ ﺃﻭﻝ(. ﺛﺎﻧﻴﺎ: ﺷﺮﻛﺔ ﺩﻟﺘﺎ ﻃﻨﻄﺎ ﻟﻠﻤﻘﺎﻭﻻﺕ ﺍﻟﻌﺎﻣﺔ، ﻭﻣﻘﺮﻫﺎ ٤٤ ﺷﺎﺭﻉ ﺍﻟﺠﻴﺶ، ﻃﻨﻄﺎ، ﺍﻟﻐﺮﺑﻴﺔ )ﻃﺮﻑ ﺛﺎﻥ ﺇﻧﻪ ﻓﻲ ﻳﻮﻡ ﺍﻷﺣﺪ ﺍﻟﻤﻮﺍﻓﻖ ٥١ ﻳﻨﺎﻳﺮ ٦٢٠٢ ﺗﺤﺮﺭ ﻫﺬﺍ ﺍﻟﻌﻘﺪ ﺑﻴﻦ ﻛﻞ ﻣﻦ: ﺃﻭﻻ: ﺷﺮﻛﺔ ﺍﻟﻨﻴﻞ ﺍﻷﺯﺭﻕ ﻟﻠﺘﻮﺭﻳﺪﺍﺕ ﺍﻟﻬﻨﺪﺳﻴﺔ ﺵ.ﻡ.ﻡ، ﻭﻣﻘﺮﻫﺎ Made on 15 January 2026 between Blue Nile Engineering Suppli...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
عقد توريد وتركيب
```

- `section`: 'عقد توريد وتركيب' | `clause_id`: 'sec_عقد_توريد_وتركيب' | `chunk_strategy`: 'structural'
- normalization applied: []

## `synthetic_lease_bilingual.docx`

- type: `docx`
- detected: contract, mixed, 1 pages, 18 chunks
- warnings: 2 (first: DOCX has no stored pagination; page numbers are derived from explicit page breaks and are not comparable to PDF page num)

**SOURCE** (raw extractor output)

```
LEASE AGREEMENT / عقد إيجار - SYNTHETIC TEST DOCUMENT [FABRICATED TEST DATA - no real parties or premises] 1. Definitions and Interpretation 1.1 In this Lease the following expressions have the meanings given below. 1.2 "Premises" means the third floor of 44 El Geish Street, Tanta, Gharbia. 1.3 "Term" means five (5) years commencing 1 February 2026. 2. Grant and Rent / منح الإيجار والأجرة 2.1 The ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
Clause 1 LEASE AGREEMENT / عقد ايجار - SYNTHETIC TEST DOCUMENT [FABRICATED TEST DATA - no real parties or premises] 1. Definitions and Interpretation
```

- `section`: 'Definitions and Interpretation' | `clause_id`: 'cl_1' | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef']

## `synthetic_memo_mixed.txt`

- type: `txt`
- detected: correspondence, mixed, 1 pages, 4 chunks
- warnings: 1 (first: 7 RTL/reading-order flags raised across 1 pages; see chunk metadata.rtl_flags for detail)

**SOURCE** (raw extractor output)

```
مذكرة داخلية / Internal Memorandum إلى: إدارة الشئون القانونية - Legal Affairs Department من: Ahmed Farouk, Senior Associate التاريخ: ١٥/٠٣/٢٠٢٦ الموضوع: مراجعة عقد التوريد رقم CTR-2026-0147 أولاً: الخلفية تم استلام مسودة العقد من العميل Blue Nile Engineering Supplies بتاريخ ١٢/٠٣/٢٠٢٦. وقد راجعنا البنود من (1) إلى (9) على ضوء أحكام Law No. 182 of 2018 والقانون المدني. ثانياً: الملاحظات الجوهرية 1...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
مذكرة داخلية / Internal Memorandum الي: ادارة الشئون القانونية - Legal Affairs Department من: Ahmed Farouk، Senior Associate التاريخ: 15/03/2026 الموضوع: مراجعة عقد التوريد رقم CTR-2026-0147
```

- `section`: None | `clause_id`: None | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef', 'normalize_alef_maksura', 'normalize_digits:to_western', 'normalize_punctuation']

## `synthetic_statute_ar.txt`

- type: `txt`
- detected: law, ar, 1 pages, 11 chunks

**SOURCE** (raw extractor output)

```
قانون رقم 17 لسنة 2026 بإصدار قانون تنظيم التوريدات الحكومية باسم الشعب رئيس الجمهورية بعد الاطلاع على الدستور؛ وعلى القانون المدني الصادر بالقانون رقم 131 لسنة 1948؛ قرر مجلس النواب القانون الآتي نصه، وقد أصدرناه: الباب الأول أحكام عامة الفصل الأول في التعريفات والنطاق المادة (1) يعمل بأحكام القانون المرفق في شأن تنظيم التوريدات الحكومية، ويلغى كل حكم يخالف أحكامه. المادة (2) يقصد في تطبيق أحكام ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
قانون رقم 17 لسنة 2026 باصدار قانون تنظيم التوريدات الحكومية باسم الشعب رئيس الجمهورية بعد الاطلاع علي الدستور؛ وعلي القانون المدني الصادر بالقانون رقم 131 لسنة 1948؛ قرر مجلس النواب القانون الاتي نصه، وقد اصدرناه:
```

- `section`: None | `clause_id`: None | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef', 'normalize_alef_maksura']

## `synthetic_visual_order_ar.txt`

- type: `txt`
- detected: law, ar, 1 pages, 8 chunks
- warnings: 1 (first: 31 RTL/reading-order flags raised across 1 pages; see chunk metadata.rtl_flags for detail)

**SOURCE** (raw extractor output)

```
2026 ﺔﻨﺴﻟ 17 ﻢﻗﺭ ﻥﻮﻧﺎﻗ ﺔﻴﻣﻮﻜﺤﻟﺍ ﺕﺍﺪﻳﺭﻮﺘﻟﺍ ﻢﻴﻈﻨﺗ ﻥﻮﻧﺎﻗ ﺭﺍﺪﺻﺈﺑ ﺐﻌﺸﻟﺍ ﻢﺳﺎﺑ ﺔﻳﺭﻮﻬﻤﺠﻟﺍ ﺲﻴﺋﺭ ؛ﺭﻮﺘﺳﺪﻟﺍ ﻰﻠﻋ ﻉﻼﻃﻻﺍ ﺪﻌﺑ ؛1948 ﺔﻨﺴﻟ 131 ﻢﻗﺭ ﻥﻮﻧﺎﻘﻟﺎﺑ ﺭﺩﺎﺼﻟﺍ ﻲﻧﺪﻤﻟﺍ ﻥﻮﻧﺎﻘﻟﺍ ﻰﻠﻋﻭ :ﻩﺎﻧﺭﺪﺻﺃ ﺪﻗﻭ ،ﻪﺼﻧ ﻲﺗﻵﺍ ﻥﻮﻧﺎﻘﻟﺍ ﺏﺍﻮﻨﻟﺍ ﺲﻠﺠﻣ ﺭﺮﻗ ﻝﻭﻷﺍ ﺏﺎﺒﻟﺍ ﺔﻣﺎﻋ ﻡﺎﻜﺣﺃ ﻝﻭﻷﺍ ﻞﺼﻔﻟﺍ ﻕﺎﻄﻨﻟﺍﻭ ﺕﺎﻔﻳﺮﻌﺘﻟﺍ ﻲﻓ (1) ﺓﺩﺎﻤﻟﺍ .ﻪﻣﺎﻜﺣﺃ ﻒﻟﺎﺨﻳ ﻢﻜﺣ ﻞﻛ ﻰﻐﻠﻳﻭ ،ﺔﻴﻣﻮﻜﺤﻟﺍ ﺕﺍﺪﻳﺭﻮﺘﻟﺍ ﻢﻴﻈﻨﺗ ﻥﺄﺷ ﻲﻓ ﻖﻓﺮﻤﻟﺍ ﻥﻮﻧﺎﻘﻟﺍ ﻡﺎﻜﺣﺄﺑ ﻞﻤﻌﻳ (2) ﺓﺩﺎﻤﻟﺍ :ﺎﻬﻨﻣ ﻞﻛ ﻦﻳﺮﻗ ﻦﻴﺒﻤﻟﺍ ﻰﻨﻌﻤ...
```

**PIPELINE** (chunk 1 as delivered to M2/M3)

```
قانون رقم 17 لسنة 2026 باصدار قانون تنظيم التوريدات الحكومية باسم الشعب رئيس الجمهورية بعد االطالع علي الدستور؛ وعلي القانون المدني الصادر بالقانون رقم 131 لسنة 1948؛ قرر مجلس النواب القانون االتي نصه، وقد اصدرناه: لولاا بابلا ةماع ماكحا لولاا لصفلا قاطنلاو تافيرعتلا يف (1) ةداملا .هماكحا فلاخي مكح لك ىغليو ،ةيموكحلا تاديروتلا ميظنت ناش يف قفرملا نوناقلا ماكحاب لمعي
```

- `section`: None | `clause_id`: None | `chunk_strategy`: 'structural'
- normalization applied: ['normalize_alef', 'normalize_alef_maksura']
