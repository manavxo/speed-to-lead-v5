"""
Speed to Lead v5 — Phase Summary PDF Report
============================================
"""

import sys
import os

# Add the skill's template directory to path so we can import the base
sys.path.insert(0, os.path.expanduser("~/AppData/Local/hermes/skills/software-development/pdf-report-generation/templates"))

from fpdf import FPDF
from pathlib import Path
import io
import re
import os as os_mod

SOURCE_MD = Path(__file__).parent / "report_source.md"
OUT_PDF = Path(__file__).parent / "SPEED_TO_LEAD_v5_BUILD_PROGRESS.pdf"

TITLE = "Speed to Lead v5"
SUBTITLE = "Build Progress Report — Phases 0 Through 4"
KICKER = (
    "Five phases completed, 12 total. Test suite grown from 128 to 151 passing tests. "
    "Every change follows TDD: RED before GREEN, full suite before commit, QA subagent after every phase."
)
CLASSIFICATION = "INTERNAL BUILD REPORT  |  v1.0  |  JUNE 20, 2026"

COLOR_PRIMARY = (79, 70, 229)
COLOR_SECONDARY = (30, 41, 59)
COLOR_MUTED = (100, 116, 139)
COLOR_LIGHT_BG = (241, 245, 249)
COLOR_BORDER = (226, 232, 240)
COLOR_TEXT = (15, 23, 42)
COLOR_GREEN = (22, 163, 74)
COLOR_AMBER = (217, 119, 6)
COLOR_RED = (220, 38, 38)

UNICODE_FONT = "C:/Windows/Fonts/arial.ttf"
USE_UNICODE = Path(UNICODE_FONT).exists()


def ascii_safe(text: str) -> str:
    if not text or USE_UNICODE:
        return text
    repl = {
        "\u2014": "--", "\u2013": "-", "\u201c": '"', "\u201d": '"',
        "\u2018": "'", "\u2019": "'", "\u2026": "...", "\u00d7": "x",
        "\u2022": "*", "\u00b7": "-", "\u2192": "->", "\u2190": "<-",
        "\u2713": "[x]", "\u2717": "[ ]", "\u00a9": "(c)", "\u00ae": "(R)",
        "\u2122": "(TM)",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def strip_inline_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", text)
    return text


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        self.bookmarks = []
        self._has_page = False
        if USE_UNICODE:
            from pathlib import Path as P
            FONT_DIR = P("C:/Windows/Fonts/")
            self.add_font("Uni", "", str(FONT_DIR / "arial.ttf"), uni=True)
            self.add_font("Uni", "B", str(FONT_DIR / "arialbd.ttf"), uni=True)
            self.add_font("Uni", "I", str(FONT_DIR / "ariali.ttf"), uni=True)
            self.add_font("Uni", "BI", str(FONT_DIR / "arialbi.ttf"), uni=True)
            self.font_family = "Uni"
        else:
            self.font_family = "Helvetica"

    def _ensure_page(self):
        if not self._has_page:
            self.add_page()
            self._has_page = True

    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(8)
        self.set_font(self.font_family, "B", 8)
        self.set_text_color(*COLOR_MUTED)
        self.cell(0, 5, "SPEED TO LEAD v5  |  BUILD PROGRESS REPORT  |  JUNE 2026",
                 border=0, align="L")
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.2)
        self.line(10, 14, self.w - 10, 14)
        self.set_y(18)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font(self.font_family, "I", 8)
        self.set_text_color(*COLOR_MUTED)
        self.cell(0, 6, f"Page {self.page_no()}", border=0, align="C")

    def add_cover_page(self, title, subtitle, kicker, classification):
        self.add_page()
        self._has_page = True
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(0, 0, self.w, 70, style="F")
        self.set_xy(15, 22)
        self.set_text_color(255, 255, 255)
        self.set_font(self.font_family, "B", 22)
        self.cell(0, 10, "SPEED TO LEAD v5", ln=0)
        self.set_xy(15, 38)
        self.set_font(self.font_family, "", 10)
        self.cell(0, 6, classification, ln=0)
        self.set_xy(15, 110)
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 32)
        self.multi_cell(self.w - 30, 14, title)
        self.set_xy(15, self.get_y() + 8)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "", 16)
        self.multi_cell(self.w - 30, 8, subtitle)
        self.set_xy(15, self.get_y() + 18)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "I", 11)
        self.multi_cell(self.w - 30, 6, kicker)
        self.set_xy(15, self.h - 60)
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.3)
        self.line(15, self.h - 60, self.w - 15, self.h - 60)
        self.set_xy(15, self.h - 52)
        self.set_text_color(*COLOR_MUTED)
        self.set_font(self.font_family, "", 9)
        for line in [
            "Prepared for:  Manav (Project Lead)",
            "Prepared by:   Hermes Agent — Nous Research",
            "Date:          June 20, 2026  |  v1.0",
            "Classification:  Internal Build Document",
        ]:
            self.cell(0, 5, line, ln=1)
            self.set_x(15)

    def add_h1(self, text):
        self._ensure_page()
        self.ln(8)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 20)
        self.multi_cell(0, 10, ascii_safe(text))
        y = self.get_y() + 1
        self.set_draw_color(*COLOR_PRIMARY)
        self.set_line_width(0.6)
        self.line(10, y, 50, y)
        self.bookmarks.append((strip_inline_md(text), self.page_no()))
        self.ln(6)

    def add_h2(self, text):
        self._ensure_page()
        self.ln(4)
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 15)
        self.multi_cell(0, 8, ascii_safe(text))
        self.bookmarks.append(("    " + strip_inline_md(text), self.page_no()))
        self.ln(2)

    def add_h3(self, text):
        self._ensure_page()
        self.ln(3)
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 12)
        self.multi_cell(0, 7, ascii_safe(text))
        self.ln(1)

    def add_h4(self, text):
        self._ensure_page()
        self.ln(2)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "B", 11)
        self.multi_cell(0, 6, ascii_safe(text))
        self.ln(1)

    def add_para(self, text):
        self._ensure_page()
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(0, 5.5, ascii_safe(text))
        self.ln(2)

    def add_bullet(self, text, level=0):
        self._ensure_page()
        indent = 6 + level * 4
        self.set_x(indent)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 10)
        self.cell(5, 5.5, "  " * level + ("\u2022" if level == 0 else "\u2013"), ln=0)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(self.w - indent - 18, 5.5, ascii_safe(text))
        self.ln(0.5)

    def add_status_indicator(self, label, status):
        """Add a colored status indicator."""
        self._ensure_page()
        self.ln(2)
        colors = {
            "passed": (22, 163, 74),
            "warn": (217, 119, 6),
            "done": (22, 163, 74),
            "next": (100, 116, 139),
        }
        c = colors.get(status.lower(), COLOR_MUTED)
        self.set_fill_color(*c)
        self.set_text_color(255, 255, 255)
        self.set_font(self.font_family, "B", 8)
        self.cell(20, 6, f" {status.upper()} ", border=0, fill=True, align="C")
        self.set_x(self.get_x() + 2)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(self.w - 40, 6, ascii_safe(label))
        self.ln(1)

    def add_table(self, headers, rows, col_widths=None):
        self._ensure_page()
        if col_widths is None:
            total_w = self.w - 20
            n_cols = len(headers)
            col_widths = [total_w / n_cols] * n_cols
        total_w = self.w - 20
        col_widths = [max(20, w) for w in col_widths]
        s = sum(col_widths)
        if s != total_w:
            col_widths = [w * (total_w / s) for w in col_widths]
        self.set_fill_color(*COLOR_SECONDARY)
        self.set_text_color(255, 255, 255)
        self.set_font(self.font_family, "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, str(h)[:200], border=0, fill=True, align="L")
        self.ln(8)
        for ri, row in enumerate(rows):
            row_h = 6
            for ci, cell in enumerate(row[:len(col_widths)]):
                chars_per_line = max(1, int(col_widths[ci] / 1.6))
                lines_needed = max(1, (len(str(cell)) + chars_per_line - 1) // chars_per_line)
                row_h = max(row_h, lines_needed * 4.5 + 1)
            if self.get_y() + row_h > self.h - 18:
                self.add_page()
            x0 = self.get_x()
            y0 = self.get_y()
            if ri % 2 == 0:
                self.set_fill_color(*COLOR_LIGHT_BG)
                self.rect(x0, y0, sum(col_widths), row_h, style="F")
            for ci, cell in enumerate(row[:len(col_widths)]):
                self.set_xy(x0 + sum(col_widths[:ci]), y0)
                self.set_text_color(*COLOR_TEXT)
                self.set_font(self.font_family, "", 9)
                self.multi_cell(col_widths[ci], 4.5, str(cell)[:1000], border=0)
            self.set_xy(x0, y0 + row_h)
        self.ln(3)

    def add_rule(self):
        self._ensure_page()
        self.ln(2)
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(10, y, self.w - 10, y)
        self.ln(3)

    def add_callout(self, label, text):
        self._ensure_page()
        self.ln(2)
        x = self.get_x()
        y = self.get_y()
        h = max(20, 5 + (len(text) // 90 + 1) * 5.5)
        if y + h > self.h - 18:
            self.add_page()
            x, y = self.get_x(), self.get_y()
        self.set_fill_color(238, 242, 255)
        self.rect(x, y, self.w - 20, h, style="F")
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(x, y, 3, h, style="F")
        self.set_xy(x + 8, y + 3)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 10)
        self.cell(0, 5, ascii_safe(label), ln=1)
        self.set_x(x + 8)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(self.w - 32, 5.5, ascii_safe(text))
        self.set_y(y + h + 3)


def parse_markdown(lines):
    chunks = []
    i = 0
    quote_accum = []
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            if quote_accum:
                chunks.append(("quote", " ".join(quote_accum)))
                quote_accum = []
            chunks.append(("blank", ""))
            i += 1
            continue
        if re.match(r"^-{3,}$|^\*{3,}$", line.strip()):
            chunks.append(("rule", ""))
            i += 1
            continue
        if line.startswith("#### "):
            chunks.append(("h4", line[5:].strip()))
        elif line.startswith("### "):
            chunks.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            chunks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            chunks.append(("h1", line[2:].strip()))
        elif line.startswith("> "):
            quote_accum.append(line[2:].strip())
        elif "|" in line and i + 1 < len(lines) and re.match(r"^\|?[\s\-:|]+\|?$", lines[i + 1].strip()):
            if quote_accum:
                chunks.append(("quote", " ".join(quote_accum)))
                quote_accum = []
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            chunks.append(("table", (headers, rows)))
            continue
        elif re.match(r"^[\-\*] ", line):
            if quote_accum:
                chunks.append(("quote", " ".join(quote_accum)))
                quote_accum = []
            chunks.append(("bullet", line[2:].strip()))
        else:
            if quote_accum:
                quote_accum.append(line)
            else:
                chunks.append(("para", line.strip()))
        i += 1
    if quote_accum:
        chunks.append(("quote", " ".join(quote_accum)))
    return chunks


def render_chunk(pdf, ctype, cdata):
    if ctype == "h1":
        pdf.add_h1(cdata)
    elif ctype == "h2":
        pdf.add_h2(cdata)
    elif ctype == "h3":
        pdf.add_h3(cdata)
    elif ctype == "h4":
        pdf.add_h4(cdata)
    elif ctype == "para":
        m = re.match(r"^\*\*([^*]+):\*\*\s*(.*)$", cdata)
        if m:
            pdf.add_callout(m.group(1).strip(), strip_inline_md(m.group(2).strip()))
        else:
            pdf.add_para(strip_inline_md(cdata))
    elif ctype == "bullet":
        pdf.add_bullet(strip_inline_md(cdata))
    elif ctype == "quote":
        pdf.add_callout("Key Insight", strip_inline_md(cdata))
    elif ctype == "table":
        headers, rows = cdata
        headers = [strip_inline_md(h) for h in headers]
        rows = [[strip_inline_md(c) for c in r] for r in rows]
        pdf.add_table(headers, rows)
    elif ctype == "rule":
        pdf.add_rule()


def find_render_start(chunks):
    start_idx = 0
    for idx, c in enumerate(chunks):
        if c[0] == "h2" and "table of contents" in c[1].lower():
            start_idx = idx
            break
    render_start = start_idx + 1
    while render_start < len(chunks) and chunks[render_start][0] in ("bullet", "para", "blank"):
        if chunks[render_start][0] == "para" and "Executive Summary" in chunks[render_start][1]:
            break
        render_start += 1
    return render_start


def main():
    text = SOURCE_MD.read_text(encoding="utf-8")
    lines = text.split("\n")
    chunks = parse_markdown(lines)
    print(f"Parsed {len(chunks)} chunks")

    body_pdf = ReportPDF()
    render_start = find_render_start(chunks)
    print(f"Rendering body from chunk {render_start}...")
    for ctype, cdata in chunks[render_start:]:
        render_chunk(body_pdf, ctype, cdata)
    print(f"  Body: {body_pdf.page_no()} pages, {len(body_pdf.bookmarks)} bookmarks")

    body_buf = io.BytesIO()
    body_pdf.output(body_buf)
    body_buf.seek(0)

    final_pdf = ReportPDF()
    final_pdf.add_cover_page(TITLE, SUBTITLE, KICKER, CLASSIFICATION)

    final_pdf.add_page()
    final_pdf._has_page = True
    final_pdf.set_text_color(*COLOR_SECONDARY)
    final_pdf.set_font(final_pdf.font_family, "B", 22)
    final_pdf.cell(0, 12, "Contents", ln=1)
    final_pdf.ln(4)

    body_offset = 2
    for label, body_pg in body_pdf.bookmarks:
        if "table of contents" in label.lower():
            continue
        final_pdf.set_text_color(*COLOR_TEXT)
        final_pdf.set_font(final_pdf.font_family, "", 10)
        x_before = final_pdf.get_x()
        y_before = final_pdf.get_y()
        final_pdf.cell(0, 6, ascii_safe(label), ln=0)
        final_pdf.set_x(final_pdf.w - 25)
        final_pdf.cell(15, 6, str(body_offset + body_pg), border=0, align="R")
        label_w = final_pdf.get_string_width(ascii_safe(label))
        final_pdf.set_draw_color(*COLOR_BORDER)
        final_pdf.set_line_width(0.2)
        final_pdf.line(x_before + label_w + 2, y_before + 4, final_pdf.w - 28, y_before + 4)

    front_buf = io.BytesIO()
    final_pdf.output(front_buf)
    front_buf.seek(0)

    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    for p in PdfReader(front_buf).pages:
        writer.add_page(p)
    for p in PdfReader(body_buf).pages:
        writer.add_page(p)

    with open(OUT_PDF, "wb") as f:
        writer.write(f)

    size_kb = os_mod.path.getsize(OUT_PDF) / 1024
    print(f"PDF written. Pages: {len(writer.pages)}  Size: {size_kb:.0f} KB")
    print(f"  {OUT_PDF}")


if __name__ == "__main__":
    main()
