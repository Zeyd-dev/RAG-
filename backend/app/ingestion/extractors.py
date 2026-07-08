"""
Text extraction for supported file types: PDF, DOCX, TXT, Markdown.

Each extractor returns a list of (page_number, text) tuples so downstream
chunking can preserve page-level provenance for citations. TXT/Markdown
have no real "pages" — they are treated as a single page (page=1).
"""
import re
from dataclasses import dataclass
from pathlib import Path

import markdown as md_lib
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from pypdf import PdfReader


@dataclass
class PageText:
    page: int
    text: str


class UnsupportedFileType(Exception):
    pass


# Matches runs of single letters (optionally with an apostrophe, for
# contractions) each separated by a single space, e.g. "P o t e n t i a l".
# This shows up when pypdf extracts text from PDFs where a heading or
# emphasized span uses letter-spacing/tracking in the design (common in
# slide-deck-style PDF exports): each glyph is individually positioned in
# the PDF content stream, and pypdf reads the gap between glyphs as a
# literal space even though it's meant as stylistic spacing, not a word
# break.
_LETTER_SPACED_RUN = re.compile(r"(?:(?<=^)|(?<=\s))(?:[A-Za-z']\s){1,}[A-Za-z](?=\s|$|[.,:;!?])")
_LOWER_UPPER_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _fix_letter_spacing(text: str) -> str:
    """
    Collapses letter-spaced runs back into words. Re-inserts a space at
    each lowercase->uppercase boundary in the collapsed run, which
    recovers word breaks correctly for Title Case headings (the common
    case). It can't recover word breaks in an all-lowercase or ALL-CAPS
    spaced run (no case signal to split on), so e.g. a mid-sentence
    spaced-out phrase like "d o e s i t" may fuse into "doesit" instead
    of "does it" -- still far more readable than the original letter-by-
    letter spacing, just not perfectly re-segmented in every case.
    """

    def collapse(match: re.Match) -> str:
        blob = match.group(0).replace(" ", "")
        return _LOWER_UPPER_BOUNDARY.sub(" ", blob)

    return _LETTER_SPACED_RUN.sub(collapse, text)


def extract_pdf(path: str) -> list[PageText]:
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(PageText(page=i, text=_fix_letter_spacing(text)))
    return pages


def extract_docx(path: str) -> list[PageText]:
    """
    DOCX files don't store page numbers the way PDFs do -- pagination is
    computed at render/print time, not saved in the file. What we *can*
    detect are explicit manual page breaks (Ctrl+Enter in Word, or a
    paragraph's "page break before" property), which many structured
    documents -- reports, theses, chapters -- do use between sections.
    We split on those. Documents that rely purely on Word's automatic
    line-wrap pagination (no manual breaks at all) will still come back
    as a single page, since recovering that would require actually
    rendering the document the way Word does, which is out of scope here.
    """
    doc = DocxDocument(path)
    pages: list[list[str]] = [[]]

    for para in doc.paragraphs:
        if para.paragraph_format.page_break_before:
            pages.append([])

        pages[-1].append(para.text)

        # An explicit page-break character (Ctrl+Enter) shows up as a
        # <w:br w:type="page"/> element inside one of the paragraph's runs.
        has_trailing_break = any(
            br.get(qn("w:type")) == "page"
            for run in para.runs
            for br in run._element.findall(".//" + qn("w:br"))
        )
        if has_trailing_break:
            pages.append([])

    page_texts = ["\n".join(lines) for lines in pages if any(line.strip() for line in lines)]
    if not page_texts:
        page_texts = [""]

    return [PageText(page=i, text=text) for i, text in enumerate(page_texts, start=1)]


def extract_txt(path: str) -> list[PageText]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return [PageText(page=1, text=text)]


def extract_markdown(path: str) -> list[PageText]:
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    html = md_lib.markdown(raw)
    # Strip tags crudely to get plain text for chunking; raw markdown text
    # is kept (not the HTML) since it's already human-readable.
    return [PageText(page=1, text=raw)]


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".txt": extract_txt,
    ".md": extract_markdown,
    ".markdown": extract_markdown,
}


def extract_text(path: str, suffix: str) -> list[PageText]:
    fn = EXTRACTORS.get(suffix.lower())
    if not fn:
        raise UnsupportedFileType(f"Unsupported file type: {suffix}")
    return fn(path)


def page_count_for(pages: list[PageText]) -> int:
    return len(pages)
