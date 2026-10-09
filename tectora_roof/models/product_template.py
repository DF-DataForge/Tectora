# -*- coding: utf-8 -*-
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Two time norms per sold unit, because one works item can carry both: a
    # "leveren en plaatsen" post that first takes the old one down.
    tectora_hours_execution_per_uom = fields.Float(
        string="Uren opbouw per eenheid",
        digits=(16, 3),
        help="Uitvoeringstijd van de opbouwwerken in uren per verkochte eenheid "
        "van dit product (per m², per lm, per stuk); 0,25 is een kwartier. "
        "Elke offertelijn vermenigvuldigt dit met haar hoeveelheid; de som "
        "staat op de offerte en wordt bij bevestiging de toegewezen tijd van "
        "de taak Uitvoeringswerken van het project.",
    )
    tectora_hours_demolition_per_uom = fields.Float(
        string="Uren afbraak per eenheid",
        digits=(16, 3),
        help="Tijd van de afbraakwerken in uren per verkochte eenheid van dit "
        "product. Wordt op dezelfde manier gesommeerd en bij bevestiging de "
        "toegewezen tijd van de taak Afbraakwerken van het project.",
    )

    # Hercalculatie: a component a bill of materials counts in m, m² or m³
    # (per m² of roof, so much m² of insulation) but that is bought and
    # stocked per piece of L, L × B or L × B × H. The material list turns the
    # length, area or volume into pieces.
    tectora_recalc = fields.Boolean(
        string="Hercalculatie",
        help="Op een stuklijst staat de hoeveelheid van dit product in m, m² "
        "of m³ (de reken-UoM); de materiaallijst rekent die om naar stuks met "
        "de afmetingen hieronder, naar boven afgerond. Bv. 10 m² van een "
        "plaat van 1 m × 0,5 m = 20 stuks; 10 m van een profiel van 3 m = 4 "
        "stuks.",
    )
    tectora_recalc_uom = fields.Selection(
        [("m", "m"), ("m2", "m²"), ("m3", "m³")],
        string="Reken-UoM",
        default="m2",
        help="m: één stuk is L (B en H staan er ter info). m²: één stuk is L × B. "
        "m³: één stuk is L × B × H.",
    )
    tectora_length = fields.Float(string="Lengte (L)", digits=(16, 4), help="In meter.")
    tectora_width = fields.Float(string="Breedte (B)", digits=(16, 4), help="In meter.")
    tectora_height = fields.Float(string="Hoogte (H)", digits=(16, 4), help="In meter.")
    tectora_recalc_size = fields.Float(
        string="Per stuk",
        compute="_compute_tectora_recalc_size",
        digits=(16, 4),
        help="Lengte (m), oppervlakte (m²) of volume (m³) van één stuk.",
    )

    @api.depends("tectora_recalc_uom", "tectora_length", "tectora_width", "tectora_height")
    def _compute_tectora_recalc_size(self):
        for template in self:
            uom = template.tectora_recalc_uom
            size = template.tectora_length
            if uom in ("m2", "m3"):
                size *= template.tectora_width
            if uom == "m3":
                size *= template.tectora_height
            template.tectora_recalc_size = size

    @api.constrains(
        "tectora_recalc", "tectora_recalc_uom",
        "tectora_length", "tectora_width", "tectora_height",
    )
    def _check_tectora_recalc(self):
        for template in self.filtered("tectora_recalc"):
            if template.tectora_recalc_size <= 0.0:
                raise ValidationError(
                    _(
                        "%(product)s: geef voor de hercalculatie in %(uom)s %(sizes)s "
                        "groter dan 0 in.",
                        product=template.display_name,
                        uom=dict(self._fields["tectora_recalc_uom"].selection).get(
                            template.tectora_recalc_uom, ""
                        ),
                        sizes={
                            "m": _("de lengte"),
                            "m2": _("de lengte en de breedte"),
                        }.get(template.tectora_recalc_uom, _("de lengte, de breedte en de hoogte")),
                    )
                )

    def _tectora_recalculate(self, quantity):
        """Pieces for ``quantity`` m, m² or m³ of this product, rounded up; the
        quantity unchanged when the product has no hercalculatie."""
        self.ensure_one()
        if not self.tectora_recalc or self.tectora_recalc_size <= 0.0:
            return quantity
        pieces = quantity / self.tectora_recalc_size
        # Up to whole pieces, without 20.000000001 becoming 21.
        return float(math.ceil(round(pieces, 6)))

    def _tectora_recalc_explanation(self, quantity, rounded=False):
        """How ``quantity`` in the Reken-UoM becomes pieces, as a line of
        text for a bill of materials: "1,00 m² ÷ 0,72 m² per stuk = 1,39
        stuks". With ``rounded``, the whole pieces the material list takes.
        Empty when the product has no hercalculatie."""
        self.ensure_one()
        size = self.tectora_recalc_size
        if not self.tectora_recalc or size <= 0.0:
            return ""
        unit = dict(self._fields["tectora_recalc_uom"].selection).get(self.tectora_recalc_uom, "")
        exact = quantity / size
        text = _(
            "%(qty)s %(unit)s ÷ %(size)s %(unit)s per stuk = %(pieces)s stuks",
            qty=formatLang(self.env, quantity, digits=2),
            unit=unit,
            size=formatLang(self.env, size, digits=4).rstrip("0").rstrip(",.") or "0",
            pieces=formatLang(self.env, exact, digits=2),
        )
        if rounded:
            text = _("%(text)s → %(whole)s stuks op de materiaallijst", text=text,
                     whole=formatLang(self.env, self._tectora_recalculate(quantity), digits=0))
        return text
