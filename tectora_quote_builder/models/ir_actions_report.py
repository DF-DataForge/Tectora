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


# The layout frames rendered so far, per database and company: the frame only
# shows the layout's header and footer, so it is the same for every order of
# a company until the company, its layout or its data change (see
# _tectora_frame_key). Saves a wkhtmltopdf run on every print.
FRAME_CACHE = {}
FRAME_CACHE_SIZE = 16
DECOMPRESS_CHUNK = 64 * 1024


def _decompress_damaged(data):
    """What can be read of a damaged stream, as pypdf does as a last resort
    (byte by byte, skipping what does not decompress), but in chunks: only
    a chunk that fails is read byte by byte, and the result is collected
    once instead of copied at every byte."""
    stream = zlib.decompressobj(zlib.MAX_WBITS | 32)
    result = bytearray()
    for start in range(0, len(data), DECOMPRESS_CHUNK):
        chunk = data[start:start + DECOMPRESS_CHUNK]
        saved = stream.copy()
        try:
            result += stream.decompress(chunk)
            continue
        except zlib.error:
            stream = saved
        for index in range(len(chunk)):
            try:
                result += stream.decompress(chunk[index:index + 1])
            except zlib.error:
                pass
    return bytes(result)


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
            return _decompress_damaged(data)

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
            if stamp and not frame:
                content = self._tectora_stamp_customer_name(
                    content, order, quotation_document.tectora_customer_name_top
                )
            if frame:
                # One pass: the name is stamped on the first page while the
                # pages are put in the frame, the PDF is read and written once.
                stamp_first_page = stamp and (
                    lambda page: self._tectora_stamp_page(
                        page, order, quotation_document.tectora_customer_name_top
                    )
                )
                content = self._tectora_put_in_frame(
                    content,
                    frame["pdf"],
                    stamp_first_page=stamp_first_page or None,
                    crop_top=quotation_document.tectora_crop_top * MM,
                    crop_bottom=quotation_document.tectora_crop_bottom * MM,
                    crop_bottom_pages=quotation_document._tectora_crop_bottom_page_numbers(),
                    crop_top_pages=quotation_document._tectora_page_numbers("tectora_crop_top_pages"),
                    fit_pages=quotation_document._tectora_page_numbers("tectora_fit_pages") or (),
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
            key = clean._tectora_frame_key(report, order)
            frame = FRAME_CACHE.get(key)
            if frame is None:
                pdf, _report_type = clean._render_qweb_pdf(report, order.ids)
                paperformat = report.get_paperformat()
                frame = {
                    "pdf": pdf,
                    "margin_top": (paperformat.margin_top or 0) * MM,
                    "margin_bottom": (paperformat.margin_bottom or 0) * MM,
                }
                if len(FRAME_CACHE) >= FRAME_CACHE_SIZE:
                    FRAME_CACHE.pop(next(iter(FRAME_CACHE)))
                FRAME_CACHE[key] = frame
        except Exception:
            _logger.exception("Lay-outkader voor offerte %s kon niet gemaakt worden", order.name)
        if frames is not None:
            frames[order.id] = frame
        return frame

    @api.model
    def _tectora_frame_key(self, report, order):
        """What the layout frame depends on: the company with its layout,
        logo, colours and footer data (its partner and bank accounts), the
        paper format, the language, and the views (a module upgrade loads a
        new registry). Not the order: the frame shows no recipient or title."""
        company = order.company_id or self.env.company
        partner = company.partner_id
        paperformat = report.get_paperformat()
        return (
            self.env.cr.dbname,
            getattr(self.env.registry, "registry_sequence", None),
            company.id,
            str(company.write_date),
            str(partner.write_date),
            tuple(sorted(str(bank.write_date) for bank in partner.bank_ids)),
            company.external_report_layout_id.id,
            paperformat.id,
            str(paperformat.write_date),
            str(report.write_date),
            self.env.context.get("lang") or self.env.lang,
        )

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
                self._tectora_stamp_page(page, order, top_mm)
            writer.add_page(page)
        return self._tectora_pdf_bytes(writer)

    @api.model
    def _tectora_stamp_page(self, page, order, top_mm):
        """Stamps the customer's name and the site on `page` (in place)."""
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
        stamp_first_page=None,
    ):
        """Every page of `content` with the frame (the header and footer of
        the document layout) on top, without `crop_top` and `crop_bottom`
        points (the page's own header and footer band).

        A page is printed at full size, scaled to the frame's width if it
        has another one; a page in `fit_pages` (its content runs up to the
        edge) is scaled down to fit between `body_top` and `body_bottom`
        points, the space between the layout's header and footer. Page
        numbers are 1-based; `crop_top_pages` / `crop_bottom_pages`: the
        pages with a band of their own, None for all. `stamp_first_page`:
        called with the first page before it is framed (the customer's name).
        """
        reader = PdfFileReader(io.BytesIO(content), strict=False)
        writer = PdfFileWriter()
        frame_page = PdfFileReader(io.BytesIO(frame_pdf), strict=False).pages[0]
        for number, page in enumerate(reader.pages, start=1):
            if number == 1 and stamp_first_page:
                stamp_first_page(page)
            page_crop_top = crop_top if crop_top_pages is None or number in crop_top_pages else 0.0
            page_crop_bottom = (
                crop_bottom if crop_bottom_pages is None or number in crop_bottom_pages else 0.0
            )
            frame_width = float(frame_page.mediabox.width)
            frame_height = float(frame_page.mediabox.height)
            box = page.mediabox
            left, width = float(box.left), float(box.width)
            bottom = float(box.bottom) + page_crop_bottom
            top = float(box.top) - page_crop_top
            if top <= bottom:
                bottom, top = float(box.bottom), float(box.top)
            self._tectora_clip_page(page, left, bottom, width, top - bottom)
            body_height = frame_height - body_top - body_bottom
            if number in fit_pages and body_height > 0:
                scale = min(frame_width / width, body_height / (top - bottom))
                offset_x = (frame_width - width * scale) / 2 - left * scale
                offset_y = frame_height - body_top - top * scale
            else:
                scale = frame_width / width
                offset_x = -left * scale
                offset_y = frame_height - float(box.top) * scale
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
