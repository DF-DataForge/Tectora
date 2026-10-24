# -*- coding: utf-8 -*-
from odoo import fields, models


class TectoraPartnerTitle(models.Model):
    """Salutation of a contact ("De heer" / "Dhr."). Odoo 20 dropped the
    partner titles of earlier versions; the quotation's cover puts the short
    form in front of the customer's name."""

    _name = "tectora.partner.title"
    _description = "Aanspreektitel"
    _order = "sequence, id"

    name = fields.Char(string="Aanspreektitel", required=True, translate=True)
    shortcut = fields.Char(
        string="Afkorting", translate=True,
        help="Zoals het voor de naam staat, bv. 'Dhr.'. Leeg = de aanspreektitel zelf.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class ResPartner(models.Model):
    _inherit = "res.partner"

    tectora_title_id = fields.Many2one(
        "tectora.partner.title", string="Aanspreektitel", ondelete="restrict",
    )

    def _tectora_name_with_title(self):
        """The name with the salutation in front: "Dhr. Michiels Philippe"."""
        self.ensure_one()
        title = self.tectora_title_id
        prefix = title.shortcut or title.name if title else ""
        name = self.name or self.display_name or ""
        return f"{prefix} {name}".strip() if prefix else name
