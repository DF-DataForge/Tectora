# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    roof_planning_id = fields.Many2one(
        "tectora.roof.planning",
        string="Dakwerkblok",
        index=True,
        ondelete="cascade",
        copy=False,
        help="Werkblok van het dakproject waaruit deze planning-item komt.",
    )
    roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        compute="_compute_roof_project_id",
        store=True,
        index=True,
        help="Dakproject van deze planning-item: van het werkblok, of van het "
        "projectdossier waaraan de shift hangt.",
    )
    roof_team_id = fields.Many2one(
        related="roof_planning_id.team_id",
        string="Ploeg",
        store=True,
        index=True,
    )
    roof_partner_id = fields.Many2one(
        related="roof_project_id.partner_id", string="Klant"
    )
    roof_address = fields.Char(related="roof_project_id.address", string="Werfadres")

    @api.depends("roof_planning_id.project_id")
    def _compute_roof_project_id(self):
        """A shift belongs to a roof project either through a work block or —
        for shifts the Planning app itself created — through the project
        dossier the roof project owns. That way existing planning.slot records
        are picked up instead of being duplicated."""
        has_project = "project_id" in self._fields
        dossiers = {}
        if has_project:
            dossier_ids = self.mapped("project_id").ids
            if dossier_ids:
                roof_projects = self.env["tectora.roof.project"].search(
                    [("project_id", "in", dossier_ids)]
                )
                dossiers = {
                    project.project_id.id: project for project in roof_projects
                }
        for slot in self:
            project = slot.roof_planning_id.project_id
            if not project and has_project and slot.project_id:
                project = dossiers.get(slot.project_id.id)
            slot.roof_project_id = project
