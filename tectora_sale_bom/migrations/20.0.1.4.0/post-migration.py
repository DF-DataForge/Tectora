# -*- coding: utf-8 -*-
"""A component with hercalculatie now costs per piece on a bill of materials
made to measure (the cost is pieces × the cost of one piece) instead of per
m, m² or m³: the kept cost of such lines is computed again. Their extra
margin, a new field, starts at the product's safety margin."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Not on cancelled orders (read-only), and without rebuilding a material
    # list per line: what is needed does not change, only what it costs.
    lines = env["tectora.sale.bom.line"].with_context(tectora_sale_bom_batch=True).search([
        ("product_id.tectora_recalc", "=", True),
        ("bom_id.order_id.state", "!=", "cancel"),
    ])
    lines._compute_unit_cost()
    lines.flush_recordset()
    _logger.info("tectora_sale_bom: cost per piece on %s component line(s)", len(lines))
