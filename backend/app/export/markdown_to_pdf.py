"""
Turns Markdown text (the same constrained subset produced by the Groq
provider -- headings, bold, bullet/numbered lists, GFM tables, plain
paragraphs) into a downloadable PDF. Used by the notebook report endpoint.

Uses fpdf2 rather than converting a .docx to PDF (e.g. via LibreOffice)
so the container doesn't need a whole office suite installed just for
this -- fpdf2 is pure Python and renders directly. Mirrors the parsing
in export/markdown_to_docx.py (same regexes, same constrained Markdown
subset) so both exporters stay in sync if the model's output format
ever changes; only the rendering backend differs.

Visual design: a branded header band (logo dot + title) on page 1, a
slim brand rule + running title on later pages, brand-colored section
markers/rules for headings, drawn bullet dots (rather than a "-" glyph,
since fpdf2's core fonts can't render a real bullet character), a
tinted/zebra-striped table style, and a "Sources" section with numbered
badge chips instead of a plain list. All colors reuse the same brand
red ramp as the frontend's Tailwind config so exported PDFs look like
part of the same product rather than a default-styled document.

Known limitation: table cells use fixed-width single-line cells (no
in-cell text wrapping), unlike the Word exporter's real wrapping table
cells. Fine for the short comparison-style tables the system prompt
asks the model to produce; revisit with fpdf2's newer table() API if
long cell content becomes common.
"""
import io
import re
from datetime import datetime
from typing import Optional

from fpdf import FPDF

CITATION_TOKEN = re.compile(r"\[S(\d+)\]")
BOLD_OR_CITATION = re.compile(r"(\*\*.+?\*\*)|(\[S\d+\])")
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
ORDERED_ITEM = re.compile(r"^\s*\d+[.)]\s+(.*)$")
UNORDERED_ITEM = re.compile(r"^\s*[-*]\s+(.*)$")
HEADING = re.compile(r"^(#{1,3})\s+(.*)$")

PAGE_W = 210  # A4, mm
MARGIN = 20
CONTENT_WIDTH = PAGE_W - 2 * MARGIN
BODY_SIZE = 11
HEADING_SIZES = {0: 20, 1: 16, 2: 13, 3: 12}
BAND_HEIGHT = 34

# Same ramp as frontend/tailwind.config.js `brand.*`, anchored on the
# logo red (#E30613 at 600), plus the neutral slate scale used alongside
# it in the UI -- keeping the exported PDF visually consistent with the
# web app rather than introducing a separate ad-hoc palette.
BRAND = {
    50: (253, 240, 241),
    100: (251, 223, 224),
    200: (247, 185, 189),
    500: (230, 31, 43),
    600: (227, 6, 19),
    700: (179, 7, 17),
    800: (140, 8, 15),
}
SLATE = {
    900: (15, 23, 42),
    700: (51, 65, 85),
    400: (148, 163, 184),
    200: (226, 232, 240),
    50: (248, 250, 252),
}

# fpdf2's built-in core fonts (Helvetica, Times, Courier) only support the
# latin-1 character set, not full Unicode -- and the LLM output (or a
# document's filename) regularly contains smart quotes/dashes that fall
# outside it. Embedding a Unicode TTF font would fix this properly, but
# that's a binary asset to ship in the repo/container for one formatting
# nicety, and Hugging Face's git host already rejects large binaries on
# push (see docs/rag_notebook_walkthrough.pdf). Transliterating to plain
# ASCII equivalents keeps this dependency-free; anything left over that
# still can't be encoded is replaced with "?" rather than crashing the
# export.
_UNICODE_REPLACEMENTS = {
    "—": "-", "–": "-",   # em dash, en dash
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',   # curly double quotes
    "…": "...",                # ellipsis
    "•": "-",                  # bullet
    " ": " ",                  # non-breaking space
}


def _ascii_safe(text: str) -> str:
    if not text:
        return text
    for src, dst in _UNICODE_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class _ReportPDF(FPDF):
    def __init__(self, title: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_title = _ascii_safe(title) or "Notebook Report"
        self.alias_nb_pages()

    def header(self):
        if self.page_no() == 1:
            self._first_page_band()
        else:
            self._continuation_band()

    def _first_page_band(self):
        self.set_fill_color(*BRAND[600])
        self.rect(0, 0, PAGE_W, BAND_HEIGHT, style="F")
        # Small vector "logo dot" (white ring, brand-colored center) so the
        # header reads as branded without shipping a binary logo asset.
        self.set_fill_color(255, 255, 255)
        self.ellipse(MARGIN, 9, 10, 10, style="F")
        self.set_fill_color(*BRAND[600])
        self.ellipse(MARGIN + 2.6, 11.6, 4.8, 4.8, style="F")

        self.set_xy(MARGIN + 15, 7.5)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 16)
        self.multi_cell(CONTENT_WIDTH - 15, 7, self.report_title)

        self.set_xy(MARGIN + 15, 20)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*BRAND[100])
        self.cell(0, 6, f"Generated {datetime.now().strftime('%B %d, %Y')} - RAG NoteBook")

        self.set_y(BAND_HEIGHT + 10)
        self.set_text_color(*SLATE[900])
        self.set_font("Helvetica", "", BODY_SIZE)

    def _continuation_band(self):
        self.set_fill_color(*BRAND[600])
        self.rect(0, 0, PAGE_W, 3, style="F")
        self.set_xy(MARGIN, 10)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*SLATE[400])
        self.cell(CONTENT_WIDTH, 5, self.report_title)
        self.set_y(22)
        self.set_text_color(*SLATE[900])
        self.set_font("Helvetica", "", BODY_SIZE)

    def footer(self):
        self.set_y(-16)
        self.set_draw_color(*SLATE[200])
        self.set_line_width(0.2)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.set_y(-13)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*SLATE[400])
        self.cell(CONTENT_WIDTH * 0.75, 8, "Generated by RAG NoteBook -- verify against the original source documents.")
        self.set_font("Helvetica", "", 8)
        self.cell(CONTENT_WIDTH * 0.25, 8, f"Page {self.page_no()}/{{nb}}", align="R")


def _write_inline(pdf: FPDF, text: str, size: int = BODY_SIZE) -> None:
    """Writes `text` at the current cursor position, honoring **bold**
    spans and turning [S<n>] citation tokens into a small brand-colored
    bracketed number -- fpdf2 has no superscript-run API, so this is the
    plain-text equivalent of the docx exporter's superscript citation
    markers."""
    pos = 0
    for match in BOLD_OR_CITATION.finditer(text):
        if match.start() > pos:
            pdf.set_font("Helvetica", "", size)
            pdf.write(6, text[pos:match.start()])
        bold_span, citation_span = match.groups()
        if bold_span:
            pdf.set_font("Helvetica", "B", size)
            pdf.write(6, bold_span[2:-2])
        elif citation_span:
            num = CITATION_TOKEN.match(citation_span).group(1)
            pdf.set_font("Helvetica", "B", max(size - 2, 7))
            pdf.set_text_color(*BRAND[600])
            pdf.write(6, f"[{num}]")
            pdf.set_text_color(*SLATE[900])
        pos = match.end()
    if pos < len(text):
        pdf.set_font("Helvetica", "", size)
        pdf.write(6, text[pos:])
    pdf.ln(6)


def _write_indented(pdf: FPDF, text: str, indent: float, size: int = BODY_SIZE) -> None:
    """Renders one wrapped paragraph with a hanging indent -- wrapped
    continuation lines land under the text, not under the bullet/number
    marker, by temporarily moving fpdf2's left margin (the anchor it
    wraps back to) in for the duration of this call."""
    pdf.set_left_margin(indent)
    pdf.set_x(indent)
    _write_inline(pdf, text, size=size)
    pdf.set_left_margin(MARGIN)


def _section_heading(pdf: FPDF, text: str, size: int) -> None:
    """A small filled brand square + colored bold text + a thin rule
    underneath, used for both '## document.md' subsections and the
    'Sources' block -- replaces the old plain bold-text-only heading."""
    pdf.ln(3)
    y0 = pdf.get_y()
    pdf.set_fill_color(*BRAND[600])
    pdf.rect(MARGIN, y0 + 1.8, 3.2, 3.2, style="F")
    pdf.set_xy(MARGIN + 6.5, y0)
    pdf.set_text_color(*BRAND[800])
    pdf.set_font("Helvetica", "B", size)
    pdf.multi_cell(CONTENT_WIDTH - 6.5, 8, text)
    rule_y = pdf.get_y() + 1
    pdf.set_draw_color(*BRAND[100])
    pdf.set_line_width(0.4)
    pdf.line(MARGIN, rule_y, MARGIN + CONTENT_WIDTH, rule_y)
    pdf.set_y(rule_y + 4)
    pdf.set_text_color(*SLATE[900])
    pdf.set_font("Helvetica", "", BODY_SIZE)


def _parse_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows = []
    i = start
    while i < len(lines) and TABLE_ROW.match(lines[i]):
        if i == start + 1 and re.fullmatch(r"[\s|:-]+", lines[i].strip()):
            i += 1
            continue
        cells = [c.strip() for c in TABLE_ROW.match(lines[i]).group(1).split("|")]
        rows.append(cells)
        i += 1
    return rows, i


def render_markdown_to_pdf(
    content: str,
    citations: Optional[list[dict]] = None,
    title: Optional[str] = None,
) -> io.BytesIO:
    content = _ascii_safe(content)

    pdf = _ReportPDF(title=title or "")
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_margins(MARGIN, 10, MARGIN)
    pdf.add_page()

    lines = content.replace("\r\n", "\n").split("\n")
    i = 0
    ordered_counter = 0
    while i < len(lines):
        line = lines[i]

        if not line.strip():
            ordered_counter = 0
            i += 1
            continue

        heading_match = HEADING.match(line)
        if heading_match:
            ordered_counter = 0
            level = len(heading_match.group(1))
            _section_heading(pdf, heading_match.group(2).strip(), HEADING_SIZES.get(level, 12))
            i += 1
            continue

        if TABLE_ROW.match(line) and i + 1 < len(lines) and re.fullmatch(
            r"[\s|:-]+", lines[i + 1].strip()
        ):
            ordered_counter = 0
            rows, i = _parse_table(lines, i)
            if rows:
                col_count = len(rows[0])
                col_w = CONTENT_WIDTH / col_count
                pdf.ln(2)
                pdf.set_x(MARGIN)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_fill_color(*BRAND[50])
                pdf.set_text_color(*BRAND[800])
                pdf.set_draw_color(*SLATE[200])
                pdf.set_line_width(0.2)
                for cell in rows[0]:
                    pdf.cell(col_w, 9, cell, border=1, fill=True, align="C")
                pdf.ln(9)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*SLATE[700])
                for r_idx, row_cells in enumerate(rows[1:]):
                    pdf.set_x(MARGIN)
                    fill = r_idx % 2 == 1
                    if fill:
                        pdf.set_fill_color(*SLATE[50])
                    for c in range(col_count):
                        pdf.cell(
                            col_w, 9,
                            row_cells[c] if c < len(row_cells) else "",
                            border=1, fill=fill,
                        )
                    pdf.ln(9)
                pdf.set_text_color(*SLATE[900])
                pdf.ln(4)
            continue

        ordered_match = ORDERED_ITEM.match(line)
        if ordered_match:
            ordered_counter += 1
            pdf.set_x(MARGIN)
            pdf.set_font("Helvetica", "B", BODY_SIZE)
            pdf.set_text_color(*BRAND[700])
            label = f"{ordered_counter}. "
            pdf.write(6, label)
            indent = MARGIN + pdf.get_string_width(label)
            pdf.set_text_color(*SLATE[900])
            _write_indented(pdf, ordered_match.group(1), indent)
            i += 1
            continue

        unordered_match = UNORDERED_ITEM.match(line)
        if unordered_match:
            ordered_counter = 0
            bullet_y = pdf.get_y()
            pdf.set_fill_color(*BRAND[500])
            pdf.ellipse(MARGIN + 1, bullet_y + 2.6, 1.6, 1.6, style="F")
            _write_indented(pdf, unordered_match.group(1), MARGIN + 6)
            i += 1
            continue

        ordered_counter = 0
        pdf.set_x(MARGIN)
        _write_inline(pdf, line.strip())
        i += 1

    if citations:
        _section_heading(pdf, "Sources", HEADING_SIZES[2])
        for idx, c in enumerate(citations, start=1):
            page = c.get("page")
            filename = _ascii_safe(c.get("filename", "unknown"))
            label = filename + (f", page {page}" if page is not None else "")
            row_y = pdf.get_y()
            pdf.set_fill_color(*BRAND[600])
            pdf.ellipse(MARGIN, row_y + 0.4, 5, 5, style="F")
            pdf.set_xy(MARGIN, row_y + 0.4)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(5, 5, str(idx), align="C")
            pdf.set_xy(MARGIN + 8, row_y)
            pdf.set_text_color(*SLATE[700])
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(CONTENT_WIDTH - 8, 6, label)
            pdf.ln(1)
        pdf.set_text_color(*SLATE[900])

    return io.BytesIO(bytes(pdf.output()))
