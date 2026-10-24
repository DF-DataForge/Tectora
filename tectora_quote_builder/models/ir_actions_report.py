# -*- coding: utf-8 -*-
"""The headers and footers of the quotation (Quote Builder) in the document
layout.

Odoo adds the header and footer PDFs as they are, around the quotation. Here
every page of such a PDF is printed in the frame of the document layout
(Settings › Document Layout): the frame report renders the layout's header
and footer around an empty page, the PDF page without its own band (the
heights set on the document) is scaled into the space between them. The
first header can also carry the name of the customer.
"""
import contextlib
import io
import logging
import zlib

import pypdf.filters
from pypdf import Transformation
from pypdf.generic import ContentStream
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from odoo import api, models
from odoo.tools.pdf import PdfFileReader, PdfFileWriter

_logger = logging.getLogger(__name__)

MM = 72 / 25.4  # PDF points per millimetre
FRAME_REPORT = "tectora_quote_builder.action_report_layout_frame"


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
                content = self._tectora_fit_into_frame(
                    content,
                    frame["pdf"],
                    crop_top=quotation_document.tectora_crop_top * MM,
                    crop_bottom=quotation_document.tectora_crop_bottom * MM,
                    crop_bottom_pages=quotation_document._tectora_crop_bottom_page_numbers(),
                    body_top=frame["margin_top"],
                    body_bottom=frame["margin_bottom"],
                )
        return content

    @api.model
    def _tectora_is_first_header(self, quotation_document, order):
        headers = order.quotation_document_ids.filtered(lambda doc: doc.document_type == "header")
        return headers[:1] == quotation_document

    @api.model
    def _tectora_layout_frame(self, order):
        """The empty page with the header and footer of the document layout
        for this order, and the margins (in points) of the space between
        them. False when it cannot be rendered: the document is then printed
        as it is."""
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
            frame = {
                "pdf": pdf,
                "margin_top": (paperformat.margin_top or 0) * MM,
                "margin_bottom": (paperformat.margin_bottom or 0) * MM,
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
        company's primary colour."""
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
                pdf.save()
                stamp = PdfFileReader(io.BytesIO(overlay.getvalue())).pages[0]
                page.merge_transformed_page(
                    stamp, Transformation().translate(float(box.left), float(box.bottom))
                )
            writer.add_page(page)
        return self._tectora_pdf_bytes(writer)

    @api.model
    def _tectora_fit_into_frame(
        self, content, frame_pdf, crop_top, crop_bottom, body_top, body_bottom, crop_bottom_pages=None
    ):
        """Every page of `content` in the frame: the page without `crop_top`
        and `crop_bottom` points (its own header and footer) is scaled to fit
        between `body_top` and `body_bottom` points of the frame page, centred
        horizontally and aligned to the top. `crop_bottom_pages`: the page
        numbers (1-based) that have a footer of their own; None for all."""
        reader = PdfFileReader(io.BytesIO(content), strict=False)
        writer = PdfFileWriter()
        for number, page in enumerate(reader.pages, start=1):
            page_crop_bottom = (
                crop_bottom if crop_bottom_pages is None or number in crop_bottom_pages else 0.0
            )
            frame_page = PdfFileReader(io.BytesIO(frame_pdf), strict=False).pages[0]
            frame_width = float(frame_page.mediabox.width)
            frame_height = float(frame_page.mediabox.height)
            box = page.mediabox
            left, right = float(box.left), float(box.right)
            bottom = float(box.bottom) + page_crop_bottom
            top = float(box.top) - crop_top
            if top <= bottom:
                bottom, top = float(box.bottom), float(box.top)
            region_width, region_height = right - left, top - bottom
            body_height = frame_height - body_top - body_bottom
            if body_height <= 0:
                body_height = frame_height
                body_top = 0
            scale = min(frame_width / region_width, body_height / region_height)
            self._tectora_clip_page(page, left, bottom, region_width, region_height)
            offset_x = (frame_width - region_width * scale) / 2 - left * scale
            offset_y = frame_height - body_top - top * scale
            frame_page.merge_transformed_page(
                page, Transformation().scale(scale, scale).translate(offset_x, offset_y)
            )
            writer.add_page(frame_page)
        return self._tectora_pdf_bytes(writer)

    @api.model
    def _tectora_clip_page(self, page, x, y, width, height):
        """Only what lies within the rectangle is drawn of the page."""
        contents = page.get_contents()
        data = contents.get_data() if contents is not None else b""
        clipped = ContentStream(None, None)
        clipped.set_data(
            b"q %.3f %.3f %.3f %.3f re W n\n" % (x, y, width, height) + data + b"\nQ\n"
        )
        page.replace_contents(clipped)

    @api.model
    def _tectora_pdf_bytes(self, writer):
        with io.BytesIO() as buffer:
            writer.write(buffer)
            return buffer.getvalue()
