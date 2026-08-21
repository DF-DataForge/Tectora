# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        copy=False,
        index=True,
        help="Roof measurement project this quotation was generated from.",
    )

    def action_confirm(self):
        """On confirmation the order feeds the roof project's dossier: the
        analytic project link is completed (revenue) and the material list is
        (re)generated from the bills of materials of the sold products."""
        result = super().action_confirm()
        roof_orders = self.filtered("roof_project_id")
        for order in roof_orders:
            try:
                order._tectora_link_project()
                order._tectora_generate_materials()
            except Exception:
                _logger.exception(
                    "Could not build the roof project dossier for order %s",
                    order.name,
                )
        return result

    def _tectora_link_project(self):
        """Make sure the roof project has a project dossier and that this
        order points at it (which applies the analytic distribution)."""
        self.ensure_one()
        project = self.roof_project_id._ensure_project()
        if not project or "project_id" not in self._fields:
            return
        if not self.project_id:
            self.project_id = project
            # Re-trigger the analytic distribution now the project is known.
            self.order_line._compute_analytic_distribution()

    # ---------------------------------------------------------- material list
    def _tectora_material_values(self, line, product, quantity, uom, bom_name):
        return {
            "project_id": self.roof_project_id.id,
            "product_id": product.id,
            "product_uom_id": (uom or product.uom_id).id,
            "quantity": quantity,
            "source_product_id": line.product_id.id,
            "bom_name": bom_name or False,
            "sale_order_id": self.id,
            "sale_order_line_id": line.id,
        }

    def _tectora_generate_materials(self):
        """Explode every sold product into material requirements.

        Products with a bill of materials contribute their components (nested
        phantom BoMs included, as ``explode`` resolves those); products without
        one are themselves the material. Services are skipped. Lines generated
        by an earlier confirmation of this order are replaced.
        """
        self.ensure_one()
        Material = self.env["tectora.roof.material"]
        Material.search([("sale_order_id", "=", self.id)]).unlink()

        lines = self.order_line.filtered(
            lambda line: not line.display_type
            and line.product_id
            and line.product_id.type != "service"
        )
        if not lines:
            return Material

        boms = {}
        BoM = self.env.get("mrp.bom")  # Manufacturing is an optional dependency
        if BoM is not None:
            boms = BoM._bom_find(lines.product_id, company_id=self.company_id.id)

        values = []
        for line in lines:
            bom = boms.get(line.product_id) if boms else None
            quantity = line.product_uom_qty
            if not bom:
                values.append(
                    self._tectora_material_values(
                        line, line.product_id, quantity, line.product_uom_id, None
                    )
                )
                continue
            # explode() expects how many times the BoM is needed, in the BoM's
            # own unit of measure.
            bom_quantity = quantity
            if line.product_uom_id and bom.product_uom_id != line.product_uom_id:
                bom_quantity = line.product_uom_id._compute_quantity(
                    quantity, bom.product_uom_id
                )
            factor = bom_quantity / (bom.product_qty or 1.0)
            _boms_done, lines_done = bom.explode(line.product_id, factor)
            for bom_line, line_data in lines_done:
                values.append(
                    self._tectora_material_values(
                        line,
                        bom_line.product_id,
                        line_data["qty"],
                        bom_line.product_uom_id,
                        bom.display_name,
                    )
                )
        materials = Material.create(values) if values else Material
        if materials:
            self.roof_project_id.message_post(
                body=_(
                    "Materiaallijst bijgewerkt uit %(order)s: %(count)s "
                    "materiaallijn(en).",
                    order=self.name,
                    count=len(materials),
                )
            )
        return materials
