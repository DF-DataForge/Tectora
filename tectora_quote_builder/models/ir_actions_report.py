# -*- coding: utf-8 -*-
"""The headers and footers of the quotation (Quote Builder) in the document
layout.

Odoo adds the header and footer PDFs as they are, around the quotation. Here
every page of such a PDF gets the header and footer of the document layout
(Settings › Document Layout): the frame report renders the layout's header
and footer on an otherwise empty, transparent page, which is laid over the
PDF page at full size; the PDF's own band (the heights set on the document)
is left out underneath. The first header can also carry the name of the
customer.
"""
import contextlib
import io
import logging
import zlib

import pypdf.filters
from pypdf import PageObject, Transformation
from pypdf.generic import ContentStream
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from odoo import api, models
from odoo.tools.pdf import PdfFileReader, PdfFileWriter

_logger = logging.getLogger(__name__)

MM = 72 / 25.4  # PDF points per millimetre
FRAME_REPORT = "tectora_quote_builder.action_report_layout_frame"
# How far under the lower edge of the layout's header a page is cut, so the
# header's own line and its anti-aliasing never show the page beneath.
CONTOUR_MARGIN_MM = 0.5


@contextlib.contextmanager
def lenient_flate():
    """Decompress the page streams as pypdf itself does.

    Odoo replaces pypdf's decompress by a stricter one (odoo/tools/pdf), which
    fails on streams that pypdf reads byte by byte as a last resort; PDFs from
    design tools have such streams. Odoo only copies the pages of a header or
    footer, these pages are drawn on the layout frame and so decompressed.
    """
    strict = pypdf.filters.decompress

    def decompress(data):
        try:
            return strict(data)
        except zlib.error:
            stream = zlib.decompressobj(zlib.MAX_WBITS | 32)
            result = b""
            for index in range(len(data)):
                try:
                    result += stream.decompress(data[index:index + 1])
                except zlib.error:
                    pass
            return result

    pypdf.filters.decompress = decompress
    try:
        yield
    finally:
        pypdf.filters.decompress = strict


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        if self._get_report(report_ref).report_name == "sale.report_saleorder":
            # One layout frame per order, rendered once for all its documents.
            self = self.with_context(tectora_layout_frames={})
        return super(IrActionsReport, self)._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )

    @api.model
    def _update_mapping_and_add_pages_to_writer(
        self, writer, document, form_fields_values_mapping, prefix, order, order_line=None
    ):
        if document._name == "quotation.document" and (
            document.tectora_in_layout or document.tectora_customer_name
        ):
            self = self.with_context(tectora_quotation_document=document, tectora_order=order)
        return super(IrActionsReport, self)._update_mapping_and_add_pages_to_writer(
            writer, document, form_fields_values_mapping, prefix, order, order_line=order_line
        )

    @api.model
    def _add_pages_to_writer(self, writer, document, prefix=None):
        quotation_document = self.env.context.get("tectora_quotation_document")
        order = self.env.context.get("tectora_order")
        if quotation_document and order:
            document = self._tectora_prepare_quotation_document(quotation_document, document, order)
        return super()._add_pages_to_writer(writer, document, prefix=prefix)

    # ------------------------------------------------------------------ pages
    @api.model
    def _tectora_prepare_quotation_document(self, quotation_document, content, order):
        """The pages of a header or footer as printed on the quotation: with
        the customer's name on the first page of the first header, and in the
        frame of the document layout."""
        stamp = quotation_document.tectora_customer_name and self._tectora_is_first_header(
            quotation_document, order
        )
        frame = quotation_document.tectora_in_layout and self._tectora_layout_frame(order)
        with lenient_flate():
            if stamp:
                content = self._tectora_stamp_customer_name(
                    content, order, quotation_document.tectora_customer_name_top
                )
            if frame:
                content = self._tectora_put_in_frame(
                    content,
                    frame["pdf"],
                    crop_top=quotation_document.tectora_crop_top * MM,
                    crop_bottom=quotation_document.tectora_crop_bottom * MM,
                    crop_bottom_pages=quotation_document._tectora_crop_bottom_page_numbers(),
                    crop_top_pages=quotation_document._tectora_page_numbers("tectora_crop_top_pages"),
                    fit_pages=quotation_document._tectora_page_numbers("tectora_fit_pages") or (),
                    body_top=frame["margin_top"],
                    body_bottom=frame["margin_bottom"],
                    header_contour=frame.get("contour"),
                )
        return content

    @api.model
    def _tectora_is_first_header(self, quotation_document, order):
        headers = order.quotation_document_ids.filtered(lambda doc: doc.document_type == "header")
        return headers[:1] == quotation_document

    @api.model
    def _tectora_layout_frame(self, order):
        """The page with only the header and footer of the document layout
        for this order, with the margins (in points) of the space between
        them: {"pdf", "margin_top", "margin_bottom"}. False when it cannot be
        rendered: the document is then printed as it is."""
        frames = self.env.context.get("tectora_layout_frames")
        if frames is not None and order.id in frames:
            return frames[order.id]
        frame = False
        # Rendered with a clean context: the documents and orders in it are
        # only meant for the pages of the quotation.
        context = {k: v for k, v in self.env.context.items() if not k.startswith("tectora_")}
        clean = self.with_env(self.env(context=context))
        try:
            report = clean.env.ref(FRAME_REPORT)
            pdf, _report_type = clean._render_qweb_pdf(report, order.ids)
            paperformat = report.get_paperformat()
            company = order.company_id or self.env.company
            frame = {
                "pdf": pdf,
                "margin_top": (paperformat.margin_top or 0) * MM,
                "margin_bottom": (paperformat.margin_bottom or 0) * MM,
                # The lower edge of the layout's header (tectora_report_layout),
                # to cut the page's own band away along it.
                "contour": (
                    company._tectora_header_contour()
                    if hasattr(company, "_tectora_header_contour") else None
                ),
            }
        except Exception:
            _logger.exception("Lay-outkader voor offerte %s kon niet gemaakt worden", order.name)
        if frames is not None:
            frames[order.id] = frame
        return frame

    @api.model
    def _tectora_stamp_customer_name(self, content, order, top_mm):
        """The customer's name with the salutation ("Dhr. Michiels
        Philippe"), centred on the first page, `top_mm` from its top, in the
        company's primary colour; under it the site: the delivery address of
        the order ("Werfadres: Lostraat 15, 1703 Schepdaal")."""
        reader = PdfFileReader(io.BytesIO(content), strict=False)
        writer = PdfFileWriter()
        for index, page in enumerate(reader.pages):
            if index == 0:
                box = page.mediabox
                width, height = float(box.width), float(box.height)
                overlay = io.BytesIO()
                pdf = canvas.Canvas(overlay, pagesize=(width, height))
                pdf.setFillColor(HexColor(order.company_id.primary_color or "#008B93"))
                pdf.setFont("Helvetica-Bold", 20)
                name = order.partner_id._tectora_name_with_title()
                pdf.drawCentredString(width / 2, height - top_mm * MM, name)
                site = self._tectora_site_address(order)
                if site:
                    pdf.setFont("Helvetica", 12)
                    pdf.drawCentredString(width / 2, height - (top_mm + 8) * MM, f"Werfadres: {site}")
                pdf.save()
                stamp = PdfFileReader(io.BytesIO(overlay.getvalue())).pages[0]
                page.merge_transformed_page(
                    stamp, Transformation().translate(float(box.left), float(box.bottom))
                )
            writer.add_page(page)
        return self._tectora_pdf_bytes(writer)

    @api.model
    def _tectora_site_address(self, order):
        """The delivery address of the order on one line, "" without street
        or city."""
        partner = order.partner_shipping_id or order.partner_id
        city = " ".join(part for part in (partner.zip, partner.city) if part)
        return ", ".join(part for part in (partner.street, partner.street2, city) if part)

    @api.model
    def _tectora_put_in_frame(
        self, content, frame_pdf, crop_top, crop_bottom, crop_bottom_pages=None,
        crop_top_pages=None, fit_pages=(), body_top=0.0, body_bottom=0.0,
        header_contour=None,
    ):
        """Every page of `content` with the frame (the header and footer of
        the document layout) on top, without `crop_top` and `crop_bottom`
        points (the page's own header and footer band).

        A page is printed at full size, scaled to the frame's width if it
        has another one; a page in `fit_pages` (its content runs up to the
        edge) is scaled down to fit between `body_top` and `body_bottom`
        points, the space between the layout's header and footer. Page
        numbers are 1-based; `crop_top_pages` / `crop_bottom_pages`: the
        pages with a band of their own, None for all.

        `header_contour`: the lower edge of the layout's header, as points
        (fraction of the width, mm from the top). A page whose own band is
        left out is then cut along that edge (and at least `crop_top` deep),
        not along a straight line: a header with a sloped side (the roof
        edge) would otherwise leave a white wedge where the page was cut
        higher than the header comes down, and a piece of the page's own
        band where it was cut lower.
        """
        reader = PdfFileReader(io.BytesIO(content), strict=False)
        writer = PdfFileWriter()
        for number, page in enumerate(reader.pages, start=1):
            page_crop_top = crop_top if crop_top_pages is None or number in crop_top_pages else 0.0
            page_crop_bottom = (
                crop_bottom if crop_bottom_pages is None or number in crop_bottom_pages else 0.0
            )
            frame_page = PdfFileReader(io.BytesIO(frame_pdf), strict=False).pages[0]
            frame_width = float(frame_page.mediabox.width)
            frame_height = float(frame_page.mediabox.height)
            box = page.mediabox
            left, width = float(box.left), float(box.width)
            bottom = float(box.bottom) + page_crop_bottom
            top = float(box.top) - page_crop_top
            if top <= bottom:
                bottom, top = float(box.bottom), float(box.top)
            body_height = frame_height - body_top - body_bottom
            if number in fit_pages and body_height > 0:
                scale = min(frame_width / width, body_height / (top - bottom))
                offset_x = (frame_width - width * scale) / 2 - left * scale
                offset_y = frame_height - body_top - top * scale
                outline = None
            else:
                scale = frame_width / width
                offset_x = -left * scale
                offset_y = frame_height - float(box.top) * scale
                outline = header_contour and page_crop_top and self._tectora_header_outline(
                    header_contour, left, width, top,
                    to_page_y=lambda mm: (frame_height - mm * MM - offset_y) / scale,
                )
            if outline:
                self._tectora_clip_page_to(
                    page, [(left, bottom), (left + width, bottom)] + outline[::-1]
                )
            else:
                self._tectora_clip_page(page, left, bottom, width, top - bottom)
            sheet = PageObject.create_blank_page(width=frame_width, height=frame_height)
            sheet.merge_transformed_page(
                page, Transformation().scale(scale, scale).translate(offset_x, offset_y)
            )
            # The layout's header and footer over the page: the frame is
            # transparent between them.
            sheet.merge_page(frame_page)
            writer.add_page(sheet)
        return self._tectora_pdf_bytes(writer)

    @api.model
    def _tectora_header_outline(self, contour, left, width, crop_y, to_page_y):
        """The top side of what stays of a page under the layout's header, in
        the page's own coordinates, from left to right: the header's lower
        edge (`contour`, a little lower to cover its line), but never above
        `crop_y` (the straight cut of the page's own band). `to_page_y` turns
        millimetres from the top of the frame into the page's y."""
        points = [
            (left + fraction * width, to_page_y(mm + CONTOUR_MARGIN_MM))
            for fraction, mm in sorted(contour)
        ]
        if len(points) < 2:
            return None
        outline = []
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            outline.append((x1, min(y1, crop_y)))
            # Where the edge crosses the straight cut, both meet.
            if (y1 - crop_y) * (y2 - crop_y) < 0:
                x = x1 + (crop_y - y1) * (x2 - x1) / (y2 - y1)
                outline.append((x, crop_y))
        outline.append((points[-1][0], min(points[-1][1], crop_y)))
        return outline

    @api.model
    def _tectora_clip_page(self, page, x, y, width, height):
        """Only what lies within the rectangle is drawn of the page."""
        self._tectora_clip_contents(page, b"%.3f %.3f %.3f %.3f re " % (x, y, width, height))

    @api.model
    def _tectora_clip_page_to(self, page, polygon):
        """Only what lies within the polygon (page coordinates) is drawn of
        the page."""
        path = b"%.3f %.3f m " % polygon[0] + b"".join(
            b"%.3f %.3f l " % point for point in polygon[1:]
        )
        self._tectora_clip_contents(page, path + b"h ")

    @api.model
    def _tectora_clip_contents(self, page, path):
        """Only what lies within `path` (PDF path operators) is drawn of the
        page."""
        contents = page.get_contents()
        data = contents.get_data() if contents is not None else b""
        clipped = ContentStream(None, None)
        clipped.set_data(b"q " + path + b"W n\n" + data + b"\nQ\n")
        page.replace_contents(clipped)

    @api.model
    def _tectora_pdf_bytes(self, writer):
        with io.BytesIO() as buffer:
            writer.write(buffer)
            return buffer.getvalue()
