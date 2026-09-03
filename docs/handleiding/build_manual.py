# -*- coding: utf-8 -*-
import sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, ListFlowable, ListItem,
    NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

import content_nl, content_en, content_sq
from flows import FLOWS

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DejaVu", FONT_DIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", FONT_DIR + "DejaVuSans-Bold.ttf"))
import os
from reportlab.pdfbase.pdfmetrics import registerFontFamily
_oblique = FONT_DIR + "DejaVuSans-Oblique.ttf"
_bold_oblique = FONT_DIR + "DejaVuSans-BoldOblique.ttf"
pdfmetrics.registerFont(TTFont("DejaVu-Oblique", _oblique if os.path.exists(_oblique) else FONT_DIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-BoldOblique", _bold_oblique if os.path.exists(_bold_oblique) else FONT_DIR + "DejaVuSans-Bold.ttf"))
registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu-Oblique", boldItalic="DejaVu-BoldOblique")

NAVY = colors.HexColor("#1E476B")
TEAL = colors.HexColor("#2BB5D8")
MINT = colors.HexColor("#3ED1B5")
GREY = colors.HexColor("#5f6b73")
LIGHT = colors.HexColor("#F1F6F8")
LINE = colors.HexColor("#D8E3E8")

import os as _os
LOGO = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dataforge_logo.png")
LANGS = {"nl": (content_nl, "nl"), "en": (content_en, "en"), "sq": (content_sq, "sq")}
LANG = sys.argv[1] if len(sys.argv) > 1 else "nl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "Tectora_Dakmeting_Handleiding_%s.pdf" % LANG.upper()

styles = {
    "body": ParagraphStyle("body", fontName="DejaVu", fontSize=9.5, leading=14, textColor=colors.HexColor("#1f2933"), spaceAfter=6),
    "bullet": ParagraphStyle("bullet", fontName="DejaVu", fontSize=9.5, leading=14, textColor=colors.HexColor("#1f2933")),
    "part": ParagraphStyle("PartTitle", fontName="DejaVu-Bold", fontSize=26, leading=32, textColor=NAVY, spaceAfter=6),
    "partsub": ParagraphStyle("partsub", fontName="DejaVu", fontSize=12, leading=16, textColor=GREY, spaceAfter=18),
    "h1": ParagraphStyle("H1", fontName="DejaVu-Bold", fontSize=17, leading=22, textColor=NAVY, spaceBefore=6, spaceAfter=10),
    "h2": ParagraphStyle("H2", fontName="DejaVu-Bold", fontSize=11.5, leading=15, textColor=TEAL.clone(), spaceBefore=8, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="DejaVu", fontSize=8.5, leading=11.5, textColor=colors.HexColor("#1f2933")),
    "cellh": ParagraphStyle("cellh", fontName="DejaVu-Bold", fontSize=8.5, leading=11.5, textColor=colors.white),
    "tip": ParagraphStyle("tip", fontName="DejaVu", fontSize=9, leading=13, textColor=colors.HexColor("#1f2933")),
    "cover_title": ParagraphStyle("cover_title", fontName="DejaVu-Bold", fontSize=34, leading=40, textColor=NAVY),
    "cover_sub": ParagraphStyle("cover_sub", fontName="DejaVu", fontSize=13, leading=18, textColor=GREY),
    "cover_small": ParagraphStyle("cover_small", fontName="DejaVu", fontSize=10, leading=14, textColor=GREY),
    "toc_title": ParagraphStyle("toc_title", fontName="DejaVu-Bold", fontSize=20, leading=26, textColor=NAVY, spaceAfter=12),
    "footer": ParagraphStyle("footer", fontName="DejaVu", fontSize=7.5, textColor=GREY),
}
styles["h2"].textColor = colors.HexColor("#1b8fae")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


class Manual(BaseDocTemplate):
    def __init__(self, filename, meta, **kw):
        self.meta = meta
        super().__init__(filename, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=26 * mm, bottomMargin=20 * mm,
                         title="Tectora Dakmeting — " + meta["part"], author="Data Forge",
                         subject=meta["subtitle"], **kw)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        cover = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="cover")
        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover], onPage=self.draw_cover),
            # Header/footer drawn after the page's flowables, so a page that
            # opens a new language part already carries that part's name.
            PageTemplate(id="Body", frames=[frame], onPageEnd=self.draw_page),
        ])
        self.part_label = ""

    def build(self, *args, **kwargs):
        self.part_label = ""
        return super().build(*args, **kwargs)

    def draw_cover(self, canvas, doc):
        canvas.saveState()
        # Teal band on the left
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0, 14 * mm, PAGE_H, stroke=0, fill=1)
        canvas.setFillColor(MINT)
        canvas.rect(14 * mm, 0, 3 * mm, PAGE_H, stroke=0, fill=1)
        canvas.drawImage(LOGO, PAGE_W - MARGIN - 80 * mm, PAGE_H - 22 * mm - 19 * mm, width=80 * mm, height=19 * mm, mask="auto")
        canvas.setFillColor(GREY)
        canvas.setFont("DejaVu", 8)
        canvas.drawRightString(PAGE_W - MARGIN, 14 * mm, "Data Forge · www.data-forge.be")
        canvas.restoreState()

    def draw_page(self, canvas, doc):
        canvas.saveState()
        canvas.drawImage(LOGO, MARGIN, PAGE_H - 17 * mm, width=42 * mm, height=10 * mm, mask="auto")
        canvas.setFillColor(GREY)
        canvas.setFont("DejaVu", 8)
        label = self.part_label or self.meta["toc"]
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 13 * mm, "Tectora Dakmeting — " + label)
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, PAGE_H - 19 * mm, PAGE_W - MARGIN, PAGE_H - 19 * mm)
        canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
        canvas.setFont("DejaVu", 7.5)
        canvas.drawString(MARGIN, 9 * mm, self.meta["for"] + " · www.data-forge.be")
        canvas.drawRightString(PAGE_W - MARGIN, 9 * mm, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            name = flowable.style.name
            text = flowable.getPlainText()
            if name == "PartTitle":
                self.part_label = text
                key = "part-%d" % self.seq.next("part")
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0, closed=False)
                self.notify("TOCEntry", (0, text, self.page, key))
            elif name == "H1":
                key = "h1-%d" % self.seq.next("h1")
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=1, closed=True)
                self.notify("TOCEntry", (1, text, self.page, key))


def para(text, style="body"):
    return Paragraph(text, styles[style])


def bullets(items, ordered=False):
    flow = [ListItem(Paragraph(item, styles["bullet"]), leftIndent=12, value=None) for item in items]
    return ListFlowable(
        flow, bulletType="1" if ordered else "bullet", start=None if ordered else "•",
        bulletFontName="DejaVu", bulletFontSize=9, leftIndent=14, bulletColor=TEAL if not ordered else NAVY,
        spaceAfter=6,
    )


def table(rows):
    data = [[Paragraph(c, styles["cellh"]) for c in rows[0]]]
    for row in rows[1:]:
        data.append([Paragraph(c, styles["cell"]) for c in row])
    ncols = len(rows[0])
    total = PAGE_W - 2 * MARGIN
    if ncols == 2:
        widths = [total * 0.36, total * 0.64]
    elif ncols == 3:
        widths = [total * 0.28, total * 0.42, total * 0.30]
    else:
        widths = [total / ncols] * ncols
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [t, Spacer(1, 8)]


def callout(label, text, color):
    body = Paragraph("<b>%s</b> — %s" % (label, text), styles["tip"])
    t = Table([[body]], colWidths=[PAGE_W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("LINEBEFORE", (0, 0), (0, -1), 3, color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [t, Spacer(1, 8)]


def render_blocks(blocks, meta):
    out = []
    for kind, payload in blocks:
        if kind == "p":
            out.append(para(payload))
        elif kind == "h2":
            out.append(para(payload, "h2"))
        elif kind == "ul":
            out.append(bullets(payload))
        elif kind == "ol":
            out.append(bullets(payload, ordered=True))
        elif kind == "table":
            out.extend(table(payload))
        elif kind == "tip":
            out.extend(callout(meta["tip"], payload, TEAL))
        elif kind == "note":
            out.extend(callout(meta["note"], payload, colors.HexColor("#d97706")))
    return out


def build_part(module, flow, story):
    meta = module.META
    chapters = list(module.CHAPTERS)
    chapters.insert(3, flow)
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())
    story.append(Paragraph(meta["part"], styles["part"]))
    story.append(Paragraph(meta["subtitle"], styles["partsub"]))
    story.append(Spacer(1, 6))
    for number, (title, blocks) in enumerate(chapters, start=1):
        heading = Paragraph("%d. %s" % (number, title), styles["h1"])
        body = render_blocks(blocks, meta)
        story.append(KeepTogether([heading] + body[:1]))
        story.extend(body[1:])
        story.append(Spacer(1, 10))


def main():
    module, flow_key = LANGS[LANG]
    meta = module.META
    doc = Manual(OUT, meta)
    story = []
    # Cover
    story.append(Spacer(1, 70 * mm))
    story.append(Paragraph(meta["title"], styles["cover_title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(meta["part"], styles["cover_sub"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(meta["subtitle"], styles["cover_sub"]))
    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph(meta["for"] + "<br/>" + meta["version"], styles["cover_small"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Odoo 19 · tectora_roof, tectora_roof_planning, tectora_products, tectora_boms", styles["cover_small"]))
    # Table of contents
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())
    story.append(Paragraph(meta["toc"], styles["toc_title"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("toc0", fontName="DejaVu-Bold", fontSize=11, leading=16, textColor=NAVY, spaceBefore=8),
        ParagraphStyle("toc1", fontName="DejaVu", fontSize=9.5, leading=13.5, leftIndent=14, textColor=colors.HexColor("#1f2933")),
    ]
    toc.dotsMinLevel = 1
    story.append(toc)
    build_part(module, FLOWS[flow_key], story)
    doc.multiBuild(story)
    print("written", OUT)


if __name__ == "__main__":
    main()
