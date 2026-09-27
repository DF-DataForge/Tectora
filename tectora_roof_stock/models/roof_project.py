# -*- coding: utf-8 -*-
"""The material list of a roof project as an outgoing transfer.

The list (``tectora.roof.material``) says what the works need; the transfer
is what leaves the warehouse for the site. One roof project can have several
material transfers -- the list grows with a change order, part of it leaves
earlier -- so each new transfer carries only what no earlier one does.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    material_picking_ids = fields.One2many(
        "stock.picking",
        "tectora_roof_project_id",
        string="Materiaalleveringen",
        help="Uitgaande leveringen die uit de materiaallijst van dit dakproject "
        "klaargezet werden.",
    )
    material_picking_count = fields.Integer(
        compute="_compute_material_picking_count", string="Materiaalleveringen"
    )

    @api.depends("material_picking_ids.state")
    def _compute_material_picking_count(self):
        for project in self:
            project.material_picking_count = len(
                project.material_picking_ids.filtered(lambda p: p.state != "cancel")
            )

    def _get_pickings(self):
        """The Leveringen counters count the material transfers too."""
        return super()._get_pickings() | self.material_picking_ids

    # ------------------------------------------------------------ quantities
    def _material_requirements(self):
        """{product: quantity in the product's unit} of the goods on the list.

        Services are labour and do not move; the list is added up per product
        because several works items may need the same primer or screw.
        """
        self.ensure_one()
        needs = {}
        for line in self.material_line_ids:
            product = line.product_id
            if product.type != "consu" or line.quantity <= 0:
                continue
            quantity = line.quantity
            if line.product_uom_id and line.product_uom_id != product.uom_id:
                quantity = line.product_uom_id._compute_quantity(quantity, product.uom_id)
            needs[product] = needs.get(product, 0.0) + quantity
        return needs

    def _material_on_pickings(self):
        """{product: quantity} already on this project's material transfers
        that were not cancelled, in the product's unit."""
        self.ensure_one()
        shipped = {}
        pickings = self.material_picking_ids.filtered(lambda p: p.state != "cancel")
        for move in pickings.move_ids.filtered(lambda m: m.state != "cancel"):
            quantity = move.product_uom._compute_quantity(
                move.product_uom_qty, move.product_id.uom_id
            )
            shipped[move.product_id] = shipped.get(move.product_id, 0.0) + quantity
        return shipped

    def _material_to_ship(self):
        """What the list needs beyond what is already on a transfer."""
        self.ensure_one()
        shipped = self._material_on_pickings()
        remaining = {}
        for product, quantity in self._material_requirements().items():
            rest = float_round(
                quantity - shipped.get(product, 0.0),
                precision_rounding=product.uom_id.rounding,
            )
            if float_compare(rest, 0.0, precision_rounding=product.uom_id.rounding) > 0:
                remaining[product] = rest
        return remaining

    # --------------------------------------------------------------- picking
    def _material_picking_type(self):
        """The delivery operation type of the company's warehouse."""
        self.ensure_one()
        company = self.company_id or self.env.company
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)], limit=1
        )
        if not warehouse or not warehouse.out_type_id:
            raise UserError(
                _("Er is geen magazijn met een leveringsbewerking voor %s.", company.name)
            )
        return warehouse.out_type_id

    def _material_picking_partner(self):
        """The site: the order's delivery address, else the customer."""
        self.ensure_one()
        order = self.sale_order_id
        return (order.partner_shipping_id if order else self.partner_id) or self.partner_id

    def action_create_material_picking(self):
        """Put the material list on an outgoing transfer: one move per
        material for what is not on a transfer yet, addressed to the site and
        scheduled on the planned start of the works."""
        self.ensure_one()
        if not self._material_requirements():
            raise UserError(
                _("De materiaallijst van %s bevat geen goederen om te leveren.",
                  self.display_name)
            )
        to_ship = self._material_to_ship()
        if not to_ship:
            raise UserError(
                _("Alle materialen van %s staan al op een levering.", self.display_name)
            )
        picking_type = self._material_picking_type()
        partner = self._material_picking_partner()
        company = self.company_id or self.env.company
        source = picking_type.default_location_src_id
        destination = (
            picking_type.default_location_dest_id
            or (partner and partner.property_stock_customer)
            or self.env.ref("stock.stock_location_customers")
        )
        order = self.sale_order_id
        origin = " / ".join(filter(None, [order.name if order else "", self.code or self.name]))
        moves = [
            (0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "product_uom_qty": quantity,
                "product_uom": product.uom_id.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": company.id,
            })
            for product, quantity in sorted(
                to_ship.items(), key=lambda item: item[0].display_name or ""
            )
        ]
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "partner_id": partner.id if partner else False,
            "origin": origin,
            "scheduled_date": self.planned_date_begin or fields.Datetime.now(),
            "location_id": source.id,
            "location_dest_id": destination.id,
            "company_id": company.id,
            "tectora_roof_project_id": self.id,
            "move_ids": moves,
        })
        # Confirmed, so the warehouse sees it and reserves what it has; the
        # office validates it when the van is loaded.
        picking.action_confirm()
        self.message_post(
            body=_(
                "Levering %(picking)s klaargezet uit de materiaallijst: "
                "%(count)s materialen.",
                picking=picking._get_html_link(),
                count=len(picking.move_ids),
            )
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_material_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaalleveringen"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("tectora_roof_project_id", "=", self.id)],
            "context": {"default_tectora_roof_project_id": self.id},
        }
