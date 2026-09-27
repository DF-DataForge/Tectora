# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _tectora_line_material_values(self, line, bom):
        """A line with a bill of materials made to measure takes its
        components from there instead of from the product's.

        A component that is itself a kit (a phantom BoM) is exploded, as the
        product's bill of materials would be.
        """
        sale_bom = line.tectora_sale_bom_id
        if not sale_bom:
            return super()._tectora_line_material_values(line, bom)
        components = sale_bom.line_ids.filtered("product_id")
        kits = self.env["mrp.bom"]._bom_find(
            components.product_id, company_id=self.company_id.id, bom_type="phantom"
        )
        name = sale_bom.display_name
        values = []
        for component in components:
            quantity = component.total_quantity
            if not quantity:
                continue
            kit = kits.get(component.product_id)
            if not kit:
                values.append(
                    self._tectora_material_values(
                        line, component.product_id, quantity,
                        component.product_uom_id, name,
                    )
                )
                continue
            factor = component.product_uom_id._compute_quantity(
                quantity, kit.product_uom_id, round=False
            ) / (kit.product_qty or 1.0)
            _boms_done, lines_done = kit.explode(component.product_id, factor)
            for bom_line, line_data in lines_done:
                values.append(
                    self._tectora_material_values(
                        line,
                        bom_line.product_id,
                        self._tectora_exploded_quantity(kit, factor, bom_line, line_data),
                        bom_line.product_uom_id,
                        name,
                    )
                )
        return values

    def _tectora_exploded_quantity(self, bom, factor, bom_line, line_data):
        """A component with a fixed quantity takes that quantity once for the
        order line, whatever was sold; so do the contents of a fixed kit one
        level down (explode's quantities are linear in ``factor``)."""
        quantity = super()._tectora_exploded_quantity(bom, factor, bom_line, line_data)
        parent = line_data.get("parent_line")
        if bom_line.tectora_fixed_qty and bom_line.bom_id == bom:
            return bom_line.product_qty
        if parent and parent.tectora_fixed_qty and parent.bom_id == bom:
            return quantity / factor if factor else 0.0
        return quantity

    def _tectora_sale_bom_changed(self):
        """A bill of materials made to measure changed on a confirmed order:
        its material list follows. What is already on a transfer stays there;
        the next transfer carries the difference (tectora_roof_stock)."""
        for order in self:
            if order.state == "sale" and order.roof_project_id:
                order._tectora_generate_materials()
