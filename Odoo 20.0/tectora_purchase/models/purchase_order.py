# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    tectora_roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        index=True,
        copy=False,
        ondelete="set null",
        help="Het dakproject waarvan de materiaalbehoefte met deze order "
        "besteld wordt (een dropship-order is altijd van één dakproject).",
    )
    tectora_roof_project_ids = fields.Many2many(
        "tectora.roof.project",
        string="Dakprojecten",
        compute="_compute_tectora_roof_project_ids",
        store=True,
        help="Alle dakprojecten waarvan materiaal op deze order staat.",
    )
    tectora_logistics_route_id = fields.Many2one(
        "tectora.logistics.route",
        string="Logistieke route",
        copy=False,
        help="Dropship naar de werf of levering aan het magazijn; bepaalt de "
        "operatie en het leveradres van de order.",
    )
    tectora_delivery_type = fields.Selection(
        related="tectora_logistics_route_id.delivery_type", string="Levering"
    )
    tectora_planned_date_begin = fields.Datetime(
        related="tectora_roof_project_id.planned_date_begin",
        string="Geplande start werf",
        help="De geplande start van de werken op het dakproject: de dag "
        "waarop een dropship op de werf moet staan.",
    )
    tectora_site_address = fields.Char(
        related="tectora_roof_project_id.address", string="Werfadres"
    )
    tectora_warehouse_pickup = fields.Boolean(
        string="Extra materiaal af te halen aan het magazijn",
        copy=False,
        help="Naast deze dropship-levering op de werf haalt de ploeg nog "
        "materiaal af aan het magazijn (geleverd aan het magazijn of uit "
        "voorraad). Wat precies staat in de toelichting.",
    )
    tectora_warehouse_pickup_note = fields.Text(
        string="Af te halen aan het magazijn",
        copy=False,
        help="Het materiaal van dit dakproject dat niet op deze dropship "
        "staat en aan het magazijn opgehaald wordt.",
    )
    tectora_material_count = fields.Integer(
        string="Materiaallijnen", compute="_compute_tectora_material_count"
    )

    @api.depends("order_line.tectora_material_ids")
    def _compute_tectora_material_count(self):
        for order in self:
            order.tectora_material_count = len(order.order_line.tectora_material_ids)

    @api.depends("order_line.tectora_material_ids.project_id", "tectora_roof_project_id")
    def _compute_tectora_roof_project_ids(self):
        for order in self:
            order.tectora_roof_project_ids = (
                order.order_line.tectora_material_ids.project_id
                | order.tectora_roof_project_id
            )

    def action_view_tectora_materials(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaalbehoefte"),
            "res_model": "tectora.roof.material",
            "view_mode": "list,form",
            "domain": [("purchase_order_id", "=", self.id)],
            "context": {"search_default_group_project": 1},
        }

    def action_view_tectora_roof_project(self):
        self.ensure_one()
        if not self.tectora_roof_project_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "view_mode": "form",
            "res_id": self.tectora_roof_project_id.id,
        }


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    tectora_material_ids = fields.One2many(
        "tectora.roof.material",
        "purchase_line_id",
        string="Materiaalbehoefte",
        help="De materiaallijnen van de dakprojecten die met deze lijn "
        "besteld worden.",
    )
    tectora_roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        compute="_compute_tectora_roof_project_id",
        store=True,
        help="Het dakproject van deze lijn (op een magazijnorder staan de "
        "lijnen per dakproject gegroepeerd).",
    )

    @api.depends("tectora_material_ids.project_id", "order_id.tectora_roof_project_id")
    def _compute_tectora_roof_project_id(self):
        for line in self:
            projects = line.tectora_material_ids.project_id
            line.tectora_roof_project_id = (
                projects[:1] if len(projects) == 1 else line.order_id.tectora_roof_project_id
            )
