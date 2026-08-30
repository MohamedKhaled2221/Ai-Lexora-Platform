"""Download publicly available Arabic legal documents into ``test_corpus/public/``.

INTERIM CORPUS ONLY. These are published Egyptian statutes and constitutional
texts from open sources. They stand in for firm documents until an anonymized
sample batch arrives. Nothing here reflects the firm's own formatting, and no
conclusion drawn from them should be reported as validated against firm data.

Sources are all public-law texts (no copyright restriction on legislative text)
served over HTTPS from stable hosts. Each downloaded file is probed with our own
type detector and recorded in ``download_log.json`` with its verdict, so the
manifest can state what each file actually is rather than what we hoped it was.

Run::

    python scripts/fetch_public_corpus.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PUBLIC_CORPUS_DIR  # noqa: E402

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
}
TIMEOUT = 90

# WIPO Lex serves national legislation PDFs from a CDN behind *signed* URLs.
# The bare path 404s, so we scrape each legislation detail page for the signed
# link and follow it immediately (the signature is short-lived).
# Egyptian Arabic originals live under ``/laws/ar/eg/``.
WIPO_DETAIL = "https://www.wipo.int/wipolex/en/legislation/details/{}"
WIPO_PDF_RE = r"https?://wipolex-res\.wipo\.int/edocs/lexdocs/laws/ar/eg/[^\"'<>\s]+\.pdf[^\"'<>\s]*"

# Detail-page ids known to be Egyptian, plus a probe range to pick up more.
WIPO_KNOWN_IDS = [22066, 22397, 19870, 22065, 22067, 22398, 19871, 22064]
WIPO_PROBE_RANGE = list(range(22050, 22130))

# Direct, individually-verified URLs from other open repositories.
DIRECT_SOURCES: list[dict] = [
    {
        "url": "https://www.constituteproject.org/constitution/Egypt_2014.pdf?lang=ar",
        "name": "constitute_egypt_2014_ar.pdf",
        "source": "Constitute Project (comparativeconstitutionsproject.org)",
        "description": "دستور جمهورية مصر العربية 2014 -- Egyptian Constitution 2014, Arabic",
        "language_expected": "ar",
    },
    {
        "url": "https://www.constituteproject.org/constitution/Egypt_2019.pdf?lang=ar",
        "name": "constitute_egypt_2019_ar.pdf",
        "source": "Constitute Project",
        "description": "دستور جمهورية مصر العربية 2019 (تعديلات) -- Egyptian Constitution as amended 2019, Arabic",
        "language_expected": "ar",
    },
    {
        "url": "https://www.constituteproject.org/constitution/Egypt_2014.pdf",
        "name": "constitute_egypt_2014_en.pdf",
        "source": "Constitute Project",
        "description": "Egyptian Constitution 2014, English translation",
        "language_expected": "en",
    },
    {
        "url": "https://constitutionnet.org/sites/default/files/Egypt%20Constitution.pdf",
        "name": "eg_constitution_2014_en.pdf",
        "source": "ConstitutionNet (International IDEA)",
        "description": "Constitution of the Arab Republic of Egypt, English translation",
        "language_expected": "en",
    },
    {
        "url": "https://www.ecoi.net/en/file/local/1421080/1930_1515491436_5a4cbae14.pdf",
        "name": "eg_official_gazette_excerpt.pdf",
        "source": "ecoi.net (Austrian Red Cross)",
        "description": "Egyptian Official Gazette excerpt (Law 70/2017 on Associations), "
                       "unofficial English translation",
        "language_expected": "en",
    },
]

MAX_ARABIC_PDFS = 8
MIN_BYTES = 20_000       # anything smaller is an error page, not a statute
MAX_BYTES = 40_000_000


def _looks_like_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-"


def _get(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"    ! request failed: {exc}")
        return None
    if r.status_code != 200:
        return None
    if not _looks_like_pdf(r.content):
        return None
    if not (MIN_BYTES <= len(r.content) <= MAX_BYTES):
        print(f"    ! size {len(r.content)} outside accepted range")
        return None
    return r.content


def fetch_wipo(dest: Path, log: list[dict]) -> int:
    """Scrape WIPO Lex detail pages for Egyptian statutes in Arabic.

    For each candidate legislation id: fetch the HTML detail page, pull the
    signed CDN link to the Arabic PDF, and download it straight away before the
    signature expires. Ids that are not Egyptian simply yield no ``/ar/eg/``
    link and are skipped.
    """
    import html
    import re

    seen_docs: set[str] = set()
    n_ar = 0
    ids = WIPO_KNOWN_IDS + [i for i in WIPO_PROBE_RANGE if i not in WIPO_KNOWN_IDS]
    print(f"Scraping WIPO Lex detail pages for Egyptian legislation "
          f"(up to {MAX_ARABIC_PDFS} Arabic PDFs)...")

    for doc_id in ids:
        if n_ar >= MAX_ARABIC_PDFS:
            break
        try:
            r = requests.get(WIPO_DETAIL.format(doc_id), headers={**HEADERS, "Accept": "text/html"},
                             timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue

        matches = re.findall(WIPO_PDF_RE, r.text)
        signed = [html.unescape(m) for m in matches if "Signature" in m]
        if not signed:
            continue
        url = signed[0]

        code_match = re.search(r"/(eg\d+ar[^/?]*)\.pdf", url)
        code = code_match.group(1) if code_match else f"doc{doc_id}"
        if code in seen_docs:
            continue

        content = _get(url)
        if content is None:
            continue

        seen_docs.add(code)
        name = f"wipo_{code}.pdf"
        (dest / name).write_bytes(content)
        n_ar += 1
        print(f"  [{n_ar}] {name}  ({len(content)/1024:.0f} KB)  <- detail id {doc_id}")
        log.append(
            {
                "file": name,
                "url": url.split("?")[0] + "  (signed URL; re-fetch via detail page)",
                "detail_page": WIPO_DETAIL.format(doc_id),
                "source": "WIPO Lex (wipo.int/wipolex)",
                "description": "Egyptian legislation, Arabic original as published by WIPO Lex",
                "language_expected": "ar",
                "bytes": len(content),
            }
        )
        time.sleep(0.8)  # be polite to the host
    return n_ar


def fetch_direct(dest: Path, log: list[dict]) -> int:
    n = 0
    print("\nFetching direct sources...")
    for spec in DIRECT_SOURCES:
        print(f"  {spec['name']} ...")
        content = _get(spec["url"])
        if content is None:
            print("    ! unavailable, skipped")
            continue
        (dest / spec["name"]).write_bytes(content)
        n += 1
        print(f"    ok ({len(content)/1024:.0f} KB)")
        log.append({**spec, "file": spec["name"], "bytes": len(content)})
        time.sleep(0.6)
    return n


def classify_all(dest: Path, log: list[dict]) -> None:
    """Run our own type detector over everything downloaded.

    This is the corpus's ground truth for "is this scanned or text-based" --
    recorded now so the manifest and the evaluation report describe the files
    as they actually are.
    """
    from src.type_detection import detect

    print("\nClassifying downloaded files with src.type_detection...")
    by_file = {e["file"]: e for e in log}
    for pdf in sorted(dest.glob("*.pdf")):
        entry = by_file.setdefault(pdf.name, {"file": pdf.name})
        try:
            det = detect(pdf)
            rep = det.pdf_report
            entry.update(
                file_type=det.file_type.value,
                pdf_kind=det.pdf_kind,
                route=det.route.value,
                n_pages=rep.n_pages if rep else None,
                total_chars=rep.total_chars if rep else None,
                scanned_pages=rep.scanned_pages if rep else [],
                encrypted=rep.is_encrypted if rep else False,
            )
            print(f"  {pdf.name:<34} {det.pdf_kind:<8} "
                  f"{entry['n_pages']:>4} pages  {entry['total_chars']:>8} chars")
        except Exception as exc:  # noqa: BLE001
            entry["detect_error"] = str(exc)
            print(f"  {pdf.name:<34} ERROR {exc}")

    # Sample the text so the manifest can state the real language mix.
    try:
        import fitz

        from src.structure_preservation import detect_language

        for pdf in sorted(dest.glob("*.pdf")):
            entry = by_file.get(pdf.name, {})
            try:
                with fitz.open(pdf) as d:
                    sample = "".join(d[i].get_text() for i in range(min(4, d.page_count)))
                entry["language_detected"] = detect_language(sample).value
                entry["sample_text"] = " ".join(sample.split())[:180]
            except Exception:  # noqa: BLE001
                pass
    except ImportError:
        pass

    log.clear()
    log.extend(by_file.values())


def main() -> int:
    dest = PUBLIC_CORPUS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []

    n_wipo = fetch_wipo(dest, log)
    n_direct = fetch_direct(dest, log)
    total = n_wipo + n_direct
    print(f"\nDownloaded {total} file(s) into {dest}")

    if total:
        classify_all(dest, log)

    (dest / "download_log.json").write_text(
        json.dumps(
            {
                "note": "INTERIM public corpus -- stand-in for firm documents, "
                        "which have not been received. No firm data here.",
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files": sorted(log, key=lambda e: e.get("file", "")),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {dest / 'download_log.json'}")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
