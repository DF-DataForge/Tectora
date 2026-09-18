# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_create_material_picking(self):
        """The dashboard's button: the roof project does the work."""
        self.ensure_one()
        roof = self.roof_project_id
        if not roof:
            raise UserError(_("Dit project heeft geen dakproject en dus geen materiaallijst."))
        return roof.action_create_material_picking()
