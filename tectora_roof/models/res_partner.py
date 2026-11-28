# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
    roof_team_ids = fields.Many2many(
        "tectora.roof.team",
        "tectora_roof_team_partner_rel",
        "partner_id",
        "team_id",
        string="Ploegen",
        help="De ploegen waar dit contact lid van is.",
    )
    roof_team_count = fields.Integer(compute="_compute_roof_team_count")

    @api.depends("roof_team_ids")
    def _compute_roof_team_count(self):
        for partner in self:
            partner.roof_team_count = len(partner.roof_team_ids)

    def _tectora_employees(self):
        """The employees behind these contacts (the contact is their work
        contact). Planning and registration run on the contact; only what
        needs an employee -- a timesheet line -- takes this."""
        if not self.ids:
            return self.env["hr.employee"].sudo()
        return self.env["hr.employee"].sudo().search(
            [("work_contact_id", "in", self.ids)]
        )

    def _tectora_one_line_address(self):
        """The address on one line, without the name: "Lostraat 15, 1703
        Schepdaal"."""
        self.ensure_one()
        lines = self._display_address(without_name=True).split("\n")
        return ", ".join(line.strip() for line in lines if line.strip())

    def _tectora_name_with_title(self):
        """The name with the salutation in front: "Dhr. Michiels Philippe"."""
        self.ensure_one()
        title = self.tectora_title_id
        prefix = title.shortcut or title.name if title else ""
        name = self.name or self.display_name or ""
        return f"{prefix} {name}".strip() if prefix else name
