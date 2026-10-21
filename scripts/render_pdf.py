"""Render the editable Markdown report as a clean, paginated A4 PDF."""
import html
import os
import re
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, Image, PageBreak, Preformatted, KeepTogether)

from common import ROOT
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
from matplotlib.font_manager import FontProperties, findfont

FONT = Path("/System/Library/Fonts/Supplemental")
for name, filename in [("Body", "Arial.ttf"), ("Bold", "Arial Bold.ttf"),
                       ("Italic", "Arial Italic.ttf"), ("Mono", "Courier New.ttf")]:
    path = FONT / filename
    if not path.exists():
        path = findfont(FontProperties(family="DejaVu Sans Mono" if name == "Mono" else "DejaVu Sans",
                                       weight="bold" if name == "Bold" else "normal",
                                       style="italic" if name == "Italic" else "normal"))
    pdfmetrics.registerFont(TTFont(name, str(path)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Bold", italic="Italic", boldItalic="Bold")
pdfmetrics.registerFont(TTFont("Currency", findfont(FontProperties(family="DejaVu Sans"))))
NAVY, TEAL, GRAY = [colors.HexColor(c) for c in ("#252525", "#315f80", "#666666")]
W, H = A4
WIDTH = W - 88
STYLES = {
    "body": ParagraphStyle("body", fontName="Body", fontSize=10.5, leading=14.5,
                           textColor=NAVY, spaceAfter=8),
    "title": ParagraphStyle("title", fontName="Bold", fontSize=22, leading=26,
                            textColor=NAVY, spaceAfter=15),
    "h2": ParagraphStyle("h2", fontName="Bold", fontSize=15, leading=19,
                         textColor=NAVY, spaceAfter=12, keepWithNext=True),
    "h3": ParagraphStyle("h3", fontName="Bold", fontSize=11.5, leading=15,
                         textColor=TEAL, spaceBefore=5, spaceAfter=8, keepWithNext=True),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.4, leading=11,
                           textColor=NAVY),
    "th": ParagraphStyle("th", fontName="Bold", fontSize=8.2, leading=10.5,
                         textColor=colors.white),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8.0, leading=10.7,
                           textColor=NAVY, backColor=colors.HexColor("#f3f3f3"),
                           borderPadding=7, spaceBefore=4, spaceAfter=13),
    "caption": ParagraphStyle("caption", fontName="Italic", fontSize=8.5, leading=11.5,
                              textColor=GRAY, spaceAfter=10),
}


def fmt(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r'<font face="Mono">\1</font>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<link href="\2" color="#315f80"><u>\1</u></link>', s)
    s = s.replace("₽", '<font face="Currency">₽</font>')
    return s


def widths_for(headers):
    n = len(headers)
    ratios = {2: [.44, .56], 3: [.61, .18, .21],
              4: [.16, .28, .28, .28], 5: [.08, .24, .26, .21, .21],
              7: [.20, .09, .11, .11, .13, .13, .23]}.get(n, [1/n]*n)
    if n == 4 and headers[0] == "Сочетание":
        ratios = [.32, .29, .21, .18]
    elif n == 4 and "Режим" in headers:
        ratios = [.075, .22, .35, .355] if "1 / 2 / 3" in headers[2] else [.10, .36, .27, .27]
    elif n == 7 and headers[1] == "Размер":
        ratios = [.17, .055, .335, .09, .09, .15, .11]
    return [WIDTH * x for x in ratios]


def footer(canvas, doc):
    canvas.setFont("Body", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(44, H-33, "Анализ Frontend-вакансий · Вариант 8")
    canvas.setFont("Body", 8)
    canvas.drawString(44, 26, "RustFS · MapReduce · DuckDB")
    canvas.drawRightString(W-44, 26, str(doc.page))


def main():
    story = []
    lines = (ROOT / "report.md").read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line == "<!-- pagebreak -->":
            story.append(PageBreak())
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            style = {1: "title", 2: "h2", 3: "h3"}.get(level, "h3")
            story.append(Paragraph(fmt(line[level:].strip()), STYLES[style]))
            continue
        if line.startswith("```"):
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.extend(textwrap.wrap(lines[i], width=98, subsequent_indent="    ",
                                          replace_whitespace=False, drop_whitespace=False) or [""])
                i += 1
            i += 1
            story.append(Preformatted("\n".join(code), STYLES["code"]))
            continue
        if line.startswith("|"):
            rows = [line]
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            cells = [[v.strip() for v in r.strip("|").split("|")]
                     for r in rows if not re.match(r"^\|[ :|\-]+\|$", r)]
            data = [[Paragraph(fmt(v), STYLES["th" if j == 0 else "cell"])
                     for v in row] for j, row in enumerate(cells)]
            t = Table(data, colWidths=widths_for(cells[0]), repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), NAVY),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f4f4f4"), colors.white]),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LINEBELOW", (0,-1), (-1,-1), .5, colors.HexColor("#cccccc")),
                ("LEFTPADDING", (0,0), (-1,-1), 6),
                ("RIGHTPADDING", (0,0), (-1,-1), 6),
                ("TOPPADDING", (0,0), (-1,-1), 4.5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4.5),
            ]))
            story.extend([t, Spacer(1,10)])
            continue
        match = re.match(r"!\[([^]]*)\]\(([^)]+)\)", line)
        if match:
            img = Image(str(ROOT / match[2]))
            scale = min(WIDTH/img.imageWidth, 316/img.imageHeight)
            img.drawWidth, img.drawHeight = img.imageWidth*scale, img.imageHeight*scale
            story.append(KeepTogether([img, Spacer(1,5), Paragraph(fmt(match[1]), STYLES["caption"])]))
            continue
        if line.startswith("- "):
            line = "• " + line[2:]
        para = [line]
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "```", "![", "<!--", "- ")):
            para.append(lines[i].strip())
            i += 1
        story.append(Paragraph(fmt(" ".join(para)), STYLES["body"]))
    doc = SimpleDocTemplate(str(ROOT / "report.pdf"), pagesize=A4,
                            leftMargin=44, rightMargin=44, topMargin=52, bottomMargin=45,
                            title="Анализ Frontend-вакансий · Вариант 8", author="")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(ROOT / "report.pdf")


if __name__ == "__main__":
    main()
