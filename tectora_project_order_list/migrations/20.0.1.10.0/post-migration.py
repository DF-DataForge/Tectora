# -*- coding: utf-8 -*-
"""Let the material list's purchase status follow the order list on upgrade.

The material list's purchase status and purchase order now also follow what
the order list ordered or delivers from the warehouse: recompute them for the
material lines whose product is on an order list already.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Material = env["tectora.roof.material"].with_context(active_test=False)
    materials = Material.search([])
    env.add_to_compute(Material._fields["order_list_product_ids"], materials)
    materials.flush_recordset(["order_list_product_ids"])
    linked = materials.filtered("order_list_product_ids")
    env.add_to_compute(Material._fields["purchase_state"], linked)
    env.add_to_compute(Material._fields["purchase_order_id"], linked)
    linked.flush_recordset(["purchase_state", "purchase_order_id"])
    _logger.info(
        "tectora_project_order_list: purchase status of %s material lines follows the order list",
        len(linked),
    )
