# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class QuotationDocument(models.Model):
    """Headers and footers of the quotation (Quote Builder), printed in the
    document layout: every page gets the layout's header and footer."""

    _inherit = "quotation.document"

    tectora_in_layout = fields.Boolean(
        string="In de documentlay-out",
        default=True,
        help="Elke pagina krijgt de kop en voet van de documentlay-out "
        "(Instellingen › Documentlay-out). De eigen band van de pdf wordt "
        "weggelaten en de inhoud ertussen past tussen de kop en de voet van "
        "de lay-out.",
    )
    tectora_crop_top = fields.Float(
        string="Eigen kop weglaten (mm)",
        default=28.0,
        help="Hoogte bovenaan elke pagina van deze pdf die niet afgedrukt "
        "wordt: de band of het logo dat de pdf zelf heeft. 0 = niets weglaten.",
    )
    tectora_crop_bottom = fields.Float(
        string="Eigen voet weglaten (mm)",
        default=24.0,
        help="Hoogte onderaan elke pagina van deze pdf die niet afgedrukt "
        "wordt: de voetband van de pdf zelf. 0 = niets weglaten.",
    )
    tectora_crop_bottom_pages = fields.Char(
        string="Eigen voet enkel op pagina's",
        help="De pagina's van deze pdf die een eigen voetband hebben, bv. "
        "'1,4' of '1-2, 5'. Leeg = alle pagina's. Op de andere pagina's loopt "
        "de inhoud door tot onderaan en wordt er onderaan niets weggelaten.",
    )
    tectora_customer_name = fields.Boolean(
        string="Naam klant op de eerste pagina",
        help="Drukt de naam van de klant, met de aanspreektitel ervoor "
        "(Dhr., Mevr., ...), op de eerste pagina van deze pdf af, "
        "gecentreerd (bv. onder 'Voorstel op maat' op de voorpagina). Enkel "
        "voor de eerste kop van de offerte.",
    )
    tectora_customer_name_top = fields.Float(
        string="Positie naam klant (mm van boven)",
        default=232.0,
        help="Afstand van de bovenkant van de oorspronkelijke pdf-pagina tot "
        "de naam van de klant.",
    )

    @api.constrains("tectora_crop_bottom_pages")
    def _check_tectora_crop_bottom_pages(self):
        for document in self:
            try:
                document._tectora_crop_bottom_page_numbers()
            except ValueError:
                raise ValidationError(self.env._(
                    "Pagina's met een eigen voet: geef paginanummers of reeksen, "
                    "gescheiden door komma's, bv. '1,4' of '1-2, 5'."
                )) from None

    def _tectora_crop_bottom_page_numbers(self):
        """The (1-based) page numbers with their own footer band, or None
        for all pages."""
        self.ensure_one()
        spec = (self.tectora_crop_bottom_pages or "").replace(" ", "")
        if not spec:
            return None
        pages = set()
        for part in spec.split(","):
            if not part:
                continue
            start, _sep, end = part.partition("-")
            first, last = int(start), int(end or start)
            if first < 1 or last < first:
                raise ValueError(part)
            pages.update(range(first, last + 1))
        return pages
