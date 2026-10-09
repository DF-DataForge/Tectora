# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class TectoraAddRoofsWizard(models.TransientModel):
    """Daken toevoegen: how many roofs the project has, with a description
    each. Every roof gets a plan on the roof project and a subsection under
    the afbouw- and opbouwwerken of the quotation."""

    _name = "tectora.add.roofs.wizard"
    _description = "Daken toevoegen"

    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade")
    existing_count = fields.Integer(
        string="Bestaande daken", compute="_compute_existing_count"
    )
    roof_count = fields.Integer(string="Aantal daken toe te voegen", default=1)
    line_ids = fields.One2many(
        "tectora.add.roofs.wizard.line", "wizard_id", string="Daken"
    )

    @api.depends("order_id")
    def _compute_existing_count(self):
        for wizard in self:
            wizard.existing_count = len(wizard.order_id.roof_project_id.roof_ids)

    @api.onchange("roof_count")
    def _onchange_roof_count(self):
        """One line per roof to add, keeping what was typed already."""
        typed = [(line.name, line.description) for line in self.line_ids.sorted("sequence")]
        count = max(self.roof_count, 0)
        values = []
        for index in range(count):
            name, description = typed[index] if index < len(typed) else (False, False)
            values.append(Command.create({
                "sequence": index,
                "name": name or _("Dak %s", self.existing_count + index + 1),
                "description": description,
            }))
        self.line_ids = [Command.clear()] + values

    def action_apply(self):
        self.ensure_one()
        order = self.order_id
        lines = self.line_ids.filtered("name")
        if not lines:
            raise UserError(_("Geef minstens één dak op."))
        order._tectora_check_roofs_allowed()
        roof_project = order.roof_project_id or order._tectora_create_roof_project(
            raise_if_failed=True
        )
        roofs = self.env["tectora.roof.project.roof"].create([
            {
                "project_id": roof_project.id,
                "name": line.name,
                "description": line.description,
                "sequence": (max(roof_project.roof_ids.mapped("sequence") or [0]) + 1 + index),
            }
            for index, line in enumerate(lines.sorted("sequence"))
        ])
        order._tectora_add_roof_subsections(roofs)
        return {"type": "ir.actions.act_window_close"}


class TectoraAddRoofsWizardLine(models.TransientModel):
    _name = "tectora.add.roofs.wizard.line"
    _description = "Dak toe te voegen"
    _order = "sequence, id"

    wizard_id = fields.Many2one("tectora.add.roofs.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Dak", required=True)
    description = fields.Char(string="Omschrijving")
