# -*- coding: utf-8 -*-
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    # Hercalculatie: a component a bill of materials counts in m² or m³ (per
    # m² of roof, so much m² of insulation) but that is bought and stocked
    # per piece of L × B (× H). The material list turns the area or volume
    # into pieces.
    tectora_recalc = fields.Boolean(
        string="Hercalculatie",
        help="Op een stuklijst staat de hoeveelheid van dit product in m² of "
        "m³ (de reken-UoM); de materiaallijst rekent die om naar stuks met "
        "de afmetingen hieronder, naar boven afgerond. Bv. 10 m² van een "
        "plaat van 1 m × 0,5 m = 20 stuks.",
    )
    tectora_recalc_uom = fields.Selection(
        [("m2", "m²"), ("m3", "m³")],
        string="Reken-UoM",
        default="m2",
        help="m²: één stuk is L × B. m³: één stuk is L × B × H.",
    )
    tectora_length = fields.Float(string="Lengte (L)", digits=(16, 4), help="In meter.")
    tectora_width = fields.Float(string="Breedte (B)", digits=(16, 4), help="In meter.")
    tectora_height = fields.Float(string="Hoogte (H)", digits=(16, 4), help="In meter.")
    tectora_recalc_size = fields.Float(
        string="Per stuk",
        compute="_compute_tectora_recalc_size",
        digits=(16, 4),
        help="Oppervlakte (m²) of volume (m³) van één stuk.",
    )

    @api.depends("tectora_recalc_uom", "tectora_length", "tectora_width", "tectora_height")
    def _compute_tectora_recalc_size(self):
        for template in self:
            size = template.tectora_length * template.tectora_width
            if template.tectora_recalc_uom == "m3":
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
                        "%(product)s: geef voor de hercalculatie in %(uom)s de "
                        "lengte, de breedte%(height)s groter dan 0 in.",
                        product=template.display_name,
                        uom=dict(self._fields["tectora_recalc_uom"].selection).get(
                            template.tectora_recalc_uom, ""
                        ),
                        height=_(" en de hoogte") if template.tectora_recalc_uom == "m3" else "",
                    )
                )

    def _tectora_recalculate(self, quantity):
        """Pieces for ``quantity`` m² or m³ of this product, rounded up; the
        quantity unchanged when the product has no hercalculatie."""
        self.ensure_one()
        if not self.tectora_recalc or self.tectora_recalc_size <= 0.0:
            return quantity
        pieces = quantity / self.tectora_recalc_size
        # Up to whole pieces, without 20.000000001 becoming 21.
        return float(math.ceil(round(pieces, 6)))
