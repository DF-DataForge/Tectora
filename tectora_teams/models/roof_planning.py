# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofPlanning(models.Model):
    """A work block shows the vehicles of its ploeg."""

    _inherit = "tectora.roof.planning"

    vehicle_names = fields.Char(
        string="Voertuigen van de ploeg",
        compute="_compute_vehicle_names",
        help="De voertuigen van het wagenpark die aan de ploeg van dit "
        "werkblok toegewezen zijn.",
    )

    @api.depends("team_id.vehicle_ids", "team_id.vehicle_ids.license_plate")
    def _compute_vehicle_names(self):
        # As text: whoever plans need not have access to the Fleet app.
        for item in self:
            vehicles = item.team_id.sudo().vehicle_ids
            item.vehicle_names = ", ".join(
                " ".join(filter(None, [vehicle.license_plate, vehicle.model_id.display_name]))
                for vehicle in vehicles
            ) or False
