# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofExecutionReport(models.Model):
    """A day report of the crew on a site: what was done, what was used,
    what went wrong -- with photos. Written from the employee portal, read in
    the back office (Dakmeting -> Uitvoeringsverslagen and the project
    dashboard)."""

    _name = "tectora.roof.execution.report"
    _description = "Uitvoeringsverslag"
    _order = "date desc, id desc"

    name = fields.Char(string="Verslag", compute="_compute_name", store=True)
    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    dossier_project_id = fields.Many2one(
        related="project_id.project_id", string="Project", store=True
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    partner_id = fields.Many2one(related="project_id.partner_id", string="Klant")
    address = fields.Char(related="project_id.address", string="Werfadres")
    planning_id = fields.Many2one(
        "tectora.roof.planning",
        string="Werkblok",
        ondelete="set null",
        domain="[('project_id', '=', project_id)]",
    )
    date = fields.Date(
        string="Datum", required=True, default=fields.Date.context_today, index=True
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Opgesteld door",
        default=lambda self: self.env.user.employee_id,
    )
    user_id = fields.Many2one(
        "res.users", string="Gebruiker", default=lambda self: self.env.user
    )
    progress = fields.Selection(
        [
            ("started", "Gestart"),
            ("in_progress", "In uitvoering"),
            ("finished", "Afgewerkt"),
            ("blocked", "Geblokkeerd"),
        ],
        string="Stand van zaken",
        default="in_progress",
        required=True,
    )
    work_done = fields.Text(string="Uitgevoerde werken", required=True)
    materials_used = fields.Text(string="Gebruikte materialen")
    remarks = fields.Text(string="Opmerkingen / problemen")
    image_ids = fields.Many2many(
        "ir.attachment",
        "tectora_roof_execution_report_attachment_rel",
        "report_id",
        "attachment_id",
        string="Foto's",
    )
    image_count = fields.Integer(compute="_compute_image_count")

    @api.depends("project_id.code", "project_id.name", "date")
    def _compute_name(self):
        for report in self:
            project = report.project_id
            reference = project.code or project.name or ""
            report.name = " — ".join(
                filter(None, ["Uitvoeringsverslag", reference, str(report.date or "")])
            )

    @api.depends("image_ids")
    def _compute_image_count(self):
        for report in self:
            report.image_count = len(report.image_ids)

    def _progress_label(self):
        self.ensure_one()
        return dict(self._fields["progress"]._description_selection(self.env)).get(
            self.progress, self.progress
        )

    def action_open_roof_project(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": self.project_id.id,
            "view_mode": "form",
            "target": "current",
        }
