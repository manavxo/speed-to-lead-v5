"""
Dealer Rady Market Research Report PDF Generator
Uses fpdf2 (pure Python, no GTK/Pango deps on Windows)
Builds a corporate-style PDF with cover page, headers, footers, tables, and styled content.
"""

from fpdf import FPDF
import re
from pathlib import Path

# ----- Config -----
SOURCE_MD = Path(__file__).parent / "DEALER_RADY_MARKET_RESEARCH_REPORT.md"
OUT_PDF = Path(__file__).parent / "DEALER_RADY_MARKET_RESEARCH_REPORT.pdf"

# Try to load a Unicode TTF font from Windows fonts dir (supports em-dash, smart quotes, etc.)
UNICODE_FONT = None
for candidate in [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]:
    if Path(candidate).exists():
        UNICODE_FONT = candidate
        break
USE_UNICODE = UNICODE_FONT is not None
print(f"Unicode font: {UNICODE_FONT or 'NONE (will use Helvetica with ASCII substitution)'}")

# Brand colors (corporate indigo + slate, MSFT/Anthropic inspired)
COLOR_PRIMARY = (79, 70, 229)      # Indigo 600
COLOR_SECONDARY = (30, 41, 59)      # Slate 800
COLOR_ACCENT = (16, 185, 129)       # Emerald 500
COLOR_MUTED = (100, 116, 139)       # Slate 500
COLOR_LIGHT_BG = (241, 245, 249)    # Slate 100
COLOR_BORDER = (226, 232, 240)      # Slate 200
COLOR_WHITE = (255, 255, 255)
COLOR_TEXT = (15, 23, 42)           # Slate 900

# ----- Read the markdown -----
text = SOURCE_MD.read_text(encoding="utf-8")
lines = text.split("\n")


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        self.toc_started = False
        self.bookmarks = []  # (label, page_no) - filled during render
        if USE_UNICODE:
            # Register unicode font + italic + bold variants
            try:
                self.add_font("Uni", "", UNICODE_FONT, uni=True)
                # Try italic variant
                italic_candidates = [
                    UNICODE_FONT.replace("arial.ttf", "ariali.ttf"),
                    UNICODE_FONT.replace("calibri.ttf", "calibrii.ttf"),
                    UNICODE_FONT.replace("segoeui.ttf", "segoeuii.ttf"),
                ]
                italic_font = next((p for p in italic_candidates if Path(p).exists()), None)
                if italic_font:
                    self.add_font("Uni", "I", italic_font, uni=True)
                else:
                    self.add_font("Uni", "I", UNICODE_FONT, uni=True)
                bold_candidates = [
                    UNICODE_FONT.replace("arial.ttf", "arialbd.ttf"),
                    UNICODE_FONT.replace("calibri.ttf", "calibrib.ttf"),
                    UNICODE_FONT.replace("segoeui.ttf", "segoeuib.ttf"),
                ]
                bold_font = next((p for p in bold_candidates if Path(p).exists()), None)
                if bold_font:
                    self.add_font("Uni", "B", bold_font, uni=True)
                else:
                    self.add_font("Uni", "B", UNICODE_FONT, uni=True)
                bold_italic_candidates = [
                    UNICODE_FONT.replace("arial.ttf", "arialbi.ttf"),
                    UNICODE_FONT.replace("calibri.ttf", "calibriz.ttf"),
                ]
                bi_font = next((p for p in bold_italic_candidates if Path(p).exists()), None)
                if bi_font:
                    self.add_font("Uni", "BI", bi_font, uni=True)
                else:
                    self.add_font("Uni", "BI", UNICODE_FONT, uni=True)
                self.font_family = "Uni"
            except Exception as e:
                print(f"  Font load failed: {e}, falling back to Helvetica")
                self.font_family = "Helvetica"
        else:
            self.font_family = "Helvetica"

    def _font(self, style=""):
        """Return font family + style tuple for set_font."""
        return self.font_family, style

    def header(self):
        if self.page_no() == 1:
            return  # no header on cover
        # Slim header bar
        self.set_y(8)
        self.set_font(self.font_family, "B", 8)
        self.set_text_color(*COLOR_MUTED)
        self.cell(0, 5, "DEALER RADY  |  MARKET RESEARCH REPORT  |  JUNE 2026", border=0, align="L")
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
        # Full-bleed cover with a colored top band
        self.add_page()
        # Top band
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(0, 0, self.w, 70, style="F")

        # Logo wordmark (top-left of band)
        self.set_xy(15, 22)
        self.set_text_color(*COLOR_WHITE)
        self.set_font(self.font_family, "B", 22)
        self.cell(0, 10, "DEALER RADY", ln=0)

        # Kicker (white on indigo)
        self.set_xy(15, 38)
        self.set_text_color(*COLOR_WHITE)
        self.set_font(self.font_family, "", 10)
        self.cell(0, 6, classification, ln=0)

        # Title block (centered, lower half of page)
        self.set_xy(15, 110)
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 32)
        self.multi_cell(self.w - 30, 14, title)

        # Subtitle
        self.set_xy(15, self.get_y() + 8)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "", 16)
        self.multi_cell(self.w - 30, 8, subtitle)

        # Kicker / quote
        self.set_xy(15, self.get_y() + 18)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "I", 11)
        self.multi_cell(self.w - 30, 6, kicker)

        # Bottom info block
        self.set_xy(15, self.h - 60)
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.3)
        self.line(15, self.h - 60, self.w - 15, self.h - 60)

        self.set_xy(15, self.h - 52)
        self.set_text_color(*COLOR_MUTED)
        self.set_font(self.font_family, "", 9)
        self.cell(0, 5, "Prepared for:  Dealer Rady leadership, sales, and product", ln=1)
        self.set_x(15)
        self.cell(0, 5, "Prepared by:   Market Research (autonomous)", ln=1)
        self.set_x(15)
        self.cell(0, 5, "Date:          June 2026  |  Version 1.0", ln=1)
        self.set_x(15)
        self.cell(0, 5, "Classification:  Internal — Sales Enablement & Strategy", ln=1)

    def add_toc_page(self, toc_items):
        self.add_page()
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 22)
        self.cell(0, 12, "Contents", ln=1)
        self.ln(4)

        for label, page in toc_items:
            self.set_text_color(*COLOR_TEXT)
            self.set_font(self.font_family, "", 11)
            # Dot leaders
            self.cell(0, 7, label, border=0, ln=0)
            self.set_text_color(*COLOR_MUTED)
            self.set_font(self.font_family, "", 11)
            x_before = self.get_x()
            w_text = self.get_string_width(label) + 2
            dots_x = self.w - 25
            self.set_x(dots_x)
            self.cell(8, 7, str(page), border=0, align="R", ln=1)
            # Dotted line
            self.set_draw_color(*COLOR_BORDER)
            self.set_line_width(0.2)
            self.line(w_text + 12, self.get_y() - 5, dots_x - 2, self.get_y() - 5)

    def add_h1(self, text):
        self.ln(8)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 20)
        self.multi_cell(0, 10, text)
        # Underline bar
        y = self.get_y() + 1
        self.set_draw_color(*COLOR_PRIMARY)
        self.set_line_width(0.6)
        self.line(10, y, 50, y)
        # Add bookmark
        self.bookmarks.append((strip_inline_md(text), self.page_no()))
        self.ln(6)

    def add_h2(self, text):
        self.ln(4)
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 15)
        self.multi_cell(0, 8, text)
        self.bookmarks.append(("    " + strip_inline_md(text), self.page_no()))
        self.ln(2)

    def add_h3(self, text):
        self.ln(3)
        self.set_text_color(*COLOR_SECONDARY)
        self.set_font(self.font_family, "B", 12)
        self.multi_cell(0, 7, text)
        self.ln(1)

    def add_h4(self, text):
        self.ln(2)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "B", 11)
        self.multi_cell(0, 6, text)
        self.ln(1)

    def add_para(self, text):
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def add_quote(self, text, attribution=""):
        # Block quote: left indigo bar, light background
        self.ln(2)
        x = self.get_x()
        y = self.get_y()
        # Calculate height
        h = max(15, 5 + (len(text) // 95 + 1) * 5.5)
        # Background box
        self.set_fill_color(*COLOR_LIGHT_BG)
        self.rect(x, y, self.w - 20, h, style="F")
        # Left bar
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(x, y, 3, h, style="F")
        # Quote text
        self.set_xy(x + 8, y + 3)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "I", 10)
        self.multi_cell(self.w - 32, 5.5, '"' + text + '"')
        if attribution:
            self.set_x(x + 8)
            self.set_text_color(*COLOR_MUTED)
            self.set_font(self.font_family, "", 9)
            self.multi_cell(self.w - 32, 5, "— " + attribution)
        self.set_y(y + h + 3)

    def add_bullet(self, text, level=0):
        indent = 6 + level * 4
        self.set_x(indent)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 10)
        bullet = "  " * level + ("•" if level == 0 else "–")
        self.cell(5, 5.5, bullet, ln=0)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(self.w - indent - 18, 5.5, text)
        self.ln(0.5)

    def add_numbered(self, n, text):
        self.set_x(10)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 10)
        self.cell(8, 5.5, f"{n}.", ln=0)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(self.w - 20, 5.5, text)
        self.ln(1)

    def add_table(self, headers, rows, col_widths=None):
        if col_widths is None:
            total_w = self.w - 20
            n_cols = len(headers)
            # Equal-width columns
            col_widths = [total_w / n_cols] * n_cols
        # Ensure all col widths are valid (min 20mm) and sum to w-20
        total_w = self.w - 20
        col_widths = [max(20, w) for w in col_widths]
        # Scale to fit page width exactly
        s = sum(col_widths)
        if s != total_w:
            col_widths = [w * (total_w / s) for w in col_widths]
        # Header row
        self.set_fill_color(*COLOR_SECONDARY)
        self.set_text_color(*COLOR_WHITE)
        self.set_font(self.font_family, "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, str(h)[:200], border=0, fill=True, align="L")
        self.ln(8)
        # Body rows
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 9)
        for ri, row in enumerate(rows):
            # Calculate row height based on the longest cell
            row_h = 6
            for ci, cell in enumerate(row):
                # rough char-per-mm estimate
                chars_per_line = max(1, int(col_widths[ci] / 1.6))
                lines_needed = max(1, (len(str(cell)) + chars_per_line - 1) // chars_per_line)
                row_h = max(row_h, lines_needed * 4.5 + 1)
            # Page break check
            if self.get_y() + row_h > self.h - 18:
                self.add_page()
            # Alternate row bg
            x0 = self.get_x()
            y0 = self.get_y()
            if ri % 2 == 0:
                self.set_fill_color(*COLOR_LIGHT_BG)
                self.rect(x0, y0, sum(col_widths), row_h, style="F")
            for ci, cell in enumerate(row):
                if ci >= len(col_widths):
                    break
                self.set_xy(x0 + sum(col_widths[:ci]), y0)
                self.set_text_color(*COLOR_TEXT)
                self.set_font(self.font_family, "", 9)
                self.multi_cell(col_widths[ci], 4.5, str(cell)[:1000], border=0)
            self.set_xy(x0, y0 + row_h)
        self.ln(3)

    def add_callout(self, label, text):
        self.ln(2)
        x = self.get_x()
        y = self.get_y()
        h = max(20, 5 + (len(text) // 90 + 1) * 5.5)
        self.set_fill_color(238, 242, 255)  # indigo-50
        self.rect(x, y, self.w - 20, h, style="F")
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(x, y, 3, h, style="F")
        self.set_xy(x + 8, y + 3)
        self.set_text_color(*COLOR_PRIMARY)
        self.set_font(self.font_family, "B", 10)
        self.cell(0, 5, label, ln=1)
        self.set_x(x + 8)
        self.set_text_color(*COLOR_TEXT)
        self.set_font(self.font_family, "", 10)
        self.multi_cell(self.w - 32, 5.5, text)
        self.set_y(y + h + 3)

    def add_rule(self):
        self.ln(2)
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(10, y, self.w - 10, y)
        self.ln(3)


# ----- Parse the markdown into structured chunks -----

def parse_markdown(lines):
    """Parse the markdown into a list of (type, text) tuples.
    type ∈ {h1, h2, h3, h4, para, bullet, numbered, quote, table, callout, rule, blank, code}
    Tables: detect by pipe-row; first row = header, second row = separator, rest = body.
    """
    chunks = []
    i = 0
    in_code = False
    code_buf = []

    while i < len(lines):
        line = lines[i].rstrip()

        # Code block (skip — not used in this report but defensive)
        if line.strip().startswith("```"):
            if in_code:
                chunks.append(("code", "\n".join(code_buf)))
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if not line.strip():
            chunks.append(("blank", ""))
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$|^\*{3,}$", line.strip()):
            chunks.append(("rule", ""))
            i += 1
            continue

        # Headings
        if line.startswith("#### "):
            chunks.append(("h4", line[5:].strip()))
        elif line.startswith("### "):
            chunks.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            chunks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            chunks.append(("h1", line[2:].strip()))
        # Tables
        elif "|" in line and i + 1 < len(lines) and re.match(r"^\|?[\s\-:|]+\|?$", lines[i + 1].strip()):
            # Header row
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(row_cells)
                i += 1
            chunks.append(("table", (header_cells, rows)))
            continue
        # Block quote
        elif line.startswith("> "):
            chunks.append(("quote", line[2:].strip()))
        # Bullets
        elif re.match(r"^[\-\*] ", line):
            chunks.append(("bullet", line[2:].strip(), 0))
        # Numbered list
        elif re.match(r"^\d+\. ", line):
            chunks.append(("numbered", line.strip()))
        # Regular paragraph
        else:
            chunks.append(("para", line.strip()))

        i += 1

    return chunks


# ----- Strip inline markdown (bold, italic, code) for fpdf2 plain-text rendering -----

def strip_inline_md(text):
    # Remove bold/italic markers; keep their content
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", text)
    return text


# ----- ASCII normalization (only used if no Unicode font is available) -----

def ascii_safe(text):
    if not text:
        return text
    if USE_UNICODE:
        return text
    repl = {
        "—": "--",  # em-dash
        "–": "-",   # en-dash
        """: '"',  # right double quote
        """: '"',  # left double quote
        "'": "'",   # right single quote
        "'": "'",   # left single quote
        "…": "...", # ellipsis
        "×": "x",   # multiplication
        "•": "*",   # bullet
        "·": "-",   # middle dot
        "→": "->",  # right arrow
        "←": "<-",
        "↳": ">",
        "✓": "[x]",
        "✔": "[x]",
        "⚡": "*",
        "•": "*",
        "©": "(c)",
        "®": "(R)",
        "™": "(TM)",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    # Strip remaining non-ASCII as a safety net
    text = text.encode("latin-1", errors="ignore").decode("latin-1")
    return text


# ----- Numbered extraction -----

def split_numbered(text):
    m = re.match(r"^(\d+)\.\s+(.*)$", text)
    if m:
        return int(m.group(1)), m.group(2)
    return 0, text


# ----- Build the PDF -----
# Two-pass approach: render body first to collect real page numbers, then build
# cover + TOC with those numbers, then append the body.

print("Parsing markdown...")
chunks = parse_markdown(lines)
print(f"  {len(chunks)} chunks parsed")

# --- Pass 1: render body to a temporary PDF, collecting page numbers per section ---
body_pdf = ReportPDF()
# Don't add a placeholder page — the body starts naturally. fpdf2 will auto-create
# a page on first drawing, but we ensure one is open for safety.
body_pdf.set_auto_page_break(auto=True, margin=20)
# Track whether a page is open; ensure it is before drawing
_body_has_page = [False]

def _ensure_page():
    if not _body_has_page[0]:
        body_pdf.add_page()
        _body_has_page[0] = True

# Skip front matter (the title page text from the MD) by detecting the first H1
start_idx = 0
for idx, c in enumerate(chunks):
    if c[0] == "h2" and "table of contents" in c[1].lower():
        start_idx = idx
        break

render_start = start_idx + 1
# Skip the dotted list that follows (TOC body in the source MD)
while render_start < len(chunks) and chunks[render_start][0] in ("bullet", "para", "blank"):
    if chunks[render_start][0] == "para" and "Executive Summary" in chunks[render_start][1]:
        break
    render_start += 1

print(f"Pass 1: Rendering body from chunk {render_start}...")
i = render_start
quote_buffer = []
quote_attr_buffer = []

def flush_quote_b():
    global quote_buffer, quote_attr_buffer
    if quote_buffer:
        joined = " ".join(quote_buffer)
        attr = " — ".join(quote_attr_buffer) if quote_attr_buffer else ""
        body_pdf.add_quote(joined, attr)
        quote_buffer = []
        quote_attr_buffer = []

while i < len(chunks):
    ctype = chunks[i]
    cdata = ctype[1] if len(ctype) > 1 else ""

    if ctype[0] == "h1":
        flush_quote_b()
        body_pdf.add_h1(strip_inline_md(cdata))
    elif ctype[0] == "h2":
        flush_quote_b()
        text_lower = cdata.lower()
        if "table of contents" in text_lower:
            i += 1
            continue
        body_pdf.add_h2(strip_inline_md(cdata))
    elif ctype[0] == "h3":
        flush_quote_b()
        body_pdf.add_h3(strip_inline_md(cdata))
    elif ctype[0] == "h4":
        flush_quote_b()
        body_pdf.add_h4(strip_inline_md(cdata))
    elif ctype[0] == "para":
        flush_quote_b()
        m = re.match(r"^\*\*([^*]+):\*\*\s*(.*)$", cdata)
        if m:
            body_pdf.add_callout(m.group(1).strip(), strip_inline_md(m.group(2).strip()))
        else:
            body_pdf.add_para(strip_inline_md(cdata))
    elif ctype[0] == "bullet":
        flush_quote_b()
        text = strip_inline_md(cdata)
        m = re.match(r"^\*\*([^*]+):\*\*\s*(.*)$", text)
        if m:
            body_pdf.set_x(12)
            body_pdf.set_text_color(*COLOR_PRIMARY)
            body_pdf.set_font(body_pdf.font_family, "B", 10)
            body_pdf.cell(5, 5.5, "•", ln=0)
            body_pdf.set_text_color(*COLOR_SECONDARY)
            body_pdf.set_font(body_pdf.font_family, "B", 10)
            body_pdf.cell(35, 5.5, m.group(1).strip() + ":", ln=0)
            body_pdf.set_text_color(*COLOR_TEXT)
            body_pdf.set_font(body_pdf.font_family, "", 10)
            body_pdf.multi_cell(body_pdf.w - 70, 5.5, m.group(2).strip())
            body_pdf.ln(0.5)
        else:
            body_pdf.add_bullet(text)
    elif ctype[0] == "numbered":
        flush_quote_b()
        n, t = split_numbered(cdata)
        body_pdf.add_numbered(n, strip_inline_md(t))
    elif ctype[0] == "quote":
        text = strip_inline_md(cdata)
        if text.startswith("— "):
            quote_attr_buffer.append(text[2:].strip())
        else:
            quote_buffer.append(text)
    elif ctype[0] == "table":
        flush_quote_b()
        headers, rows = cdata
        headers = [strip_inline_md(h) for h in headers]
        rows = [[strip_inline_md(c) for c in row] for row in rows]
        if len(headers) > 5:
            for row in rows:
                body_pdf.set_text_color(*COLOR_PRIMARY)
                body_pdf.set_font(body_pdf.font_family, "B", 10)
                body_pdf.cell(0, 6, headers[0] + ": " + str(row[0]), ln=1)
                body_pdf.set_text_color(*COLOR_TEXT)
                body_pdf.set_font(body_pdf.font_family, "", 9)
                for hi in range(1, len(headers)):
                    body_pdf.cell(0, 5, f"   {headers[hi]}: {row[hi]}", ln=1)
                body_pdf.ln(1)
        else:
            total_w = body_pdf.w - 20
            n_cols = len(headers)
            col_widths = [total_w / n_cols] * n_cols
            body_pdf.add_table(headers, rows, col_widths)
    elif ctype[0] == "rule":
        flush_quote_b()
        body_pdf.add_rule()
    elif ctype[0] == "blank":
        flush_quote_b()
    i += 1
flush_quote_b()

# Adjust bookmarks: the body started on page 2 (page 1 was a cover placeholder)
# But in the FINAL PDF, cover=1, TOC=2, body starts at 3. So bookmark pages
# need to be offset by +2 (cover=1, toc=2, then body offset 2).
# However, we don't yet know the TOC page count yet. Estimate: TOC is 1 page.
# We'll set offset=2 and accept a small possibility of off-by-one if TOC wraps.
body_page_offset = 2  # cover + TOC

print(f"  Body rendered. {len(body_pdf.bookmarks)} bookmarks collected. Body pages: {body_pdf.page_no() - 1}")

# Save body to bytes
import io
body_buf = io.BytesIO()
body_pdf.output(body_buf)
body_buf.seek(0)

# --- Pass 2: build the final PDF with cover + TOC + body ---
final_pdf = ReportPDF()
title = "The Speed-to-Lead Imperative for Small Used-Car Dealers"
subtitle = "Market Research, Ground Truth, and Sales Enablement"
kicker = (
    "The first hour is the only hour. After 20 hours, every additional attempt hurts. "
    "47% of internet leads arrive after business hours. 25-30% of inbound calls go unanswered. "
    "67% of BDC staff leave within 18 months. The small BC used-car dealer has no realistic way "
    "to staff this problem — until now."
)
classification = "MARKET RESEARCH REPORT  |  v1.0  |  JUNE 2026"
final_pdf.add_cover_page(title, subtitle, kicker, classification)

# Add the TOC page using the real bookmarks (offset by 2 for cover+TOC)
final_pdf.add_page()
final_pdf.set_text_color(*COLOR_SECONDARY)
final_pdf.set_font(final_pdf.font_family, "B", 22)
final_pdf.cell(0, 12, "Contents", ln=1)
final_pdf.ln(4)
# Build link map: each bookmark -> final page (body_page_offset + body_page)
def real_page(body_page):
    return body_page_offset + body_page

# Pre-compute the link targets (page numbers only) and render the TOC.
# fpdf2 needs the link target page to exist before linking — so we render TOC
# with plain text (no clickable links) to avoid that constraint.
toc_link_targets = []
for label, body_pg in body_pdf.bookmarks:
    if "Table of Contents" in label:
        continue
    toc_link_targets.append((label, real_page(body_pg)))

# Render TOC entries
for label, page in toc_link_targets:
    final_pdf.set_text_color(*COLOR_TEXT)
    final_pdf.set_font(final_pdf.font_family, "", 10)
    x_before = final_pdf.get_x()
    y_before = final_pdf.get_y()
    final_pdf.cell(0, 6, label, border=0, ln=0)
    final_pdf.set_x(final_pdf.w - 25)
    final_pdf.cell(15, 6, str(page), border=0, align="R")
    label_w = final_pdf.get_string_width(label)
    final_pdf.set_draw_color(*COLOR_BORDER)
    final_pdf.set_line_width(0.2)
    final_pdf.line(x_before + label_w + 2, y_before + 4, final_pdf.w - 28, y_before + 4)

# Now merge the body pages into final_pdf
from pypdf import PdfReader, PdfWriter
final_buf = io.BytesIO()
final_pdf.output(final_buf)
final_buf.seek(0)

reader_body = PdfReader(body_buf)
reader_final = PdfReader(final_buf)
writer = PdfWriter()
# Add final pages (cover + TOC) first
for p in reader_final.pages:
    writer.add_page(p)
# Add body pages (include all — body starts on page 1)
for p in reader_body.pages:
    writer.add_page(p)

with open(OUT_PDF, "wb") as f:
    writer.write(f)

import os
size_kb = os.path.getsize(OUT_PDF) / 1024
print(f"OK  PDF written.  Pages: {len(writer.pages)}  Size: {size_kb:.0f} KB")
print(f"    {OUT_PDF}")
