# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import BinaryBytes


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

    # ---------------------------------------------------- transport order
    # "Bestelbon materialen": the delivery instructions for the vendor of a
    # project's order, from the site information of the roof project, sent
    # with the purchase order (report/transport_order_report.xml).

    def _tectora_has_transport_order(self):
        """Orders of one roof project carry the transport order."""
        self.ensure_one()
        return bool(self.tectora_roof_project_id)

    def _tectora_transport_order_lines(self):
        """The material ordered from the vendor: the products on this order."""
        self.ensure_one()
        return [
            {"name": line.product_id.name, "qty": line.product_qty, "uom": line.uom_id.name}
            for line in self.order_line
            if not line.display_type and line.product_id
        ]

    def _tectora_transport_pickup_lines(self):
        """The project's own material that the crew fetches at the warehouse:
        what comes from stock and what was delivered to the warehouse."""
        self.ensure_one()
        project = self.tectora_roof_project_id
        materials = project.stock_material_line_ids | project.warehouse_material_line_ids
        return [
            {
                "name": material.product_id.name,
                "qty": material.quantity,
                "uom": (material.product_uom_id or material.product_id.uom_id).name,
            }
            for material in materials.sorted(lambda m: (m.sequence, m.id))
            if material.product_id and material.quantity
        ]

    def _tectora_transport_warehouse(self):
        """The warehouse the crew fetches its material at."""
        self.ensure_one()
        return self.picking_type_id.warehouse_id.filtered("partner_id") or self.env[
            "stock.warehouse"
        ].search([("company_id", "=", self.company_id.id)], limit=1)

    def _process_attachments_for_template_post(self, mail_template):
        """The purchase order mailed to the vendor of a roof project carries
        the transport order as a second PDF."""
        result = super()._process_attachments_for_template_post(mail_template) or {}
        order_reports = self.env["ir.actions.report"]
        for xmlid in ("purchase.action_report_purchase_order", "purchase.report_purchase_quotation"):
            order_reports |= self.env.ref(xmlid, raise_if_not_found=False) or order_reports
        report = self.env.ref(
            "tectora_purchase.action_report_transport_order", raise_if_not_found=False
        )
        if not report or not (mail_template.report_template_ids & order_reports):
            return result
        for order in self:
            if not order._tectora_has_transport_order():
                continue
            content, _format = self.env["ir.actions.report"]._render_qweb_pdf(report, order.ids)
            name = "Bestelbon materialen - %s.pdf" % order.name.replace("/", "-")
            result.setdefault(order.id, {}).setdefault("attachments", []).append(
                (name, BinaryBytes(content))
            )
        return result

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
