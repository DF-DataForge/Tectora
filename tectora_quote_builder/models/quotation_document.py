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
        "(Instellingen › Documentlay-out), over de pagina heen. De pagina "
        "blijft op ware grootte; de eigen band van de pdf valt weg.",
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
    tectora_crop_top_pages = fields.Char(
        string="Eigen kop enkel op pagina's",
        help="De pagina's van deze pdf die bovenaan een eigen band of logo "
        "hebben, bv. '1,2,4'. Leeg = alle pagina's. Op de andere pagina's "
        "wordt er bovenaan niets weggelaten.",
    )
    tectora_fit_pages = fields.Char(
        string="Verkleinen op pagina's",
        help="Pagina's waarvan de inhoud tot tegen de rand loopt, bv. '3': ze "
        "worden verkleind tot ze tussen de kop en de voet van de lay-out "
        "passen, zodat de kop geen tekst bedekt. Leeg = alle pagina's op ware "
        "grootte.",
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
        "(Dhr., Mevr., ...), en eronder het werfadres (het afleveradres van "
        "de offerte) op de eerste pagina van deze pdf af, "
        "gecentreerd (bv. onder 'Voorstel op maat' op de voorpagina). Enkel "
        "voor de eerste kop van de offerte.",
    )
    tectora_customer_name_top = fields.Float(
        string="Positie naam klant (mm van boven)",
        default=232.0,
        help="Afstand van de bovenkant van de oorspronkelijke pdf-pagina tot "
        "de naam van de klant.",
    )

    @api.constrains("tectora_crop_top_pages", "tectora_crop_bottom_pages", "tectora_fit_pages")
    def _check_tectora_page_numbers(self):
        for document in self:
            for fname in ("tectora_crop_top_pages", "tectora_crop_bottom_pages", "tectora_fit_pages"):
                try:
                    document._tectora_page_numbers(fname)
                except ValueError:
                    raise ValidationError(self.env._(
                        "%(field)s: geef paginanummers of reeksen, gescheiden door "
                        "komma's, bv. '1,4' of '1-2, 5'.",
                        field=document._fields[fname].string,
                    )) from None

    def _tectora_page_numbers(self, fname):
        """The (1-based) page numbers in a page field ("1,4", "1-2, 5"), or
        None when it is empty."""
        self.ensure_one()
        spec = (self[fname] or "").replace(" ", "")
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

    def _tectora_crop_bottom_page_numbers(self):
        """The page numbers with their own footer band, or None for all."""
        return self._tectora_page_numbers("tectora_crop_bottom_pages")
