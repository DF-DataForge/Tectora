# -*- coding: utf-8 -*-
import io
import re
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools.pdf import PdfFileReader, PdfFileWriter

from odoo.addons.tectora_quote_builder.models.ir_actions_report import MM

WIDTH, HEIGHT = A4


def make_pdf(pages):
    """A4 pages; each page is a list of (text, y in mm from the top)."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for texts in pages:
        for text, top_mm in texts:
            pdf.drawString(50, HEIGHT - top_mm * MM, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def text_positions(page):
    """{text: y in points from the bottom} of the text drawn on the page."""
    positions = {}

    def visitor(text, cm, tm, font_dict, font_size):
        text = text.strip()
        if text:
            # tm is in text space; cm brings it to the page
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            positions[text] = y

    page.extract_text(visitor_text=visitor)
    return positions


@tagged("post_install", "-at_install")
class TestQuoteDocuments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["ir.actions.report"]
        cls.partner = cls.env["res.partner"].create({
            "name": "Michiels Philippe",
            "tectora_title_id": cls.env.ref("tectora_roof.partner_title_mister").id,
        })
        cls.source = make_pdf([
            [("OUDE BAND", 10), ("VOORSTEL OP MAAT", 216), ("OUDE VOET", 290)],
            [("OUDE BAND", 10), ("Welkom bij Tectora", 40), ("OUDE VOET", 290)],
        ])
        cls.frame = make_pdf([[("LAYOUT KOP", 15), ("LAYOUT VOET", 285)]])
        cls.Document = cls.env["quotation.document"]
        cls.Document.search([]).action_archive()
        cls.header = cls.Document.create({
            "name": "voorpagina.pdf",
            "raw": cls.source,
            "document_type": "header",
            "tectora_customer_name": True,
        })
        cls.footer = cls.Document.create({
            "name": "voorwaarden.pdf",
            "raw": make_pdf([[("Onze verkoopsvoorwaarden", 60)]]),
            "document_type": "footer",
            "tectora_crop_top": 0,
            "tectora_crop_bottom": 0,
        })

    def _order(self, **values):
        return self.env["sale.order"].create({"partner_id": self.partner.id, **values})

    def test_put_in_frame(self):
        result = self.Report._tectora_put_in_frame(
            self.source, self.frame, crop_top=28 * MM, crop_bottom=24 * MM,
        )
        pages = PdfFileReader(io.BytesIO(result)).pages
        self.assertEqual(len(pages), 2, "one framed page per page of the document")
        self.assertAlmostEqual(float(pages[0].mediabox.height), HEIGHT, places=1)
        first = text_positions(pages[0])
        self.assertIn("LAYOUT KOP", first)
        self.assertIn("LAYOUT VOET", first)
        # Full size: the content stays where it is on the original page.
        self.assertAlmostEqual(first["VOORSTEL OP MAAT"], HEIGHT - 216 * MM, delta=1)
        second = text_positions(pages[1])
        self.assertAlmostEqual(second["Welkom bij Tectora"], HEIGHT - 40 * MM, delta=1)
        content = pages[0].get_contents().get_data()
        # Only the page between its own band (28 mm) and footer (24 mm) is
        # drawn: the clipping rectangle starts 24 mm from the bottom and is
        # 297 - 28 - 24 = 245 mm high.
        self.assertRegex(content, rb"0(\.0+)? 68\.03\d* 595\.27\d* 694\.4\d* re\s+W\s+n")
        # The layout's header and footer are drawn over the page.
        self.assertGreater(content.index(b"LAYOUT KOP"), content.index(b"VOORSTEL OP MAAT"))

    def test_crop_along_the_header_contour(self):
        """With a sloped header (the roof edge), the page's own band is cut
        along the header's lower edge, at least as deep as the straight cut."""
        contour = [(0.0, 37.5), (0.777, 29.5), (1.0, 33.5)]
        result = self.Report._tectora_put_in_frame(
            self.source, self.frame, crop_top=28 * MM, crop_bottom=24 * MM,
            header_contour=contour,
        )
        content = PdfFileReader(io.BytesIO(result)).pages[0].get_contents().get_data()
        self.assertNotRegex(content, rb"694\.4\d* re", "no straight cut at 28 mm")
        clip = re.search(rb"q\s+((?:[\d.]+ [\d.]+ [ml]\s+)+)h\s+W\s+n", content)
        self.assertTrue(clip, "the page is clipped to a polygon")
        corners = [tuple(map(float, point.split()[:2]))
                   for point in re.findall(rb"[\d.]+ [\d.]+ [ml]", clip.group(1))]
        # bottom left and right at the footer cut, then the edge from right
        # to left: 34, 30 and 38 mm from the top (0.5 mm under the edge)
        tops = [round((HEIGHT - y) / MM, 1) for _x, y in corners[2:]]
        self.assertEqual(tops, [34.0, 30.0, 38.0])
        # a straight cut deeper than the edge wins where it is lower
        outline = self.Report._tectora_header_outline(
            contour, 0.0, 595.276, HEIGHT - 32 * MM, to_page_y=lambda mm: HEIGHT - mm * MM,
        )
        ys = [round((HEIGHT - y) / MM, 1) for _x, y in outline]
        self.assertEqual(ys[0], 38.0)
        self.assertEqual(min(ys), 32.0)
        self.assertEqual(ys[-1], 34.0)

    def test_footer_crop_only_on_given_pages(self):
        result = self.Report._tectora_put_in_frame(
            self.source, self.frame, crop_top=28 * MM, crop_bottom=24 * MM, crop_bottom_pages={1},
        )
        first, second = PdfFileReader(io.BytesIO(result)).pages
        # page 1: clipped from 24 mm; page 2 (no footer band of its own): from 0
        self.assertRegex(first.get_contents().get_data(), rb"0(\.0+)? 68\.03\d* 595\.27\d* 694\.4\d* re")
        self.assertRegex(second.get_contents().get_data(), rb"0(\.0+)? 0(\.0+)? 595\.27\d* 762\.5\d* re")

    def test_fit_pages_and_crop_top_pages(self):
        """Page 2 runs up to the top edge: no own band cut away, and scaled
        down between the layout's header and footer."""
        source = make_pdf([
            [("OUDE BAND", 10), ("VOORSTEL OP MAAT", 216)],
            [("Slotbepalingen", 8), ("Handtekening", 280)],
        ])
        result = self.Report._tectora_put_in_frame(
            source, self.frame, crop_top=28 * MM, crop_bottom=0,
            crop_top_pages={1}, fit_pages={2}, body_top=52 * MM, body_bottom=32 * MM,
        )
        first, second = (text_positions(page) for page in PdfFileReader(io.BytesIO(result)).pages)
        # page 1: full size
        self.assertAlmostEqual(first["VOORSTEL OP MAAT"], HEIGHT - 216 * MM, delta=1)
        # page 2: everything between the header (52 mm) and the footer (32 mm)
        body_top, body_bottom = HEIGHT - 52 * MM, 32 * MM
        self.assertTrue(body_bottom <= second["Slotbepalingen"] <= body_top)
        self.assertTrue(body_bottom <= second["Handtekening"] <= body_top)
        content = PdfFileReader(io.BytesIO(result)).pages[1].get_contents().get_data()
        # no own band on page 2: the whole page height is drawn
        self.assertRegex(content, rb"0(\.0+)? 0(\.0+)? 595\.27\d* 841\.8\d* re")

    def test_page_field_specs(self):
        self.header.write({"tectora_crop_top_pages": "1,2", "tectora_fit_pages": "3-4"})
        self.assertEqual(self.header._tectora_page_numbers("tectora_crop_top_pages"), {1, 2})
        self.assertEqual(self.header._tectora_page_numbers("tectora_fit_pages"), {3, 4})
        with self.assertRaises(ValidationError):
            self.header.tectora_fit_pages = "drie"

    def test_crop_bottom_pages_spec(self):
        self.header.tectora_crop_bottom_pages = "1, 4-5"
        self.assertEqual(self.header._tectora_crop_bottom_page_numbers(), {1, 4, 5})
        self.header.tectora_crop_bottom_pages = False
        self.assertIsNone(self.header._tectora_crop_bottom_page_numbers())
        with self.assertRaises(ValidationError):
            self.header.tectora_crop_bottom_pages = "1,a"

    def test_customer_name_on_first_page(self):
        result = self.Report._tectora_stamp_customer_name(self.source, self._order(), 232)
        pages = PdfFileReader(io.BytesIO(result)).pages
        first, second = text_positions(pages[0]), text_positions(pages[1])
        self.assertIn("Dhr. Michiels Philippe", first)
        self.assertAlmostEqual(first["Dhr. Michiels Philippe"], HEIGHT - 232 * MM, delta=1)
        self.assertNotIn("Dhr. Michiels Philippe", second)

    def test_site_address_under_name(self):
        site = self.env["res.partner"].create({
            "name": "Werf", "parent_id": self.partner.id, "type": "delivery",
            "street": "Lostraat 15", "zip": "1703", "city": "Schepdaal",
        })
        order = self._order(partner_shipping_id=site.id)
        result = self.Report._tectora_stamp_customer_name(self.source, order, 232)
        first = text_positions(PdfFileReader(io.BytesIO(result)).pages[0])
        self.assertIn("Werfadres: Lostraat 15, 1703 Schepdaal", first)
        self.assertAlmostEqual(
            first["Werfadres: Lostraat 15, 1703 Schepdaal"], HEIGHT - 240 * MM, delta=1
        )
        # without an address, only the name
        no_address = self.env["res.partner"].create({"name": "Zonder Adres"})
        bare = self.Report._tectora_stamp_customer_name(
            self.source, self._order(partner_id=no_address.id), 232
        )
        self.assertFalse([t for t in text_positions(PdfFileReader(io.BytesIO(bare)).pages[0])
                          if t.startswith("Werfadres")])

    def test_customer_name_without_title(self):
        self.partner.tectora_title_id = False
        result = self.Report._tectora_stamp_customer_name(self.source, self._order(), 232)
        first = text_positions(PdfFileReader(io.BytesIO(result)).pages[0])
        self.assertIn("Michiels Philippe", first)
        self.assertNotIn("Dhr. Michiels Philippe", first)

    def test_documents_printed_in_layout(self):
        order = self._order(quotation_document_ids=[(6, 0, (self.header | self.footer).ids)])
        writer = PdfFileWriter()
        with patch.object(type(self.Report), "_tectora_layout_frame", lambda self, order: {
            "pdf": TestQuoteDocuments.frame, "margin_top": 52 * MM, "margin_bottom": 32 * MM,
        }):
            report = self.Report.with_context(tectora_layout_frames={})
            for document in (self.header, self.footer):
                report._update_mapping_and_add_pages_to_writer(
                    writer, document, {}, f"quotation_document_id_{document.id}__", order
                )
        self.assertEqual(len(writer.pages), 3)
        cover, intro, terms = (text_positions(page) for page in writer.pages)
        self.assertIn("LAYOUT KOP", cover)
        self.assertIn("Dhr. Michiels Philippe", cover)
        self.assertNotIn("Dhr. Michiels Philippe", intro)
        self.assertIn("LAYOUT VOET", terms)
        self.assertNotIn("Dhr. Michiels Philippe", terms, "only on the first header")

    def test_document_outside_layout_unchanged(self):
        self.footer.tectora_in_layout = False
        order = self._order(quotation_document_ids=[(6, 0, self.footer.ids)])
        prepared = self.Report._tectora_prepare_quotation_document(self.footer, self.footer.raw, order)
        self.assertEqual(prepared, self.footer.raw)

    def test_no_frame_prints_document_as_is(self):
        order = self._order(quotation_document_ids=[(6, 0, self.footer.ids)])
        with patch.object(type(self.Report), "_tectora_layout_frame", lambda self, order: False):
            prepared = self.Report._tectora_prepare_quotation_document(self.footer, self.footer.raw, order)
        self.assertEqual(prepared, self.footer.raw)

    def test_template_documents_on_quotation_made_in_code(self):
        default_header = self.Document.create({
            "name": "standaard.pdf", "raw": self.source,
            "document_type": "header", "add_by_default": True,
        })
        template = self.env["sale.order.template"].create({"name": "Renovatieproject"})
        template_footer = self.Document.create({
            "name": "renovatie.pdf", "raw": self.source,
            "document_type": "footer", "add_by_default": True,
            "quotation_template_ids": [(6, 0, template.ids)],
        })
        optional = self.Document.create({
            "name": "optioneel.pdf", "raw": self.source,
            "document_type": "footer", "quotation_template_ids": [(6, 0, template.ids)],
        })
        order = self._order(sale_order_template_id=template.id)
        self.assertIn(default_header, order.quotation_document_ids)
        self.assertIn(template_footer, order.quotation_document_ids)
        self.assertNotIn(optional, order.quotation_document_ids)
        # documents chosen explicitly stay as chosen
        chosen = self._order(sale_order_template_id=template.id,
                             quotation_document_ids=[(6, 0, optional.ids)])
        self.assertEqual(chosen.quotation_document_ids, optional)

    def test_frame_report_renders_layout(self):
        """The frame report is a valid QWeb report (HTML, without a PDF engine)."""
        order = self._order()
        html, _type = self.Report._render_qweb_html(
            "tectora_quote_builder.action_report_layout_frame", order.ids
        )
        self.assertIn(b'class="page"', html)
        # wkhtmltopdf leaves out the header and footer of an empty page
        self.assertIn(b'height: 1px', html)
        self.assertNotIn(self.partner.name.encode(), html, "no recipient address in the frame")
